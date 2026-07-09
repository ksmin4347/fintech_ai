"""Streamlit page renderers — one screen at a time (avoids st.tabs widget bleed)."""

from __future__ import annotations

import json
import html
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from streamlit_mic_recorder import speech_to_text
except Exception:  # pragma: no cover - optional browser component
    speech_to_text = None

from models.schemas import BusinessCase
from services.document_generator import generate_counselor_memo, generate_customer_guide
from services.live_consultation import (
    apply_live_profile_to_case,
    analyze_live_customer_profile,
    merge_transcript,
    should_refresh_live_analysis,
)
from services.realtime_speech_component import realtime_speech_to_text
from services.policy_loader import (
    load_policies,
    load_policies_from_upload,
    load_sample_cases,
    policies_to_dataframe,
    validate_policies,
)
from services.policy_rationale import build_eligibility_rationale
from services.policy_scoring import score_policy_results
from services.policy_rule_table import build_policy_rule_table, rule_table_summary
from services.policy_document_loader import load_markdown_file, load_pdf_file
from services.report_generator import generate_review_report, render_report_markdown
from services.readiness_package import build_readiness_package, render_readiness_package_markdown
from services.checklist_generator import generate_required_document_checklist
from services.rag_retriever import retrieve_relevant_chunks
from services.notification_service import (
    build_notification_payload,
    send_notification_email,
    send_notification_mock,
    _can_send_email,
)
from services.status_mapper import PUBLIC_STATUSES, map_condition_status, map_policy_status, public_status_icon
from utils.constants import (
    CAUTION_MESSAGE,
    DEFAULT_EVIDENCE_LOCATION,
    DEFAULT_FIELD_SOURCE,
    DEMO_NOTICE,
    FIELD_BASIS_PERIOD,
    FIELD_SOURCE_OPTIONS,
    FIELD_STATUS_OPTIONS,
    RAG_SCORE_LABEL,
    REQUIRED_FIELDS,
)
from utils.formatters import format_amount, format_months

# Import shared handlers from app module at runtime to avoid circular imports
ROOT = Path(__file__).resolve().parent

REPORT_TEMPLATE_OPTIONS = {
    "rm_review": "RM 심사 추천서형",
    "basic_consultation": "기본 상담 기록형",
    "handover_memo": "기관 인계 메모형",
}
MSG_TYPE_OPTIONS = {
    "kakao_mock": "카카오 알림톡형",
    "sms_short": "SMS 짧은 안내형",
    "email": "이메일 안내형",
}

TAB_NAMES = [
    "1. 상담 입력",
    "2. 사람 확인·구조화",
    "3. 누락정보 & 다음 질문",
    "4. 공개규칙 비교",
    "5. 자격격차 & 다음 행동",
    "6. 신청 준비 패키지",
    "7. 고객 안내문 / 발송",
    "8. 정책 데이터 관리",
]


def _as_dict_list(items):
    normalized = []
    for item in items or []:
        if isinstance(item, dict):
            normalized.append(item)
        elif callable(getattr(item, "model_dump", None)):
            normalized.append(item.model_dump())
        else:
            normalized.append(item)
    return normalized


def _style_status_rows(df: pd.DataFrame, status_col: str):
    def _row_style(row):
        status = str(row.get(status_col, ""))
        if status in ("미확인", "추가 확인 필요"):
            return ["background-color: rgba(255, 92, 92, 0.10);" for _ in row]
        if status == "공개조건 불일치":
            return ["background-color: rgba(255, 92, 92, 0.16);" for _ in row]
        if status == "확인 완료":
            return ["background-color: rgba(3, 199, 90, 0.10);" for _ in row]
        return ["" for _ in row]

    return df.style.apply(_row_style, axis=1)


def _style_public_status_rows(df: pd.DataFrame, status_col: str = "공개상태"):
    def _row_style(row):
        status = str(row.get(status_col, ""))
        if status == "공개조건 불일치":
            return ["background-color: rgba(255, 92, 92, 0.18);" for _ in row]
        if status == "추가 확인 필요":
            return ["background-color: rgba(255, 193, 7, 0.18);" for _ in row]
        if status == "확인 완료":
            return ["background-color: rgba(3, 199, 90, 0.12);" for _ in row]
        return ["" for _ in row]

    return df.style.apply(_row_style, axis=1)


PDF_ALIGNMENT_ROWS = [
    {
        "PDF 항목": "1~3. 정책금융 상담 실행 코파일럿/대표 상담 사례",
        "현재 반영": "상담 입력, 샘플 상담, 서울 음식점 운영자금 사례, 신청 준비 패키지",
        "상태": "반영",
    },
    {
        "PDF 항목": "4. 상담 입력 → AI 구조화 → 사람 확인 → 규칙 비교 → 신청 준비",
        "현재 반영": "1~7번 화면의 수직 흐름과 사람 확인·구조화 단계",
        "상태": "반영",
    },
    {
        "PDF 항목": "4.2 결과 상태 4종",
        "현재 반영": "확인 완료, 추가 확인 필요, 공개조건 불일치 3종 상태 매핑",
        "상태": "반영",
    },
    {
        "PDF 항목": "5~6. AI 추출 + 사람 확인, 정보 출처·확인상태·근거",
        "현재 반영": "GPT+규칙 파서, field_status/source/basis/evidence_location, 수정·승인자 기록",
        "상태": "강화 반영",
    },
    {
        "PDF 항목": "7. 실제 제도 규칙표",
        "현재 반영": "정책 DB를 조건 단위 제도 규칙표로 전개, CSV/JSON 다운로드",
        "상태": "강화 반영",
    },
    {
        "PDF 항목": "8. 4개 핵심 화면 MVP",
        "현재 반영": "기존 9개 기능을 유지하되 1~7번을 4단계 흐름으로 재정렬",
        "상태": "반영",
    },
    {
        "PDF 항목": "9. 공통 엔진 + 제도별 패키지",
        "현재 반영": "PolicyProduct 스키마, 규칙버전/검수상태/출처/한계 메타데이터",
        "상태": "반영",
    },
    {
        "PDF 항목": "11~12. 검증 과제와 팀원별 산출물",
        "현재 반영": "정책 규칙표, 상담 프로필, 비교 결과, 보고서/고객안내문/알림 생성",
        "상태": "반영",
    },
    {
        "PDF 항목": "운영 단계의 실제 공식 데이터 연동",
        "현재 반영": "Supabase 정책 DB 연동. 공식 공고 수집/정제 품질은 운영 데이터 상태에 따라 확장",
        "상태": "부분 반영",
    },
]


def _sync_live_voice_state(case: BusinessCase) -> None:
    if st.session_state.get("live_voice_case_id") == case.case_id:
        return
    st.session_state.live_voice_case_id = case.case_id
    st.session_state.live_voice_transcript = case.transcript or ""
    st.session_state.live_voice_last_text = ""
    st.session_state.live_voice_analysis = None
    st.session_state.live_voice_last_analysis_at = None
    st.session_state.live_voice_last_analysis_len = 0


def _render_live_voice_panel(case: BusinessCase, save_case) -> None:
    _sync_live_voice_state(case)
    st.markdown("#### 실시간 음성 상담")
    st.caption("말하는 동안 받아쓰기가 바로 표시되고, 약 7초마다 고객/사업자 기본정보만 구조화합니다.")

    payload = realtime_speech_to_text(
        initial_text=st.session_state.get("live_voice_transcript", case.transcript or ""),
        case_id=case.case_id,
        language="ko-KR",
        autosend_interval_ms=800,
        key=f"live_voice_browser_stt_{case.case_id}",
    )
    if isinstance(payload, dict) and payload.get("case_id") == case.case_id:
        payload_text = payload.get("transcript")
        if isinstance(payload_text, str):
            if payload.get("event_type") == "clear":
                merged = ""
            else:
                merged = payload_text.strip()
            if merged != st.session_state.get("live_voice_transcript", ""):
                st.session_state.live_voice_transcript = merged
                st.session_state.live_voice_last_text = payload.get("interim_transcript") or payload.get("final_transcript") or ""
                st.session_state.t1_transcript = merged
                case.transcript = merged
                save_case(case)

    live_text = st.text_area(
        "받아쓰기 원문",
        key="live_voice_transcript",
        height=150,
        help="마이크 인식 결과를 상담자가 바로 수정할 수 있습니다. 이 내용은 상담 분석에도 함께 사용됩니다.",
    )
    case.transcript = live_text
    st.session_state.t1_transcript = live_text
    save_case(case)

    last_at = st.session_state.get("live_voice_last_analysis_at")
    if should_refresh_live_analysis(
        live_text,
        last_at,
        int(st.session_state.get("live_voice_last_analysis_len", 0) or 0),
        interval_seconds=7,
    ):
        with st.spinner("실시간 상담 맥락 분석 중..."):
            st.session_state.live_voice_analysis = analyze_live_customer_profile(live_text)
            st.session_state.live_voice_last_analysis_at = datetime.now()
            st.session_state.live_voice_last_analysis_len = len(live_text.strip())
            if apply_live_profile_to_case(
                case,
                st.session_state.live_voice_analysis.get("parsed", {}),
                st.session_state.live_voice_analysis.get("corrections", []),
            ):
                save_case(case)

    analysis = st.session_state.get("live_voice_analysis")
    if analysis:
        m1, m2, m3 = st.columns(3)
        m1.metric("확인된 신상정보", analysis.get("confirmed", 0))
        m2.metric("추가 확인 필요", analysis.get("needs_review", 0))
        m3.metric("최근 분석", analysis.get("analyzed_at", "-"))
        st.markdown("**7초 요약 / 맥락**")
        st.info(analysis.get("summary", "요약할 상담 내용이 아직 없습니다."))
        corrections = analysis.get("corrections") or []
        if corrections:
            st.caption("음성 인식 문맥 보정")
            st.dataframe(pd.DataFrame(corrections), width="stretch", hide_index=True)
        rows = analysis.get("rows") or []
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        if analysis.get("parser_error"):
            st.warning(f"실시간 GPT 구조화 실패로 규칙 분석을 사용했습니다: {analysis['parser_error']}")

    if speech_to_text is not None:
        with st.expander("녹음 저장형 백업 사용", expanded=False):
            st.caption("브라우저 실시간 인식이 불안정할 때만 사용하세요. 중지 후 텍스트가 반영됩니다.")
            spoken_text = speech_to_text(
                language="ko-KR",
                start_prompt="백업 녹음 시작",
                stop_prompt="백업 녹음 중지·저장",
                just_once=False,
                use_container_width=True,
                key=f"live_voice_stt_{case.case_id}",
            )
            if spoken_text:
                merged = merge_transcript(st.session_state.live_voice_transcript, spoken_text)
                if merged != st.session_state.live_voice_transcript:
                    st.session_state.live_voice_transcript = merged
                    st.session_state.live_voice_last_text = spoken_text
                    st.session_state.t1_transcript = merged
                    case.transcript = merged
                    save_case(case)
                    st.rerun()


def render_tab_input(case: BusinessCase, save_case, run_analysis):
    st.subheader("상담 내용 입력")
    pending_inputs = st.session_state.pop("pending_input_values", None)
    should_sync_inputs = pending_inputs is not None or st.session_state.get("input_case_id") != case.case_id
    if should_sync_inputs:
        values = pending_inputs or {
            "t1_customer": case.customer_name or "",
            "t1_business": case.business_name or "",
            "t1_date": case.consultation_date or date.today(),
            "t1_raw": case.raw_consultation or "",
            "t1_memo": case.consultation_memo or "",
            "t1_transcript": case.transcript or "",
        }
        for key, value in values.items():
            st.session_state[key] = value
        if pending_inputs is not None:
            st.session_state.live_voice_transcript = values.get("t1_transcript", "")
            st.session_state.live_voice_last_text = ""
            st.session_state.live_voice_analysis = None
            st.session_state.live_voice_last_analysis_at = None
            st.session_state.live_voice_last_analysis_len = 0
        st.session_state.input_case_id = case.case_id

    def _text_input(label: str, key: str, default: str = "") -> str:
        if key in st.session_state:
            return st.text_input(label, key=key)
        return st.text_input(label, value=default, key=key)

    def _text_area(label: str, key: str, default: str = "", **kwargs) -> str:
        if key in st.session_state:
            return st.text_area(label, key=key, **kwargs)
        return st.text_area(label, value=default, key=key, **kwargs)

    def _date_input(label: str, key: str, default):
        if key in st.session_state:
            return st.date_input(label, key=key)
        return st.date_input(label, value=default, key=key)

    c1, c2 = st.columns(2)
    with c1:
        case.customer_name = _text_input("고객명", "t1_customer", case.customer_name or "")
        case.business_name = _text_input("사업체명", "t1_business", case.business_name or "")
    with c2:
        case.consultation_date = _date_input("상담 기준일", "t1_date", case.consultation_date or date.today())
    _render_live_voice_panel(case, save_case)
    st.divider()
    case.raw_consultation = _text_area("상담 원문", "t1_raw", case.raw_consultation or "", height=200)
    case.consultation_memo = _text_area("상담 메모", "t1_memo", case.consultation_memo or "", height=80)
    case.transcript = st.session_state.get("live_voice_transcript", case.transcript or "")
    st.session_state.t1_transcript = case.transcript or ""
    if st.button("🔍 상담 케이스 분석하기", type="primary", key="t1_analyze"):
        combined_input = "\n".join(
            part for part in [case.raw_consultation, case.consultation_memo, case.transcript] if part
        )
        if not combined_input.strip():
            st.error("상담 원문 또는 음성 받아쓰기 내용을 입력해 주세요.")
        else:
            run_analysis(case)
            st.success("분석 완료!")
            st.rerun()
    st.divider()
    st.markdown("**샘플 상담 불러오기**")
    samples = load_sample_cases()
    scols = st.columns(min(len(samples), 3))
    for i, s in enumerate(samples):
        with scols[i % 3]:
            if st.button(f"📋 {s['title']}", key=f"sample_{s['id']}", width="stretch"):
                case.customer_name = s["customer_name"]
                case.business_name = s["business_name"]
                case.raw_consultation = s["raw_consultation"]
                case.consultation_memo = s.get("memo", "")
                case.consultation_date = date.fromisoformat(s["consultation_date"])
                case.transcript = case.transcript or ""
                st.session_state.pending_input_values = {
                    "t1_customer": case.customer_name,
                    "t1_business": case.business_name,
                    "t1_date": case.consultation_date,
                    "t1_raw": case.raw_consultation,
                    "t1_memo": case.consultation_memo,
                    "t1_transcript": case.transcript or "",
                }
                st.session_state.input_case_id = case.case_id
                save_case(case)
                run_analysis(case)
                st.rerun()
    save_case(case)


def _customer_value(case: BusinessCase, field: str) -> str:
    value = getattr(case, field, None)
    if value in (None, "", "미확인"):
        return "확인 중"
    if field in {"required_amount", "annual_revenue", "monthly_revenue"} and isinstance(value, int):
        return format_amount(value)
    if field == "business_months" and isinstance(value, int):
        return format_months(value)
    return str(value)


def _customer_field_ready(case: BusinessCase, field: str) -> bool:
    value = getattr(case, field, None)
    return value not in (None, "", "미확인")


def _status_class(public_status: str) -> str:
    if public_status == "확인 완료":
        return "green"
    if public_status == "공개조건 불일치":
        return "red"
    if public_status == "추가 확인 필요":
        return "yellow"
    return "gray"


def _customer_policy_cards(eligibility_results) -> str:
    results = list(eligibility_results or [])
    if not results:
        return (
            '<div class="customer-card soft">'
            '<div class="customer-card-title">정책 검토</div>'
            '<div class="customer-card-value">분석 대기</div>'
            '<div class="customer-card-desc">상담사가 상담 내용을 분석하면 검토 가능한 지원정책 후보가 여기에 표시됩니다.</div>'
            "</div>"
        )

    scores = score_policy_results(results)
    status_order = {"확인 완료": 0, "추가 확인 필요": 1, "공개조건 불일치": 2}
    ranked = sorted(
        results,
        key=lambda item: (
            status_order.get(map_policy_status(item.final_status), 9),
            -scores.get(item.policy_id, {}).get("score", 0),
        ),
    )[:3]

    cards = []
    for result in ranked:
        public_status = map_policy_status(result.final_status)
        score_info = scores.get(result.policy_id, {})
        score = int(score_info.get("score", 0))
        grade = html.escape(str(score_info.get("grade", "검토 필요")))
        reason = html.escape(result.summary_reason or "공개조건 비교 결과를 바탕으로 상담사가 검토 중입니다.")
        documents = ", ".join((result.required_documents or [])[:3]) or "상담 후 안내"
        cards.append(
            '<div class="customer-policy">'
            '<div class="customer-policy-top">'
            "<div>"
            f'<div class="customer-policy-name">{html.escape(result.policy_name)}</div>'
            f'<div class="customer-policy-meta">{html.escape(result.institution)} · {grade}</div>'
            "</div>"
            f'<div class="customer-score">{score}%</div>'
            "</div>"
            '<div class="customer-chip-row">'
            f'<span class="status-pill {_status_class(public_status)}">{html.escape(public_status)}</span>'
            f'<span class="customer-chip">검토 우선순위 {score}%</span>'
            "</div>"
            f'<div class="customer-card-desc">{reason}</div>'
            f'<div class="customer-card-desc">예상 준비서류: {html.escape(documents)}</div>'
            "</div>"
        )
    return "".join(cards)


def render_customer_view(
    case: BusinessCase,
    *,
    analyzed: bool,
    missing_info,
    next_questions,
    eligibility_results,
) -> None:
    required_total = len(REQUIRED_FIELDS)
    ready_count = sum(1 for field, *_ in REQUIRED_FIELDS if _customer_field_ready(case, field))
    missing_count = len(missing_info or [])
    progress = round((ready_count / required_total) * 100) if required_total else 0
    policy_count = len(eligibility_results or [])
    confirmed_policies = sum(
        1 for result in (eligibility_results or [])
        if map_policy_status(result.final_status) == "확인 완료"
    )
    conditional_policies = sum(
        1 for result in (eligibility_results or [])
        if map_policy_status(result.final_status) == "추가 확인 필요"
    )

    customer_name = html.escape(case.customer_name or "고객")
    business_name = html.escape(case.business_name or "사업체")
    stage_label = "정책 검토 중" if analyzed else "상담 접수 중"
    step_classes = [
        "done",
        "active" if not analyzed else "done",
        "active" if analyzed and missing_count else ("done" if analyzed else ""),
        "active" if analyzed and not missing_count else "",
    ]

    st.markdown(
        f"""
        <div class="customer-hero">
            <div class="customer-hero-top">
                <div>
                    <div class="customer-kicker">CUSTOMER VIEW</div>
                    <div class="customer-title">{customer_name}님 상담 진행 현황</div>
                    <div class="customer-subtitle">{business_name} 기준으로 확인된 정보와 다음 준비사항을 정리했습니다. 최종 신청 가능 여부는 상담사가 공식 공고와 제출서류를 확인한 뒤 안내합니다.</div>
                </div>
                <div class="customer-percent">{progress}%</div>
            </div>
            <div class="customer-bar"><div class="customer-bar-fill" style="width:{progress}%;"></div></div>
            <div class="customer-chip-row">
                <span class="customer-chip">현재 단계 {html.escape(stage_label)}</span>
                <span class="customer-chip">확인된 정보 {ready_count}/{required_total}</span>
                <span class="customer-chip">추가 확인 {missing_count}</span>
                <span class="customer-chip">검토 정책 {policy_count}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="customer-steps">
            <div class="customer-step {step_classes[0]}">
                <div class="customer-step-label">1. 상담 접수</div>
                <div class="customer-step-desc">상담 내용과 사업 기본정보를 모으는 단계입니다.</div>
            </div>
            <div class="customer-step {step_classes[1]}">
                <div class="customer-step-label">2. 정보 확인</div>
                <div class="customer-step-desc">지역, 업종, 업력, 자금용도 등 필수 조건을 확인합니다.</div>
            </div>
            <div class="customer-step {step_classes[2]}">
                <div class="customer-step-label">3. 정책 비교</div>
                <div class="customer-step-desc">공개조건 기준으로 검토 가능한 지원정책을 좁힙니다.</div>
            </div>
            <div class="customer-step {step_classes[3]}">
                <div class="customer-step-label">4. 신청 준비</div>
                <div class="customer-step-desc">필요서류와 다음 행동을 정리해 신청 준비로 연결합니다.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="customer-grid">', unsafe_allow_html=True)
    cards = [
        ("업종", _customer_value(case, "industry"), "사업자등록증 기준으로 최종 확인합니다."),
        ("운영 지역", _customer_value(case, "region"), "지역별 보증·정책자금 조건에 사용됩니다."),
        ("업력", _customer_value(case, "business_months"), "업력 제한 조건 비교에 사용됩니다."),
        ("자금 용도", _customer_value(case, "funding_purpose"), "운영자금·시설자금 등 상품 매칭 기준입니다."),
    ]
    cols = st.columns(4)
    for col, (title, value, desc) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="customer-card">
                    <div class="customer-card-title">{html.escape(title)}</div>
                    <div class="customer-card-value">{html.escape(value)}</div>
                    <div class="customer-card-desc">{html.escape(desc)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)

    metric_cols = st.columns(3)
    with metric_cols[0]:
        st.markdown(
            f"""
            <div class="customer-card soft">
                <div class="customer-card-title">검토 가능 후보</div>
                <div class="customer-card-value">{confirmed_policies}건</div>
                <div class="customer-card-desc">현재 공개조건 기준으로 확인 완료에 가까운 정책입니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with metric_cols[1]:
        st.markdown(
            f"""
            <div class="customer-card soft">
                <div class="customer-card-title">추가 확인 후보</div>
                <div class="customer-card-value">{conditional_policies}건</div>
                <div class="customer-card-desc">서류나 세부 조건 확인 후 판단할 정책입니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with metric_cols[2]:
        st.markdown(
            f"""
            <div class="customer-card soft">
                <div class="customer-card-title">남은 확인사항</div>
                <div class="customer-card-value">{missing_count}개</div>
                <div class="customer-card-desc">빠르게 답변할수록 정책 비교 정확도가 올라갑니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="customer-section-title">고객님께 중요한 다음 확인사항</div>', unsafe_allow_html=True)
    question_items = list(next_questions or [])[:4]
    if question_items:
        list_html = "".join(
            f"<li>{html.escape(item.question)} <span style='color:#667085;'>({html.escape(item.related_policy)})</span></li>"
            for item in question_items
        )
    else:
        list_html = "<li>현재 추가 질문은 크지 않습니다. 상담사가 공식 공고와 제출서류 기준으로 한 번 더 확인합니다.</li>"
    st.markdown(
        f"""
        <div class="customer-card">
            <ul class="customer-list">{list_html}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="customer-section-title">지원정책 검토 요약</div>', unsafe_allow_html=True)
    st.markdown(_customer_policy_cards(eligibility_results), unsafe_allow_html=True)

    docs: list[str] = []
    for result in eligibility_results or []:
        for doc in result.required_documents or []:
            if doc and doc not in docs:
                docs.append(doc)
            if len(docs) >= 6:
                break
        if len(docs) >= 6:
            break
    if not docs:
        docs = ["사업자등록증", "대표자 신분증", "매출 확인자료", "신청기관 양식"]
    st.markdown('<div class="customer-section-title">미리 준비하면 좋은 자료</div>', unsafe_allow_html=True)
    doc_html = "".join(f"<li>{html.escape(doc)}</li>" for doc in docs)
    st.markdown(
        f"""
        <div class="customer-card">
            <ul class="customer-list">{doc_html}</ul>
            <div class="customer-card-desc">실제 필요서류는 선택한 정책과 기관 안내에 따라 달라질 수 있습니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _case_structure_fields() -> list[tuple[str, str]]:
    return [
        ("industry", "업종"), ("region", "사업장 지역"), ("business_type", "사업자 형태"), ("business_months", "업력(개월)"),
        ("annual_revenue", "연매출"), ("revenue_trend", "매출 상황"), ("funding_purpose", "자금 용도"),
        ("required_amount", "필요 자금"), ("existing_loan", "기존 대출"), ("existing_guarantee", "기존 보증"),
        ("credit_band", "신용구간"), ("tax_arrears", "세금 체납"), ("business_status", "사업 상태"),
    ]


def _render_case_edit_form(case: BusinessCase, run_analysis):
    fields = _case_structure_fields()
    status_options = FIELD_STATUS_OPTIONS

    with st.form("edit_case_form_tab3"):
        st.caption("고객 진술에서 근거가 확인된 값은 확인됨으로 표시됩니다. 모호하거나 빠진 값은 추가 확인 필요 또는 미확인으로 남겨 주세요.")
        meta1, meta2 = st.columns(2)
        reviewer_name = meta1.text_input("수정자", value="상담자", key="t3_reviewer")
        approver_name = meta2.text_input("승인자(선택)", value="", key="t3_approver")

        def _editor_value(field: str) -> str:
            value = getattr(case, field, None)
            return "" if value in (None, "") else str(value)

        def _parse_editor_value(field: str, value) -> str | int | None:
            if value is None or pd.isna(value):
                return None
            text = str(value).strip()
            if not text:
                return None
            if field in ("annual_revenue", "required_amount", "business_months"):
                compact = text.replace(",", "")
                if "억" in compact:
                    match = re.search(r"(\d+(?:\.\d+)?)", compact)
                    return int(float(match.group(1)) * 100_000_000) if match else None
                if "만" in compact:
                    match = re.search(r"(\d+(?:\.\d+)?)", compact)
                    return int(float(match.group(1)) * 10_000) if match else None
                digits = re.sub(r"[^0-9]", "", compact)
                return int(digits) if digits else None
            return text

        core_rows = []
        for f, label in fields:
            current_status = case.field_status.get(f, "미확인")
            if current_status not in status_options:
                current_status = "미확인"
            core_rows.append({
                "항목": label,
                "값": _editor_value(f),
                "확인상태": current_status,
            })
        edited_core = st.data_editor(
            pd.DataFrame(core_rows),
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            disabled=["항목"],
            column_config={
                "확인상태": st.column_config.SelectboxColumn("확인상태", options=status_options, required=True),
            },
            key="t3_core_editor",
        )

        source_edits = {}
        basis_edits = {}
        location_edits = {}
        evidence_edits = {}
        with st.expander("출처·근거 상세 편집(선택)", expanded=False):
            st.caption("서류 확인, 기관 조회, 증빙 페이지처럼 세부 근거를 남겨야 할 때만 열어서 수정하세요.")
            detail_rows = []
            for f, label in fields:
                current_source = case.field_source.get(f) or (
                    DEFAULT_FIELD_SOURCE if case.field_evidence.get(f) else "미확인"
                )
                detail_rows.append({
                    "항목": label,
                    "정보출처": current_source,
                    "기준기간": case.field_basis_period.get(f) or FIELD_BASIS_PERIOD.get(f, ""),
                    "근거위치": case.field_evidence_location.get(f) or (
                        DEFAULT_EVIDENCE_LOCATION if case.field_evidence.get(f) else ""
                    ),
                    "근거문장": case.field_evidence.get(f, ""),
                })
            edited_detail = st.data_editor(
                pd.DataFrame(detail_rows),
                width="stretch",
                hide_index=True,
                num_rows="fixed",
                disabled=["항목"],
                column_config={
                    "정보출처": st.column_config.SelectboxColumn("정보출처", options=FIELD_SOURCE_OPTIONS, required=True),
                },
                key="t3_detail_editor",
            )

        core_records = edited_core.to_dict("records")
        detail_records = edited_detail.to_dict("records")
        edits = {}
        status_edits = {}
        for (f, _), row in zip(fields, core_records):
            edits[f] = _parse_editor_value(f, row.get("값"))
            status_edits[f] = row.get("확인상태") or "미확인"
        for (f, _), row in zip(fields, detail_records):
            source_edits[f] = row.get("정보출처") or "미확인"
            basis_edits[f] = str(row.get("기준기간") or "")
            location_edits[f] = str(row.get("근거위치") or "")
            evidence_edits[f] = str(row.get("근거문장") or "")

        if st.form_submit_button("수정 후 다시 검토"):
            reviewer = reviewer_name.strip() or "상담자"
            approver = approver_name.strip()
            timestamp = datetime.now().isoformat(timespec="seconds")
            case.field_audit_log = list(case.field_audit_log or [])
            for f, val in edits.items():
                before = {
                    "value": getattr(case, f, None),
                    "status": case.field_status.get(f, "미확인"),
                    "source": case.field_source.get(f, ""),
                    "basis_period": case.field_basis_period.get(f, ""),
                    "evidence_location": case.field_evidence_location.get(f, ""),
                    "evidence": case.field_evidence.get(f, ""),
                }
                new_value = val
                setattr(case, f, new_value)
                case.field_status[f] = status_edits[f]
                case.field_source[f] = source_edits[f]
                case.field_basis_period[f] = basis_edits[f].strip()
                case.field_evidence_location[f] = location_edits[f].strip()
                case.field_evidence[f] = evidence_edits[f].strip()
                after = {
                    "value": new_value,
                    "status": case.field_status.get(f, "미확인"),
                    "source": case.field_source.get(f, ""),
                    "basis_period": case.field_basis_period.get(f, ""),
                    "evidence_location": case.field_evidence_location.get(f, ""),
                    "evidence": case.field_evidence.get(f, ""),
                }
                if before != after:
                    case.field_updated_by[f] = reviewer
                    if approver:
                        case.field_approved_by[f] = approver
                    case.field_audit_log.append({
                        "timestamp": timestamp,
                        "field": f,
                        "updated_by": reviewer,
                        "approved_by": approver,
                        "before": before,
                        "after": after,
                    })
            run_analysis(case)
            st.rerun()


def render_tab_structure(case: BusinessCase, run_analysis):
    st.subheader("사람 확인·구조화")
    if not st.session_state.analyzed:
        st.warning("먼저 분석을 실행해 주세요.")
        return
    parser_mode = st.session_state.get("parser_mode", "rules") or "rules"
    st.caption(f"구조화 방식: {parser_mode}. 3번 화면에서 상담자가 값을 수정하고 다시 검토할 수 있습니다.")
    if st.session_state.get("parser_error"):
        st.warning(f"GPT 구조화 실패로 규칙 파서를 사용했습니다: {st.session_state.parser_error}")
    fields = _case_structure_fields()

    rows = []
    for f, label in fields:
        val = getattr(case, f, None)
        display = format_amount(val) if f in ("annual_revenue", "required_amount") else (
            format_months(val) if f == "business_months" else (val or "미확인"))
        current_source = case.field_source.get(f) or (DEFAULT_FIELD_SOURCE if case.field_evidence.get(f) else "미확인")
        current_basis = case.field_basis_period.get(f) or FIELD_BASIS_PERIOD.get(f, "")
        current_location = case.field_evidence_location.get(f) or (
            DEFAULT_EVIDENCE_LOCATION if case.field_evidence.get(f) else ""
        )
        rows.append({
            "항목": label, "값": display,
            "상태": case.field_status.get(f, "미확인"),
            "정보 출처": current_source,
            "기준 기간": current_basis,
            "근거 위치": current_location,
            "근거": case.field_evidence.get(f, ""),
            "수정자": case.field_updated_by.get(f, ""),
            "승인자": case.field_approved_by.get(f, ""),
        })
    rows_df = pd.DataFrame(rows)
    structure_view = rows_df[["항목", "값", "상태", "정보 출처", "근거"]]
    st.dataframe(_style_status_rows(structure_view, "상태"), width="stretch", hide_index=True)
    with st.expander("상세 신뢰도 정보 보기", expanded=False):
        st.dataframe(rows_df, width="stretch", hide_index=True)


def render_tab_missing(case: BusinessCase, run_analysis):
    st.subheader("누락정보 & 상담 정보 수정")
    if not st.session_state.analyzed:
        st.warning("먼저 분석을 실행해 주세요.")
        return
    missing = st.session_state.missing_info
    if missing:
        st.error(f"⚠️ {len(missing)}개 항목 미확인/추가 확인 필요")
        st.dataframe(pd.DataFrame([
            {"항목": m.field_label, "상태": m.current_status, "이유": m.reason, "질문": m.sample_question}
            for m in missing
        ]), width="stretch", hide_index=True)
    else:
        st.success("필수 정보 확인 완료")
    st.divider()
    st.markdown("### 상담 정보 수정")
    _render_case_edit_form(case, run_analysis)


def render_tab_eligibility(render_policy_card):
    st.subheader("공개규칙 비교")
    if not st.session_state.analyzed:
        st.warning("먼저 분석을 실행해 주세요.")
        return
    results = st.session_state.eligibility_results
    score_map = score_policy_results(results)
    pmap = {p.policy_id: p for p in st.session_state.policies}
    filt = st.radio(
        "필터", ["전체"] + PUBLIC_STATUSES,
        horizontal=True, key="t4_filter",
    )
    filtered = results if filt == "전체" else [r for r in results if map_policy_status(r.final_status) == filt]
    filtered = sorted(filtered, key=lambda r: score_map.get(r.policy_id, {}).get("score", 0), reverse=True)
    mcols = st.columns(len(PUBLIC_STATUSES) + 1)
    avg_score = round(sum(score_map.get(r.policy_id, {}).get("score", 0) for r in results) / len(results)) if results else 0
    mcols[0].metric("평균 점수", avg_score)
    for i, s in enumerate(PUBLIC_STATUSES):
        mcols[i + 1].metric(f"{public_status_icon(s)} {s}", sum(1 for r in results if map_policy_status(r.final_status) == s))

    with st.expander("점수 산출 방식", expanded=False):
        st.markdown(
            "- 점수는 승인 확률이 아니라 상담자가 먼저 볼 정책을 정렬하기 위한 검토 우선순위입니다.\n"
            "- 공개조건 비교 결과만 사용하며, 지역·사업자 형태·업종·업력·자금용도 같은 핵심 조건에 조금 더 높은 가중치를 둡니다.\n"
            "- 확인 완료 조건은 온점수, 추가 확인 필요/미확인은 부분점수, 공개조건 불일치는 0점으로 계산합니다.\n"
            "- 공개조건 불일치가 있으면 총점 상한을 낮춰 불리한 조건이 있는 정책이 과도하게 상위에 오르지 않게 했습니다.\n"
            "- 민감정보나 임의 추정값은 점수에 넣지 않고, 모든 감점 사유는 상세표에 그대로 보여줍니다."
        )

    for r in filtered:
        score_info = score_map.get(r.policy_id, {})
        render_policy_card(r, score=score_info.get("score"))
        with st.expander(f"상세: {r.policy_name}"):
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("검토 점수", score_info.get("score", 0))
            s2.metric("확인 완료", score_info.get("confirmed_count", 0))
            s3.metric("추가 확인", score_info.get("needs_info_count", 0))
            s4.metric("불일치", score_info.get("mismatch_count", 0))
            st.caption(score_info.get("method", ""))
            rationale = build_eligibility_rationale(r)
            g1, g2, g3 = st.columns(3)
            with g1:
                st.markdown("**추천 근거**")
                for item in rationale["recommend_reasons"]:
                    st.markdown(f"- {item}")
            with g2:
                st.markdown("**비추천·주의 근거**")
                for item in rationale["caution_reasons"]:
                    st.markdown(f"- {item}")
            with g3:
                st.markdown("**추가 확인 필요**")
                for item in rationale["missing_reasons"]:
                    st.markdown(f"- {item}")
            st.divider()
            condition_df = pd.DataFrame([
                {"조건": c.condition_name, "고객": c.customer_value, "기준": c.policy_requirement,
                 "공개상태": map_condition_status(c.result), "내부결과": c.result, "근거": c.reason}
                for c in r.condition_results
            ])
            st.dataframe(_style_public_status_rows(condition_df), width="stretch", hide_index=True)
            p = pmap.get(r.policy_id)
            if p:
                st.caption(f"출처: {p.source_name} | {p.source_url} | 기준일: {p.source_date}")


def render_tab_rag(case: BusinessCase, run_rag_curation, index_policy_docs, render_rag_card):
    st.subheader("RAG 상품 큐레이션")
    st.caption("상담 케이스와 정책 문서 근거를 함께 사용해 검토 우선순위가 높은 상품을 큐레이션합니다.")
    st.warning(f"{RAG_SCORE_LABEL}는 승인 확률이 아닙니다. {CAUTION_MESSAGE}")
    if not st.session_state.analyzed:
        st.warning("먼저 상담 케이스를 분석해 주세요.")
        return
    st.info(
        f"업종: {case.industry or '미확인'} | 지역: {case.region or '미확인'} | "
        f"자금용도: {case.funding_purpose or '미확인'} | 필요금액: {format_amount(case.required_amount)}"
    )
    rc1, rc2, rc3 = st.columns(3)
    if rc1.button("📚 정책 문서 인덱싱하기", key="t5_index"):
        index_policy_docs()
        st.success(f"인덱싱 완료: chunk {len(st.session_state.rag_chunks)}개")
    if rc2.button("🎯 RAG 상품 큐레이션 실행", type="primary", key="t5_run"):
        run_rag_curation(case)
        st.success("Top 3 큐레이션 완료!")
        st.rerun()
    if rc3.button("🔄 결과 새로고침", key="t5_refresh"):
        run_rag_curation(case)
        st.rerun()
    recs = st.session_state.rag_recommendations
    if recs:
        for rec in recs:
            render_rag_card(rec)
        st.download_button(
            "📥 RAG 추천 결과 JSON",
            json.dumps([r.model_dump() for r in recs], ensure_ascii=False, indent=2, default=str),
            "rag_recommendations.json", "application/json", key="t5_dl_json",
        )
    else:
        st.info("'RAG 상품 큐레이션 실행' 버튼을 눌러주세요.")


def render_tab_gap(generate_gap_summary):
    st.subheader("자격격차 & 다음 행동")
    if not st.session_state.analyzed:
        st.warning("먼저 분석을 실행해 주세요.")
        return
    score_map = score_policy_results(st.session_state.eligibility_results)
    actionable = [
        result for result in st.session_state.eligibility_results
        if map_policy_status(result.final_status) in ("확인 완료", "추가 확인 필요")
    ]
    actionable = sorted(actionable, key=lambda r: score_map.get(r.policy_id, {}).get("score", 0), reverse=True)
    if not actionable:
        st.info("현재 확인 완료 또는 추가 확인 필요 상태의 지원정책이 없습니다.")
        return

    st.caption("공개조건 불일치 정책은 제외하고, 바로 확인하거나 진행할 수 있는 정책만 표시합니다.")
    for result in actionable[:12]:
        public_status = map_policy_status(result.final_status)
        score_info = score_map.get(result.policy_id, {})
        title = f"{public_status_icon(public_status)} {result.policy_name} · 점수 {score_info.get('score', 0)}"
        with st.expander(title, expanded=public_status == "확인 완료"):
            confirmed = [
                c for c in result.condition_results
                if map_condition_status(c.result) == "확인 완료" and c.result == "충족"
            ]
            needs = [
                c for c in result.condition_results
                if map_condition_status(c.result) == "추가 확인 필요"
            ]
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**확인 완료 조건**")
                if confirmed:
                    for condition in confirmed[:6]:
                        st.markdown(f"- {condition.condition_name}: {condition.reason}")
                else:
                    st.caption("명확히 충족된 공개조건이 아직 없습니다.")
            with c2:
                st.markdown("**추가 확인 조건**")
                if needs:
                    for condition in needs[:6]:
                        st.markdown(f"- {condition.condition_name}: {condition.reason}")
                else:
                    st.caption("추가 확인 조건이 없습니다.")

            actions = []
            for condition in needs[:4]:
                actions.append(f"{condition.condition_name} 확인: 고객값 '{condition.customer_value}'를 기준 '{condition.policy_requirement}'와 대조")
            if result.required_documents:
                actions.append("필요서류 준비: " + ", ".join(result.required_documents[:3]))
            source_url = (result.source or {}).get("source_url", "")
            if source_url:
                actions.append("공식 공고 링크에서 신청기간·접수방법 재확인")
            actions.extend(result.next_actions[:3])
            actions = list(dict.fromkeys(actions)) or ["상담자가 고객 제출자료와 공식 공고를 최종 확인"]

            st.markdown("**다음 행동**")
            for i, action in enumerate(actions[:7], start=1):
                st.checkbox(action, key=f"gap_action_{result.policy_id}_{i}")


def render_tab_report(case: BusinessCase, run_rag_curation):
    st.subheader("신청 준비 패키지")
    if not st.session_state.analyzed:
        st.warning("먼저 상담 케이스를 분석해 주세요.")
        return

    template_id = st.selectbox(
        "보고서 템플릿",
        options=list(REPORT_TEMPLATE_OPTIONS.keys()),
        format_func=lambda k: REPORT_TEMPLATE_OPTIONS[k],
        key="t7_report_template",
    )

    if st.button("📋 신청 준비 패키지 생성", type="primary", key="t7_gen_report"):
        try:
            if not st.session_state.rag_recommendations:
                run_rag_curation(case)
            recs = st.session_state.rag_recommendations
            report = generate_review_report(
                case, st.session_state.eligibility_results, recs,
                _as_dict_list(st.session_state.missing_info),
                _as_dict_list(st.session_state.next_questions),
                template_type=template_id,
                gap_analysis=_as_dict_list(st.session_state.gaps),
            )
            st.session_state.review_report = report
            st.session_state.review_report_md = render_report_markdown(report)
            st.session_state.checklist_items = report.required_documents
            package = build_readiness_package(
                case,
                st.session_state.eligibility_results,
                recs,
                _as_dict_list(st.session_state.missing_info),
                _as_dict_list(st.session_state.next_questions),
                report.required_documents,
                report.aftercare_tasks,
            )
            st.session_state.readiness_package = package
            st.session_state.readiness_package_md = render_readiness_package_markdown(package)
            st.success("신청 준비 패키지 생성 완료!")
        except Exception as e:
            st.error(f"신청 준비 패키지 생성 중 오류: {e}")
            st.exception(e)

    if st.session_state.get("readiness_package_md"):
        package = st.session_state.readiness_package
        if package:
            st.metric("신청 준비 상태", f"{public_status_icon(package.package_status)} {package.package_status}")
            st.info(package.readiness_summary)
        st.markdown("### 신청 준비 패키지 미리보기")
        st.markdown(st.session_state.readiness_package_md)
        pk1, pk2 = st.columns(2)
        pk1.download_button(
            "📥 패키지 Markdown",
            st.session_state.readiness_package_md,
            "신청준비패키지.md",
            "text/markdown",
            key="t7_dl_package_md",
        )
        if st.session_state.readiness_package:
            pk2.download_button(
                "📥 패키지 JSON",
                json.dumps(
                    st.session_state.readiness_package.model_dump(mode="json"),
                    ensure_ascii=False, indent=2, default=str,
                ),
                "신청준비패키지.json", "application/json", key="t7_dl_package_json",
            )

    if st.session_state.review_report_md:
        st.divider()
        with st.expander("보고서 원문 보기", expanded=False):
            st.markdown(st.session_state.review_report_md)
        dl1, dl2 = st.columns(2)
        dl1.download_button(
            "📥 Markdown", st.session_state.review_report_md,
            "심사보고서.md", "text/markdown", key="t7_dl_md",
        )
        if st.session_state.review_report:
            dl2.download_button(
                "📥 JSON",
                json.dumps(
                    st.session_state.review_report.model_dump(mode="json"),
                    ensure_ascii=False, indent=2, default=str,
                ),
                "심사보고서.json", "application/json", key="t7_dl_json",
            )

    st.divider()
    st.subheader("필수 구비 서류 체크리스트")
    checklist = st.session_state.checklist_items
    if checklist:
        st.dataframe(pd.DataFrame([{
            "서류": c.document_name, "우선순위": c.priority,
            "이유": c.reason, "관련상품": c.required_for, "준비방법": c.how_to_prepare,
        } for c in checklist]), width="stretch", hide_index=True)
        st.download_button(
            "📥 체크리스트 CSV",
            pd.DataFrame([c.model_dump() for c in checklist]).to_csv(index=False).encode("utf-8-sig"),
            "서류체크리스트.csv", "text/csv", key="t7_dl_checklist",
        )
    else:
        st.caption("보고서 생성 후 체크리스트가 표시됩니다.")

    st.subheader("후속 관리 태스크")
    if st.session_state.review_report:
        tasks = st.session_state.review_report.aftercare_tasks
        st.dataframe(pd.DataFrame([t.model_dump() for t in tasks]), width="stretch", hide_index=True)
        st.download_button(
            "📥 태스크 CSV",
            pd.DataFrame([t.model_dump() for t in tasks]).to_csv(index=False).encode("utf-8-sig"),
            "애프터케어.csv", "text/csv", key="t7_dl_tasks",
        )


def render_tab_notification(case: BusinessCase, run_rag_curation):
    st.subheader("고객 안내문 / 발송 미리보기")
    tone = st.radio(
        "안내문 톤", ["친절한 설명형", "간단 요약형", "문자 발송형"],
        horizontal=True, key="t8_tone",
    )
    msg_type_id = st.radio(
        "알림 유형",
        options=list(MSG_TYPE_OPTIONS.keys()),
        format_func=lambda k: MSG_TYPE_OPTIONS[k],
        key="t8_msg_type",
    )

    if st.session_state.analyzed and st.button("✉️ 고객 안내문 생성하기", key="t8_gen_guide"):
        st.session_state.customer_guide = generate_customer_guide(
            case, st.session_state.eligibility_results,
            st.session_state.missing_info, st.session_state.next_questions, tone,
        )
        st.session_state.customer_guide_version = st.session_state.get("customer_guide_version", 0) + 1

    guide = st.session_state.get("customer_guide", "")
    if guide:
        guide_key = f"t8_guide_preview_{st.session_state.get('customer_guide_version', 0)}"
        st.text_area("고객 안내문", value=guide, height=300, key=guide_key, disabled=True)
        st.download_button("📥 안내문 Markdown", guide, "고객안내문.md", "text/markdown", key="t8_dl_guide")

    def _build_payload(message_type: str):
        if not st.session_state.review_report:
            if not st.session_state.rag_recommendations:
                run_rag_curation(case)
            report = generate_review_report(
                case, st.session_state.eligibility_results, st.session_state.rag_recommendations,
                _as_dict_list(st.session_state.missing_info),
                _as_dict_list(st.session_state.next_questions),
            )
            st.session_state.review_report = report
        else:
            report = st.session_state.review_report
        checklist = st.session_state.checklist_items or generate_required_document_checklist(
            case, st.session_state.rag_recommendations, st.session_state.eligibility_results,
        )
        st.session_state.checklist_items = checklist
        return build_notification_payload(case, report, checklist, message_type)

    st.divider()
    st.subheader("문자 미리보기")
    phone = st.text_input("수신 전화번호 (선택)", value=st.session_state.customer_phone, key="t8_phone")
    st.session_state.customer_phone = phone

    if st.button("📨 문자 미리보기 만들기", key="t8_mock_send"):
        try:
            payload = _build_payload(msg_type_id)
            if phone:
                payload.recipient_phone = phone
            st.session_state.notification_payload = payload
            st.session_state.notification_result = send_notification_mock(payload)
            st.session_state.notification_preview_version = st.session_state.get("notification_preview_version", 0) + 1
            st.success("문자 미리보기를 만들었습니다. 실제 문자는 발송되지 않습니다.")
        except Exception as e:
            st.error(f"메시지 생성 오류: {e}")

    if st.session_state.notification_payload:
        msg_preview_key = f"t8_msg_preview_{st.session_state.get('notification_preview_version', 0)}"
        st.text_area(
            "메시지 미리보기", value=st.session_state.notification_payload.message_body,
            height=250, key=msg_preview_key, disabled=True,
        )

    st.divider()
    st.subheader("이메일 실제 발송")
    email = st.text_input("수신 이메일", value=st.session_state.customer_email, key="t8_email")
    st.session_state.customer_email = email
    email_consent = st.checkbox("고객 이메일 발송 동의 확인", key="t8_email_consent")
    smtp_ready = _can_send_email()
    valid_email = bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))

    if not smtp_ready:
        st.info("실제 이메일 발송을 사용하려면 `.env`에 SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL을 설정해 주세요.")
    if email and not valid_email:
        st.warning("이메일 주소 형식을 확인해 주세요.")

    email_disabled = not smtp_ready or not email_consent or not valid_email
    if st.button("📧 실제 이메일 발송", disabled=email_disabled, key="t8_email_send"):
        try:
            payload = _build_payload("email")
            payload.recipient_email = email.strip()
            st.session_state.notification_payload = payload
            st.session_state.notification_preview_version = st.session_state.get("notification_preview_version", 0) + 1
            result = send_notification_email(payload)
            st.session_state.notification_result = result
            if result.success:
                st.success(result.message)
            else:
                st.error(result.message)
        except Exception as e:
            st.error(f"이메일 발송 중 오류: {e}")


def render_tab_policy_data(case: BusinessCase, run_analysis, index_policy_docs):
    st.subheader("정책 데이터 관리")
    if os.getenv("POLICY_DATA_SOURCE", "").strip().lower() == "supabase":
        source_table = os.getenv("SUPABASE_POLICY_TABLE", "announcements")
        policy_count = len(st.session_state.get("policies", []) or [])
        if st.session_state.get("policy_load_error"):
            st.error(f"Supabase 정책 DB 로딩 오류: {st.session_state.policy_load_error}")
        elif policy_count:
            st.success(f"Supabase 정책 DB `{source_table}`에서 {policy_count}건을 불러왔습니다.")
        else:
            st.warning(f"Supabase 정책 DB `{source_table}` 연결은 되었지만 현재 앱에서 조회되는 정책이 0건입니다.")
    else:
        st.info(DEMO_NOTICE)
    with st.expander("PDF 반영 점검표", expanded=False):
        st.dataframe(pd.DataFrame(PDF_ALIGNMENT_ROWS), width="stretch", hide_index=True)

    df = policies_to_dataframe(st.session_state.policies)
    display_cols = [
        "policy_id", "policy_name", "institution", "policy_type",
        "rule_version", "rule_review_status", "is_sample_data",
    ]
    display_cols = [col for col in display_cols if col in df.columns]
    st.dataframe(
        df[display_cols],
        width="stretch", hide_index=True,
    )
    rule_df = build_policy_rule_table(st.session_state.policies)
    summary = rule_table_summary(rule_df)
    st.divider()
    st.subheader("제도 규칙표")
    st.caption("PDF 7번 기준으로 DB의 각 지원정책을 사업장 소재지, 사업자 형태, 업종·제외업종, 업력, 자금 목적, 필요서류, 내부심사 한계 등 조건 단위로 펼친 표입니다.")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("제도 수", summary["policies"])
    r2.metric("규칙 행", summary["rule_rows"])
    r3.metric("검수 필요 행", summary["needs_review"])
    r4.metric("샘플 제도", summary["sample_sources"])

    if not rule_df.empty:
        rule_items = ["전체"] + sorted(rule_df["규칙항목"].unique().tolist())
        institutions = ["전체"] + sorted(rule_df["기관"].unique().tolist())
        f1, f2, f3 = st.columns(3)
        selected_rule = f1.selectbox("규칙항목", rule_items, key="t9_rule_item_filter")
        selected_inst = f2.selectbox("기관", institutions, key="t9_rule_inst_filter")
        only_review = f3.checkbox("검수 필요만 보기", key="t9_rule_review_only")

        view_df = rule_df.copy()
        if selected_rule != "전체":
            view_df = view_df[view_df["규칙항목"] == selected_rule]
        if selected_inst != "전체":
            view_df = view_df[view_df["기관"] == selected_inst]
        if only_review:
            view_df = view_df[view_df["구조화 내용"].astype(str).str.contains("미구조화|대조 필요", regex=True)]

        rule_cols = [
            "제도명", "기관", "규칙항목", "구조화 내용", "시스템 처리",
            "고객 프로필 필드", "검수상태", "규칙버전", "출처기준일",
        ]
        st.dataframe(view_df[rule_cols], width="stretch", hide_index=True)
        d1, d2 = st.columns(2)
        d1.download_button(
            "📥 규칙표 CSV",
            rule_df.to_csv(index=False).encode("utf-8-sig"),
            "policy_rule_table.csv",
            "text/csv",
            key="t9_dl_rule_csv",
        )
        d2.download_button(
            "📥 규칙표 JSON",
            json.dumps(rule_df.to_dict(orient="records"), ensure_ascii=False, indent=2, default=str),
            "policy_rule_table.json",
            "application/json",
            key="t9_dl_rule_json",
        )

        with st.expander("규칙표 작성 기준"):
            st.markdown(
                "- 공개된 대상, 제외조건, 신청기간, 필요서류만 구조화 비교 대상으로 둡니다.\n"
                "- 내부심사, 예외, 재량, 개인별 보증한도, 금리 판단은 시스템이 판단하지 않고 추가 확인 필요로 둡니다.\n"
                "- 새 제도를 추가할 때는 정책 JSON의 조건 필드와 출처/규칙버전/검수상태를 함께 채우는 방식으로 확장합니다."
            )

    if not st.session_state.rag_indexed:
        st.caption("정책 문서 인덱싱이 필요합니다.")
    for doc in st.session_state.policy_documents:
        st.caption(f"📄 {doc.title} | {doc.institution}")

    c1, c2 = st.columns(2)
    if c1.button("🔄 정책 DB 다시 불러오기", key="t9_reload"):
        st.session_state.policies = load_policies()
        if st.session_state.analyzed:
            run_analysis(case)
        st.rerun()
    if c2.button("📚 정책 문서 재인덱싱", key="t9_reindex"):
        index_policy_docs()
        st.success(f"chunk {len(st.session_state.rag_chunks)}개")
        st.rerun()
    st.download_button(
        "📥 정책 JSON",
        json.dumps([p.model_dump(mode="json") for p in st.session_state.policies], ensure_ascii=False, indent=2),
        "policies_current.json",
        "application/json",
        key="t9_dl_json",
    )

    doc_upload = st.file_uploader("정책 문서 업로드", type=["md", "txt", "pdf"], key="t9_doc_upload")
    if doc_upload:
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / doc_upload.name
            fp.write_bytes(doc_upload.read())
            content = load_pdf_file(str(fp)) if fp.suffix == ".pdf" else load_markdown_file(str(fp))
            st.text_area("미리보기", content[:1000], height=150, key="t9_preview", disabled=True)

    uploaded = st.file_uploader("정책 JSON/CSV 업로드", type=["json", "csv"], key="t9_json_upload")
    if uploaded:
        try:
            new_p = load_policies_from_upload(uploaded)
            errs = validate_policies(new_p)
            if errs:
                st.error("\n".join(errs))
            else:
                st.session_state.policies = new_p
                st.success(f"{len(new_p)}건 로드됨")
        except Exception as e:
            st.error(str(e))

    with st.expander("기존 상담기록 생성"):
        if st.button("📄 상담기록 생성하기", key="t9_memo"):
            st.session_state.counselor_memo = generate_counselor_memo(
                case, st.session_state.eligibility_results,
                st.session_state.missing_info, st.session_state.next_questions,
            )
        if st.session_state.get("counselor_memo"):
            st.text_area("상담기록", st.session_state.counselor_memo, height=200, key="t9_memo_text", disabled=True)
