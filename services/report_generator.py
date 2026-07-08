"""Review report generator."""

from __future__ import annotations

import json

from models.rag_schemas import CuratedPolicyRecommendation
from models.report_schemas import AftercareTask, RequiredDocumentItem, ReviewReport
from models.schemas import BusinessCase, EligibilityResult
from services.aftercare_manager import generate_aftercare_tasks
from services.checklist_generator import generate_required_document_checklist
from services.llm_client import LLMClient
from services.status_mapper import (
    PUBLIC_STATUS_CONFIRMED,
    PUBLIC_STATUS_MISMATCH,
    PUBLIC_STATUS_NEEDS_INFO,
    is_verified_field_status,
    map_policy_status,
)
from utils.constants import CAUTION_MESSAGE
from utils.formatters import format_amount, format_months
from utils.helpers import ensure_missing_info_items, ensure_next_questions, get_attr_or_key

TEMPLATE_TITLES = {
    "basic_consultation": "소상공인 금융상담 기록",
    "rm_review": "RM 심사 추천서 (초안)",
    "handover_memo": "기관 인계 메모 (초안)",
}


def _case_payload(case: BusinessCase) -> dict:
    return {
        "customer_name": case.customer_name,
        "business_name": case.business_name,
        "industry": case.industry,
        "region": case.region,
        "business_type": case.business_type,
        "business_months": case.business_months,
        "annual_revenue": case.annual_revenue,
        "revenue_trend": case.revenue_trend,
        "funding_purpose": case.funding_purpose,
        "required_amount": case.required_amount,
        "existing_loan": case.existing_loan,
        "existing_guarantee": case.existing_guarantee,
        "credit_band": case.credit_band,
        "tax_arrears": case.tax_arrears,
        "business_status": case.business_status,
        "field_status": case.field_status,
        "field_evidence": case.field_evidence,
        "field_source": case.field_source,
        "field_basis_period": case.field_basis_period,
        "field_evidence_location": case.field_evidence_location,
    }


def _enhance_report_with_llm(
    report: ReviewReport,
    case: BusinessCase,
    eligibility_results: list[EligibilityResult],
    missing_info: list,
    next_questions: list,
) -> ReviewReport:
    client = LLMClient()
    if not client.is_available():
        return report

    system_prompt = (
        "너는 정책금융 초기상담 보고서 초안을 작성하는 보조자다. "
        "입력된 구조화 정보와 규칙 비교 결과만 사용한다. "
        "승인 가능, 대출 확정, 보증 확정, 개인별 한도, 금리 확정 표현은 절대 쓰지 않는다. "
        "상담자가 검토하기 쉬운 간결한 문장으로 작성한다."
    )
    payload = {
        "case": _case_payload(case),
        "eligibility_results": [
            {
                "policy_name": r.policy_name,
                "institution": r.institution,
                "status": map_policy_status(r.final_status),
                "summary_reason": r.summary_reason,
                "missing_fields": r.missing_fields,
                "exclusion_reasons": r.exclusion_reasons,
            }
            for r in eligibility_results[:6]
        ],
        "missing_info": [get_attr_or_key(m, "field_label") for m in missing_info],
        "next_questions": [get_attr_or_key(q, "question") for q in next_questions[:8]],
        "current_report": report.model_dump(mode="json"),
    }
    user_prompt = (
        "아래 데이터를 바탕으로 보고서의 문장형 필드만 개선해라. "
        "JSON 키는 counselor_summary, business_overview, funding_needs, next_actions만 반환해라. "
        "next_actions는 문자열 배열이며 10개 이하로 작성해라.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
    data = client.generate_json(system_prompt, user_prompt, "review_report_text")
    updates = {}
    for key in ("counselor_summary", "business_overview", "funding_needs"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            updates[key] = value.strip()
    actions = data.get("next_actions")
    if isinstance(actions, list):
        cleaned = [str(a).strip() for a in actions if str(a).strip()]
        if cleaned:
            updates["next_actions"] = cleaned[:10]
    return report.model_copy(update=updates) if updates else report


def _verified_fields(case: BusinessCase) -> list[str]:
    items = []
    for field, status in (case.field_status or {}).items():
        if is_verified_field_status(status):
            val = getattr(case, field, None)
            if val:
                items.append(f"{field}: {val} ({status})")
    return items


def _missing_labels(missing_info: list) -> list[str]:
    return [get_attr_or_key(m, "field_label") for m in missing_info if get_attr_or_key(m, "field_label")]


def generate_review_report(
    case: BusinessCase,
    eligibility_results: list[EligibilityResult],
    recommendations: list[CuratedPolicyRecommendation],
    missing_info: list,
    next_questions: list,
    template_type: str = "rm_review",
    gap_analysis: list | None = None,
) -> ReviewReport:
    recommended = [r.policy_name for r in recommendations if map_policy_status(r.review_status) == PUBLIC_STATUS_CONFIRMED]
    conditional = [r.policy_name for r in recommendations if map_policy_status(r.review_status) == PUBLIC_STATUS_NEEDS_INFO]
    excluded = [r.policy_name for r in recommendations if map_policy_status(r.review_status) == PUBLIC_STATUS_MISMATCH]
    exclusion_risks = []
    for r in recommendations:
        exclusion_risks.extend([f"{r.policy_name}: {e}" for e in r.exclusion_risks])

    missing_items = ensure_missing_info_items(missing_info)
    question_items = ensure_next_questions(next_questions)

    checklist = generate_required_document_checklist(case, recommendations, eligibility_results)
    aftercare = generate_aftercare_tasks(case, recommendations, missing_items, gap_analysis)

    verified = _verified_fields(case)
    missing = _missing_labels(missing_items)
    next_actions = []
    for r in recommendations:
        next_actions.extend(r.next_actions)
    for q in question_items[:5]:
        qtext = get_attr_or_key(q, "question")
        if qtext:
            next_actions.append(f"추가 질문: {qtext}")
    next_actions = list(dict.fromkeys(next_actions))[:10]

    overview = (
        f"업종 {case.industry or '미확인'}, 지역 {case.region or '미확인'}, "
        f"업력 {format_months(case.business_months)}, 연매출 {format_amount(case.annual_revenue)}"
    )
    funding = (
        f"자금용도: {case.funding_purpose or '미확인'}, "
        f"필요규모: {format_amount(case.required_amount)}, "
        f"매출추이: {case.revenue_trend or '미확인'}"
    )

    if template_type == "basic_consultation":
        summary = (
            f"{case.customer_name or '고객'}({case.business_name or '사업체'}) 상담 기록입니다. "
            f"현재 확인 완료 제도 {len(recommended)}건, 추가 확인 필요 제도 {len(conditional)}건입니다."
        )
    elif template_type == "handover_memo":
        summary = (
            f"기관 인계를 위한 요약입니다. {case.business_name or '사업체'}의 "
            f"{case.funding_purpose or '자금 수요'} 상담 건이며, 추가 확인 항목과 필요서류 중심으로 전달합니다."
        )
    else:
        summary = (
            f"{case.customer_name or '고객'}({case.business_name or '사업체'}) RM 검토 초안입니다. "
            f"확인 완료 {len(recommended)}건, 추가 확인 필요 {len(conditional)}건, 공개조건 불일치 위험 {len(exclusion_risks)}건입니다."
        )

    report = ReviewReport(
        report_title=TEMPLATE_TITLES.get(template_type, "상담 보고서"),
        case_id=case.case_id,
        customer_name=case.customer_name,
        business_name=case.business_name,
        counselor_summary=summary,
        business_overview=overview,
        funding_needs=funding,
        verified_information=verified or ["구조화된 확인 정보 없음"],
        missing_information=missing or ["추가 확인 필요 항목 없음"],
        recommended_policies=recommended or ["해당 없음"],
        conditional_policies=conditional or ["해당 없음"],
        exclusion_risks=exclusion_risks or ["명확한 제외 사유 없음"],
        required_documents=checklist,
        next_actions=next_actions,
        aftercare_tasks=aftercare,
        compliance_notes=[
            "본 보고서는 AI 생성 초안입니다.",
            "상담자가 공식 공고와 제출자료를 확인해야 합니다.",
            "승인·거절·개인별 한도·금리 확정 표현을 사용하지 않습니다.",
        ],
        caution_message=CAUTION_MESSAGE,
    )
    return _enhance_report_with_llm(report, case, eligibility_results, missing_items, question_items)


def render_report_markdown(report: ReviewReport) -> str:
    lines = [
        f"# {report.report_title}",
        "",
        "| 항목 | 내용 |",
        "|---|---|",
        f"| 케이스 ID | {report.case_id} |",
        f"| 고객 | {report.customer_name or '미입력'} |",
        f"| 사업체 | {report.business_name or '미입력'} |",
        "",
        "## 상담 개요",
        report.counselor_summary,
        "",
        "## 사업자·자금 요약",
        "| 구분 | 내용 |",
        "|---|---|",
        f"| 사업자 현황 | {report.business_overview} |",
        f"| 자금 필요 사유 | {report.funding_needs} |",
        "",
        "## 확인된 정보",
    ]
    for v in report.verified_information:
        lines.append(f"- {v}")
    lines.extend(["", "## 미확인 정보"])
    for m in report.missing_information:
        lines.append(f"- {m}")
    lines.extend(["", "## 정책 검토 요약"])
    lines.append("| 구분 | 내용 |")
    lines.append("|---|---|")
    lines.append(f"| 확인 완료 | {', '.join(report.recommended_policies[:6])} |")
    lines.append(f"| 추가 확인 필요 | {', '.join(report.conditional_policies[:6])} |")
    lines.append(f"| 공개조건 불일치 | {', '.join(report.exclusion_risks[:6])} |")

    if "기관 인계" in report.report_title:
        lines.extend(["", "## 기관 인계 포인트"])
        lines.append("- 고객 진술 기반 정보와 추가 확인 필요 정보를 구분해 전달합니다.")
        lines.append("- 기관 확인이 필요한 조건은 다음 행동과 필요서류에서 우선 처리합니다.")
    elif "RM 심사" in report.report_title:
        lines.extend(["", "## RM 검토 포인트"])
        lines.append("- 공개조건 불일치 사유는 제외 가능성으로 분리하고, 미확인 항목은 보완 요청 대상으로 둡니다.")
        lines.append("- 점수와 상태는 상담 우선순위이며 승인 판단이 아닙니다.")

    lines.extend(["", "## 필요 서류"])
    lines.append("| 서류 | 우선순위 | 이유 | 준비 방법 |")
    lines.append("|---|---|---|---|")
    for d in report.required_documents:
        lines.append(f"| {d.document_name} | {d.priority} | {d.reason} | {d.how_to_prepare or '상담 시 안내'} |")
    lines.extend(["", "## 후속 조치"])
    for idx, action in enumerate(report.next_actions, start=1):
        lines.append(f"{idx}. {action}")
    lines.extend(["", "## 애프터 케어 태스크"])
    lines.append("| 담당 | 태스크 | 이유 | 기한 |")
    lines.append("|---|---|---|---|")
    for t in report.aftercare_tasks:
        lines.append(f"| {t.owner} | {t.task_name} | {t.reason} | {t.due_date or '미정'} |")
    lines.extend(["", "## 상담자 확인 필요사항"])
    for n in report.compliance_notes:
        lines.append(f"- {n}")
    lines.extend(["", "## 주의 문구", report.caution_message])
    return "\n".join(lines)
