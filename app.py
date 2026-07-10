"""소상공인 금융상담 AI 코파일럿 - Streamlit MVP"""

from __future__ import annotations

import html
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from services.eligibility_engine import evaluate_all_policies
from services.gap_analyzer import analyze_gaps, generate_gap_summary
from services.live_consultation import normalize_finance_transcript_for_analysis
from services.missing_info import detect_missing_info
from services.parser import parse_consultation
from services.policy_loader import (
    get_supabase_policy_cache_info,
    load_cached_supabase_policies,
    load_policies,
)
from services.policy_document_loader import load_policy_documents
from services.question_generator import generate_next_questions
from services.rag_chunker import chunk_documents
from services.rag_curator import curate_top_policies
from services.rag_retriever import build_query_from_case, retrieve_relevant_chunks
from services.llm_client import LLMClient
from services.policy_rationale import build_recommendation_rationale
from services.status_mapper import is_verified_field_status, map_policy_status
from models.schemas import BusinessCase
from utils.brand_assets import brand_logo_data_uri
from utils.constants import DEMO_NOTICE, DISCLAIMER, SERVICE_NAME, SERVICE_TAGLINE, UNKNOWN
from utils.ui_theme import (
    inject_global_styles,
    policy_card_html,
    render_case_header,
    render_quality_metrics,
    render_workflow_strip,
)

from app_pages import (
    TAB_NAMES,
    render_tab_eligibility,
    render_tab_gap,
    render_tab_input,
    render_tab_missing,
    render_tab_notification,
    render_tab_policy_data,
    render_tab_report,
    render_tab_structure,
    render_customer_view,
)

POLICY_DOCS_DIR = ROOT / "data" / "policy_docs"

st.set_page_config(page_title=SERVICE_NAME, page_icon="🏦", layout="wide", initial_sidebar_state="expanded")
inject_global_styles()


def policy_data_signature() -> str:
    return "|".join(
        [
            os.getenv("POLICY_DATA_SOURCE", "local").strip().lower(),
            os.getenv("SUPABASE_URL", "").strip(),
            os.getenv("SUPABASE_POLICY_TABLE", "").strip(),
            os.getenv("SUPABASE_POLICY_DOCUMENT_TABLE", "").strip(),
        ]
    )


def is_supabase_policy_source() -> bool:
    return os.getenv("POLICY_DATA_SOURCE", "").strip().lower() == "supabase"


def load_policy_state(force: bool = False) -> None:
    signature = policy_data_signature()
    source_changed = st.session_state.get("policy_data_signature") != signature
    empty_supabase_state = is_supabase_policy_source() and not st.session_state.get("policies")
    if force or source_changed or empty_supabase_state or st.session_state.get("policies") is None:
        try:
            st.session_state.policies = load_policies()
            st.session_state.policy_load_error = ""
            st.session_state.policy_load_warning = ""
            st.session_state.policy_load_detail = ""
        except Exception as e:
            cached_policies = load_cached_supabase_policies() if is_supabase_policy_source() else []
            if cached_policies:
                cache_info = get_supabase_policy_cache_info()
                cached_at = cache_info.get("cached_at")
                cached_at_text = f" 캐시시각: {cached_at}." if cached_at else ""
                st.session_state.policies = cached_policies
                st.session_state.policy_load_error = ""
                st.session_state.policy_load_warning = (
                    f"Supabase 실시간 연결은 실패했지만 마지막 성공 캐시 "
                    f"{len(cached_policies)}건으로 임시 운영 중입니다.{cached_at_text}"
                )
                st.session_state.policy_load_detail = str(e)
            else:
                st.session_state.policies = []
                st.session_state.policy_load_error = str(e)
                st.session_state.policy_load_warning = ""
                st.session_state.policy_load_detail = str(e)
        st.session_state.policy_data_signature = signature
        st.session_state.rag_indexed = False
        st.session_state.rag_chunks = []
        st.session_state.rag_evidence = []
        st.session_state.rag_recommendations = []


def init_session():
    defaults = {
        "cases": {}, "current_case_id": None, "policies": None,
        "eligibility_results": [], "missing_info": [], "next_questions": [],
        "gaps": [], "analyzed": False,
        "parser_mode": "", "parser_error": "",
        "policy_documents": [], "rag_chunks": [], "rag_indexed": False,
        "rag_evidence": [], "rag_recommendations": [], "rag_query": "",
        "review_report": None, "review_report_md": "",
        "readiness_package": None, "readiness_package_md": "",
        "checklist_items": [], "notification_payload": None,
        "notification_result": None, "customer_phone": "", "customer_email": "",
        "customer_guide": "", "customer_guide_version": 0,
        "notification_preview_version": 0,
        "active_tab": TAB_NAMES[0],
        "view_mode": "상담사용",
        "pending_case_select": None,
        "analysis_case_id": None,
        "policy_data_signature": "",
        "policy_load_error": "",
        "policy_load_warning": "",
        "policy_load_detail": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    load_policy_state()


init_session()


def get_current_case() -> BusinessCase | None:
    cid = st.session_state.current_case_id
    if not cid:
        return None
    case = st.session_state.cases.get(cid)
    if isinstance(case, dict):
        case = BusinessCase(**case)
        st.session_state.cases[cid] = case
    return case


def save_case(case: BusinessCase):
    st.session_state.cases[case.case_id] = case
    st.session_state.current_case_id = case.case_id
    st.session_state.pending_case_select = case.case_id


def _normalize_field_statuses(statuses: dict) -> dict:
    return {
        field: ("확인됨" if status == "AI 후보" else status)
        for field, status in (statuses or {}).items()
    }


def _analysis_source_text(case: BusinessCase) -> str:
    parts = []
    if case.raw_consultation and case.raw_consultation.strip():
        parts.append(f"[상담 원문]\n{case.raw_consultation.strip()}")
    if case.consultation_memo and case.consultation_memo.strip():
        parts.append(f"[상담 메모]\n{case.consultation_memo.strip()}")
    if case.transcript and case.transcript.strip():
        normalized_transcript, corrections = normalize_finance_transcript_for_analysis(case.transcript.strip())
        if corrections and normalized_transcript.strip():
            parts.append(f"[실시간 음성 받아쓰기-금융문맥 보정]\n{normalized_transcript.strip()}")
            parts.append(f"[실시간 음성 받아쓰기 원문]\n{case.transcript.strip()}")
        else:
            parts.append(f"[실시간 음성 받아쓰기]\n{case.transcript.strip()}")
    return "\n\n".join(parts)


def run_analysis(case: BusinessCase):
    st.session_state.analysis_case_id = case.case_id
    previous_status = _normalize_field_statuses(dict(case.field_status or {}))
    previous_evidence = dict(case.field_evidence or {})
    previous_source = dict(case.field_source or {})
    previous_basis_period = dict(case.field_basis_period or {})
    previous_evidence_location = dict(case.field_evidence_location or {})
    previous_updated_by = dict(case.field_updated_by or {})
    previous_approved_by = dict(case.field_approved_by or {})
    previous_audit_log = list(case.field_audit_log or [])
    parsed = parse_consultation(_analysis_source_text(case))
    st.session_state.parser_mode = parsed.get("parser_mode", "rules")
    st.session_state.parser_error = parsed.get("parser_error", "")
    for field, val in parsed.items():
        if field in (
            "field_evidence",
            "field_status",
            "field_source",
            "field_basis_period",
            "field_evidence_location",
            "parser_mode",
            "parser_error",
        ):
            continue
        previous_value = getattr(case, field, None)
        manually_reviewed = previous_status.get(field) not in (None, "", "미확인")
        if previous_value not in (None, "", UNKNOWN) and (
            is_verified_field_status(previous_status.get(field)) or manually_reviewed
        ):
            continue
        if val is not None and hasattr(case, field):
            setattr(case, field, val)
    parsed_evidence = parsed.get("field_evidence", {})
    parsed_status = _normalize_field_statuses(parsed.get("field_status", {}))
    parsed_source = parsed.get("field_source", {})
    parsed_basis_period = parsed.get("field_basis_period", {})
    parsed_evidence_location = parsed.get("field_evidence_location", {})
    case.field_evidence = {**parsed_evidence, **previous_evidence}
    case.field_status = {**parsed_status, **previous_status}
    case.field_source = {**parsed_source, **previous_source}
    case.field_basis_period = {**parsed_basis_period, **previous_basis_period}
    case.field_evidence_location = {**parsed_evidence_location, **previous_evidence_location}
    case.field_updated_by = previous_updated_by
    case.field_approved_by = previous_approved_by
    case.field_audit_log = previous_audit_log
    case.updated_at = datetime.now()
    missing = detect_missing_info(case)
    questions = generate_next_questions(case, missing)
    ref_date = case.consultation_date or date.today()
    results = evaluate_all_policies(case, st.session_state.policies, ref_date)
    gaps = analyze_gaps(case, results, st.session_state.policies)
    st.session_state.missing_info = missing
    st.session_state.next_questions = questions
    st.session_state.eligibility_results = results
    st.session_state.gaps = gaps
    st.session_state.analyzed = True
    save_case(case)


def index_policy_docs(extra_dir: str | None = None):
    docs = load_policy_documents(str(POLICY_DOCS_DIR))
    if extra_dir:
        docs.extend(load_policy_documents(extra_dir))
    st.session_state.policy_documents = docs
    st.session_state.rag_chunks = chunk_documents(docs)
    st.session_state.rag_indexed = True


def run_rag_curation(case: BusinessCase):
    if not st.session_state.rag_indexed:
        index_policy_docs()
    chunks = st.session_state.rag_chunks
    st.session_state.rag_query = build_query_from_case(case, case.transcript)
    evidence = retrieve_relevant_chunks(case, chunks, top_k=8, transcript=case.transcript)
    st.session_state.rag_evidence = evidence
    st.session_state.rag_recommendations = curate_top_policies(
        case, st.session_state.eligibility_results, evidence, top_n=3,
    )


def render_policy_card(result, score: int | None = None):
    display_status = map_policy_status(result.final_status)
    st.markdown(
        policy_card_html(result.policy_name, result.institution, display_status, result.summary_reason, score=score),
        unsafe_allow_html=True,
    )


def render_rag_card(rec):
    from utils.constants import RAG_SCORE_LABEL
    display_status = map_policy_status(rec.review_status)
    st.markdown(
        policy_card_html(
            rec.policy_name,
            rec.institution,
            display_status,
            f"{RAG_SCORE_LABEL}는 승인 확률이 아닙니다.",
            rank=rec.priority_rank,
            score=rec.fit_score,
        ),
        unsafe_allow_html=True,
    )
    st.caption("검토 우선순위 점수는 승인 확률이 아닙니다.")
    rationale = build_recommendation_rationale(rec)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**추천 근거**")
        for item in rationale["recommend_reasons"]:
            st.markdown(f"- {item}")
    with c2:
        st.markdown("**비추천·주의 근거**")
        for item in rationale["caution_reasons"]:
            st.markdown(f"- {item}")
    with c3:
        st.markdown("**추가 확인 필요**")
        for item in rationale["missing_reasons"]:
            st.markdown(f"- {item}")
    with st.expander(f"근거 문서 ({len(rec.evidence)}건)"):
        for ev in rec.evidence:
            st.markdown(f"**{ev.title}** ({ev.score:.3f})")
            st.text(ev.text[:400])


# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    llm_client = LLMClient()
    llm_ready = llm_client.is_available()
    llm_message = llm_client.setup_message()
    brand_logo = brand_logo_data_uri("fincoc_logo.png")
    st.markdown(
        f"""
        <div class="sidebar-brand">
            <div class="sidebar-brand-top">
                <div class="sidebar-logo"><img src="{brand_logo}" alt="fincoc 로고" /></div>
                <div>
                    <div class="sidebar-eyebrow">POLICY COPILOT</div>
                    <div class="sidebar-brand-title">{html.escape(SERVICE_NAME)}</div>
                </div>
            </div>
            <div class="sidebar-brand-desc">{html.escape(SERVICE_TAGLINE)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sidebar-section">빠른 작업</div>', unsafe_allow_html=True)
    if st.button("＋ 새 상담 케이스", width="stretch", key="sb_new_case"):
        new_case = BusinessCase(case_id=str(uuid.uuid4())[:8], created_at=datetime.now())
        save_case(new_case)
        st.session_state.pending_input_values = {
            "t1_customer": "",
            "t1_business": "",
            "t1_date": date.today(),
            "t1_raw": "",
            "t1_memo": "",
            "t1_transcript": "",
        }
        st.session_state.input_case_id = new_case.case_id
        st.session_state.analyzed = False
        st.session_state.analysis_case_id = None
        st.session_state.active_tab = TAB_NAMES[0]
        st.rerun()
    case_ids = list(st.session_state.cases.keys())
    if case_ids:
        st.markdown('<div class="sidebar-section">상담 케이스</div>', unsafe_allow_html=True)
        labels = {cid: f"{st.session_state.cases[cid].customer_name or '미입력'} ({cid})" for cid in case_ids}
        pending_case_id = st.session_state.get("pending_case_select")
        if pending_case_id in case_ids:
            st.session_state.sb_case_select = pending_case_id
            st.session_state.current_case_id = pending_case_id
            st.session_state.pending_case_select = None
        elif st.session_state.get("sb_case_select") in case_ids:
            st.session_state.current_case_id = st.session_state.sb_case_select
        elif st.session_state.current_case_id in case_ids:
            st.session_state.sb_case_select = st.session_state.current_case_id
        else:
            st.session_state.current_case_id = case_ids[0]
            st.session_state.sb_case_select = case_ids[0]
        idx = case_ids.index(st.session_state.current_case_id)
        selected_case_id = st.selectbox(
            "현재 상담 케이스", case_ids,
            format_func=lambda x: labels[x], index=idx, key="sb_case_select",
        )
        st.session_state.current_case_id = selected_case_id
    st.markdown('<div class="sidebar-section">시스템 상태</div>', unsafe_allow_html=True)
    status_rows = [
        ("GPT", llm_message, llm_ready),
    ]
    if is_supabase_policy_source():
        source_table = os.getenv("SUPABASE_POLICY_TABLE", "announcements")
        policy_count = len(st.session_state.get("policies", []) or [])
        policy_error = st.session_state.get("policy_load_error")
        policy_warning = st.session_state.get("policy_load_warning")
        if policy_error:
            policy_status = "로딩 오류"
        elif policy_warning:
            policy_status = f"캐시 운영 · {policy_count}건"
        else:
            policy_status = f"{source_table} · {policy_count}건"
        status_rows.append(("정책 DB", policy_status, not bool(policy_error) and policy_count > 0))
    else:
        status_rows.append(("정책 DB", DEMO_NOTICE, False))
    status_rows.append(("알림", os.getenv("NOTIFICATION_MODE", "mock"), True))
    status_html = []
    for label, value, ok in status_rows:
        dot_class = "sidebar-dot" if ok else "sidebar-dot muted"
        status_html.append(
            '<div class="sidebar-status-row">'
            f'<div class="sidebar-status-label"><span class="{dot_class}"></span>{html.escape(str(label))}</div>'
            f'<div class="sidebar-status-value">{html.escape(str(value))}</div>'
            "</div>"
        )
    st.markdown(f'<div class="sidebar-status-card">{"".join(status_html)}</div>', unsafe_allow_html=True)
    policy_error = st.session_state.get("policy_load_error")
    policy_warning = st.session_state.get("policy_load_warning")
    policy_detail = st.session_state.get("policy_load_detail")
    if is_supabase_policy_source() and policy_warning:
        st.warning(policy_warning)
        if policy_detail:
            with st.expander("연결 오류 상세", expanded=False):
                st.code(policy_detail)
        if st.button("정책 DB 다시 연결", key="sb_retry_policy_db", width="stretch"):
            load_policy_state(force=True)
            st.rerun()
    elif is_supabase_policy_source() and policy_error:
        st.error("Supabase 정책 DB 로딩 오류입니다. 연결 정보를 확인한 뒤 다시 시도해 주세요.")
        if policy_detail or policy_error:
            with st.expander("오류 상세", expanded=False):
                st.code(policy_detail or policy_error)
        if st.button("정책 DB 다시 연결", key="sb_retry_policy_db", width="stretch"):
            load_policy_state(force=True)
            st.rerun()

    st.markdown('<div class="sidebar-section">안내</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="sidebar-notice">{html.escape(DISCLAIMER)}</div>',
        unsafe_allow_html=True,
    )

case = get_current_case()
analysis_case_id = st.session_state.get("analysis_case_id")
if (
    st.session_state.get("analyzed")
    and analysis_case_id in st.session_state.cases
    and case is not None
    and case.case_id != analysis_case_id
):
    st.session_state.current_case_id = analysis_case_id
    st.session_state.pending_case_select = analysis_case_id
    case = st.session_state.cases[analysis_case_id]
if not case:
    brand_logo = brand_logo_data_uri("fincoc_logo.png")
    st.markdown(
        f"""
        <div class="app-topbar">
            <div class="app-title-row">
                <div>
                    <div class="app-kicker">POLICY FINANCE COPILOT</div>
                    <div class="app-brand-title">
                        <img class="app-logo" src="{brand_logo}" alt="fincoc 로고" />
                        <div class="app-title">{html.escape(SERVICE_NAME)}</div>
                    </div>
                    <div class="app-subtitle">사이드바에서 새 상담 케이스를 만든 뒤 상담 입력을 시작하세요.</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.info("사이드바에서 **새 상담 케이스**를 만든 뒤 **1. 상담 입력** 화면에서 샘플을 불러오세요.")
    st.stop()

# 상단 탭 UI (기존과 동일) — 각 탭은 fragment로 분리해 다른 탭 위젯이 섞이지 않음
if st.session_state.active_tab not in TAB_NAMES:
    st.session_state.active_tab = TAB_NAMES[0]

render_case_header(
    case,
    st.session_state.active_tab,
    analyzed=st.session_state.analyzed,
    parser_mode=st.session_state.get("parser_mode", ""),
    missing_count=len(st.session_state.get("missing_info", [])),
    policy_count=len(st.session_state.get("policies", []) or []),
)

st.markdown(
    """
    <div class="view-mode-note">
        <strong>화면 모드</strong>
        <span>상담사는 전체 기능을 사용하고, 고객용은 상담 진행 현황과 다음 준비사항만 보여줍니다.</span>
    </div>
    """,
    unsafe_allow_html=True,
)
view_mode = st.radio(
    "화면 모드",
    ["상담사용", "고객용"],
    key="view_mode",
    horizontal=True,
    label_visibility="collapsed",
)

if view_mode == "고객용":
    render_customer_view(
        case,
        analyzed=st.session_state.analyzed,
        missing_info=st.session_state.get("missing_info", []),
        next_questions=st.session_state.get("next_questions", []),
        eligibility_results=st.session_state.get("eligibility_results", []),
    )
    st.stop()

active_tab = st.radio(
    "화면 선택",
    TAB_NAMES,
    key="active_tab",
    horizontal=True,
    label_visibility="collapsed",
)
render_workflow_strip(active_tab)
if st.session_state.analyzed:
    render_quality_metrics(
        case,
        len(st.session_state.get("missing_info", [])),
        len(st.session_state.get("policies", []) or []),
        st.session_state.get("eligibility_results", []),
        len(st.session_state.get("rag_recommendations", [])),
    )


@st.fragment
def _screen_tab1():
    render_tab_input(case, save_case, run_analysis)


@st.fragment
def _screen_tab2():
    render_tab_structure(case, run_analysis)


@st.fragment
def _screen_tab3():
    render_tab_missing(case, run_analysis)


@st.fragment
def _screen_tab4():
    render_tab_eligibility(render_policy_card)


@st.fragment
def _screen_tab5():
    render_tab_gap(generate_gap_summary)


@st.fragment
def _screen_tab6():
    render_tab_report(case, run_rag_curation)


@st.fragment
def _screen_tab7():
    render_tab_notification(case, run_rag_curation)


@st.fragment
def _screen_tab8():
    render_tab_policy_data(case, run_analysis, index_policy_docs)


if active_tab == TAB_NAMES[0]:
    _screen_tab1()
elif active_tab == TAB_NAMES[1]:
    _screen_tab2()
elif active_tab == TAB_NAMES[2]:
    _screen_tab3()
elif active_tab == TAB_NAMES[3]:
    _screen_tab4()
elif active_tab == TAB_NAMES[4]:
    _screen_tab5()
elif active_tab == TAB_NAMES[5]:
    _screen_tab6()
elif active_tab == TAB_NAMES[6]:
    _screen_tab7()
elif active_tab == TAB_NAMES[7]:
    _screen_tab8()
