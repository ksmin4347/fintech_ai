"""Document generation for counselor and customer."""

from __future__ import annotations

import json
from datetime import date

from models.schemas import BusinessCase, EligibilityResult, MissingInfoItem, NextQuestion
from services.llm_client import LLMClient
from services.status_mapper import map_policy_status
from utils.constants import DISCLAIMER, DOCUMENT_DISCLAIMER
from utils.formatters import format_amount, format_months


def _group_results(results: list[EligibilityResult]) -> dict[str, list[EligibilityResult]]:
    groups: dict[str, list[EligibilityResult]] = {
        "검토 가능": [],
        "조건부 검토": [],
        "제외 가능성": [],
        "판단 보류": [],
    }
    for r in results:
        groups.setdefault(r.final_status, []).append(r)
    return groups


def _enhance_customer_guide_with_llm(
    template_text: str,
    case: BusinessCase,
    eligibility_results: list[EligibilityResult],
    missing_info: list[MissingInfoItem],
    next_questions: list[NextQuestion],
    tone: str,
) -> str:
    client = LLMClient()
    if not client.is_available():
        return template_text
    system_prompt = (
        "너는 소상공인 정책금융 상담 후 고객 안내문을 작성하는 보조자다. "
        "고객에게 친절하고 명확하게 쓰되, 승인·대출·보증 확정, 개인별 한도, 금리 확정 표현은 쓰지 않는다. "
        "입력된 사실과 규칙 비교 결과만 사용하고 없는 정보는 추가 확인이 필요하다고 말한다."
    )
    payload = {
        "tone": tone,
        "case": {
            "customer_name": case.customer_name,
            "business_name": case.business_name,
            "industry": case.industry,
            "region": case.region,
            "business_type": case.business_type,
            "business_months": case.business_months,
            "funding_purpose": case.funding_purpose,
            "required_amount": case.required_amount,
            "field_status": case.field_status,
            "field_source": case.field_source,
            "field_basis_period": case.field_basis_period,
        },
        "policy_statuses": [
            {
                "policy_name": r.policy_name,
                "institution": r.institution,
                "status": map_policy_status(r.final_status),
                "reason": r.summary_reason,
                "missing_fields": r.missing_fields,
            }
            for r in eligibility_results[:5]
        ],
        "missing_info": [
            {"field": m.field_label, "question": m.sample_question}
            for m in missing_info[:8]
        ],
        "next_questions": [q.question for q in next_questions[:8]],
        "draft": template_text,
        "required_caution": DOCUMENT_DISCLAIMER,
    }
    length_hint = "SMS처럼 500자 이내로" if tone == "문자 발송형" else "Markdown 형식으로"
    user_prompt = (
        f"아래 초안을 {tone} 톤으로 다시 작성해라. {length_hint} 작성하고, "
        "필요서류와 추가 확인사항을 빠뜨리지 마라. "
        "마지막에는 주의사항을 한 문장 이상 포함해라.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
    text = client.generate_text(system_prompt, user_prompt)
    return text.strip() if text and text.strip() else template_text


def generate_counselor_memo(
    case: BusinessCase,
    eligibility_results: list[EligibilityResult],
    missing_info: list[MissingInfoItem],
    next_questions: list[NextQuestion],
) -> str:
    groups = _group_results(eligibility_results)
    today = case.consultation_date or date.today()

    lines = [
        "# 소상공인 금융상담 기록 (상담자용 초안)",
        "",
        f"**상담 기준일:** {today}",
        f"**고객명:** {case.customer_name or '미입력'}",
        f"**사업체명:** {case.business_name or '미입력'}",
        "",
        "## 1. 사업자 상황 요약",
        f"- 업종: {case.industry or '미확인'}",
        f"- 지역: {case.region or '미확인'}",
        f"- 사업자 형태: {case.business_type or '미확인'}",
        f"- 업력: {format_months(case.business_months)}",
        f"- 연매출: {format_amount(case.annual_revenue)}",
        f"- 매출 추이: {case.revenue_trend or '미확인'}",
        f"- 자금용도: {case.funding_purpose or '미확인'}",
        f"- 필요금액: {format_amount(case.required_amount)}",
        f"- 기존 대출: {case.existing_loan or '미확인'}",
        f"- 기존 보증: {case.existing_guarantee or '미확인'}",
        f"- 신용: {case.credit_band or case.credit_score or '미확인'}",
        f"- 세금 체납: {case.tax_arrears or '미확인'}",
        f"- 사업상태: {case.business_status or '미확인'}",
        "",
        "## 2. 확인된 정보",
    ]
    confirmed = [k for k, v in (case.field_status or {}).items() if v == "확인됨"]
    lines.append(", ".join(confirmed) if confirmed else "구조화된 확인 정보 없음")

    lines.extend([
        "",
        "## 3. 미확인 정보",
    ])
    for m in missing_info:
        lines.append(f"- {m.field_label}: {m.current_status} — {m.reason}")

    lines.extend(["", "## 4. 추가 질문"])
    for i, q in enumerate(next_questions[:8], 1):
        lines.append(f"{i}. [{q.priority}] {q.question} ({q.reason})")

    lines.extend(["", "## 5. 정책 검토 결과"])
    for status, items in groups.items():
        if not items:
            continue
        lines.append(f"### {status}")
        for r in items:
            lines.append(f"- **{r.policy_name}** ({r.institution}): {r.summary_reason}")
            if r.exclusion_reasons:
                lines.append(f"  - 제외/보류 사유: {'; '.join(r.exclusion_reasons)}")
            if r.missing_fields:
                lines.append(f"  - 추가 확인: {', '.join(r.missing_fields)}")

    all_docs: set[str] = set()
    for r in eligibility_results:
        if r.final_status in ("검토 가능", "조건부 검토"):
            all_docs.update(r.required_documents)

    lines.extend([
        "",
        "## 6. 필요 서류 (통합)",
    ])
    for doc in sorted(all_docs):
        lines.append(f"- {doc}")

    lines.extend([
        "",
        "## 7. 후속 조치",
        "- 미확인 정보 추가 질문 후 케이스 업데이트",
        "- 검토 가능/조건부 상품에 대해 공식 공고 재확인",
        "- 고객 안내문 전달 및 서류 준비 안내",
        "",
        "## 8. 상담자 유의사항",
        f"- {DISCLAIMER}",
        f"- {DOCUMENT_DISCLAIMER}",
        "- 본 문서는 AI 생성 초안이며 상담자가 공식 기준으로 최종 검토해야 합니다.",
        "",
        "## 9. 공식 출처",
    ])
    for r in eligibility_results[:5]:
        src = r.source
        lines.append(f"- {r.policy_name}: {src.get('source_name', '')} ({src.get('source_url', '')})")

    return "\n".join(lines)


def generate_customer_guide(
    case: BusinessCase,
    eligibility_results: list[EligibilityResult],
    missing_info: list[MissingInfoItem],
    next_questions: list[NextQuestion],
    tone: str = "친절한 설명형",
) -> str:
    groups = _group_results(eligibility_results)
    name = case.customer_name or "고객"
    business = case.business_name or "사업체"

    if tone == "간단 요약형":
        intro = f"{name} 님, {business} 관련 자금 상담 요약입니다."
    elif tone == "문자 발송형":
        intro = f"[소상공인 금융상담 안내]\n{name} 님, 안녕하세요. 상담 내용을 정리해 드립니다."
    else:
        intro = f"{name} 님, 안녕하세요.\n오늘 상담해 주신 {business} 관련 자금 지원 방향을 정리해 드립니다."

    lines = [
        intro,
        "",
        "## 검토할 수 있는 지원 방향",
    ]

    reviewable = groups.get("검토 가능", []) + groups.get("조건부 검토", [])
    if reviewable:
        for r in reviewable[:4]:
            status_note = "추가 확인 후 검토 가능" if r.final_status == "조건부 검토" else "조건 충족 시 검토 가능"
            lines.append(f"- **{r.policy_name}** ({r.institution}): {status_note}")
    else:
        lines.append("- 현재 확인된 정보로는 바로 검토 가능한 상품이 제한적입니다. 아래 추가 확인 후 다시 검토하겠습니다.")

    lines.extend(["", "## 추가로 확인이 필요한 사항"])
    if missing_info:
        for m in missing_info[:6]:
            lines.append(f"- {m.field_label}: {m.sample_question}")
    else:
        lines.append("- 현재 필수 정보가 대부분 확인되었습니다.")

    lines.extend(["", "## 준비하시면 좋은 서류"])
    docs: set[str] = set()
    for r in reviewable:
        docs.update(r.required_documents)
    for doc in sorted(docs)[:8]:
        lines.append(f"- {doc}")
    if not docs:
        lines.append("- 사업자등록증, 최근 매출 증빙, 신용조회 동의서 등 (상담 시 안내)")

    lines.extend([
        "",
        "## 신청 순서 (일반 안내)",
        "1. 추가 확인 사항 회신",
        "2. 필요 서류 준비",
        "3. 해당 기관 상담·신청 (온라인 또는 방문)",
        "4. 심사 결과 안내 후 후속 절차 진행",
        "",
        "## 문의 기관",
    ])
    institutions = list({r.institution for r in reviewable})
    for inst in institutions[:4]:
        lines.append(f"- {inst}")
    if not institutions:
        lines.append("- 소상공인시장진흥공단, 지역신용보증재단 등 관할 기관")

    lines.extend([
        "",
        "## 다시 검토할 시점",
        "- 추가 정보 확인 후 상담자가 재검토",
        "- 업력·매출 등 시간이 지나 조건이 바뀌면 재상담 가능",
        "",
        "## 주의사항",
        f"- {DOCUMENT_DISCLAIMER}",
        "- 본 안내는 상담 참고용이며, 최종 가능 여부는 기관 심사와 공식 공고 기준으로 결정됩니다.",
    ])

    template_text = "\n".join(lines)
    if tone == "문자 발송형":
        template_text = template_text.replace("## ", "").replace("**", "")

    return _enhance_customer_guide_with_llm(
        template_text, case, eligibility_results, missing_info, next_questions, tone,
    )
