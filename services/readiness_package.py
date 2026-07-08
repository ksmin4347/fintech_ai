"""Build the application readiness package described in the business plan."""

from __future__ import annotations

from datetime import date

from models.rag_schemas import CuratedPolicyRecommendation
from models.readiness_schemas import (
    ProfileEvidenceItem,
    ReadinessPackage,
    RuleComparisonItem,
)
from models.report_schemas import AftercareTask, RequiredDocumentItem
from models.schemas import BusinessCase, EligibilityResult
from services.status_mapper import (
    PUBLIC_STATUS_CONFIRMED,
    PUBLIC_STATUS_MISMATCH,
    PUBLIC_STATUS_NEEDS_INFO,
    map_condition_status,
    map_policy_status,
)
from services.policy_scoring import score_policy_results
from utils.constants import DOCUMENT_DISCLAIMER, FIELD_BASIS_PERIOD, REQUIRED_FIELDS
from utils.formatters import format_amount, format_months
from utils.helpers import get_attr_or_key


KEY_PROFILE_FIELD_ORDER = [
    "region",
    "business_type",
    "industry",
    "business_months",
    "funding_purpose",
    "required_amount",
    "annual_revenue",
    "credit_band",
    "existing_guarantee",
    "tax_arrears",
    "business_status",
]


def _field_display_value(case: BusinessCase, field: str) -> str:
    val = getattr(case, field, None)
    if val is None or val == "":
        return "미확인"
    if field in ("annual_revenue", "required_amount", "monthly_revenue"):
        return format_amount(val)
    if field == "business_months":
        return format_months(val)
    return str(val)


def _information_source(case: BusinessCase, field: str) -> str:
    recorded_source = (case.field_source or {}).get(field)
    if recorded_source:
        return recorded_source
    status = (case.field_status or {}).get(field, "")
    evidence = (case.field_evidence or {}).get(field, "")
    if status == "서류 확인":
        return "제출서류"
    if status == "기관 확인":
        return "기관 조회"
    if evidence:
        return "고객 진술/상담 원문"
    if getattr(case, field, None) not in (None, ""):
        return "상담자 직접 입력"
    return "미확인"


def _profile_next_action(case: BusinessCase, field: str, label: str) -> str:
    val = getattr(case, field, None)
    status = (case.field_status or {}).get(field, "미확인")
    if val in (None, ""):
        return f"{label} 추가 질문"
    if status in ("미확인", "추가 확인 필요"):
        return f"{label} 근거 확인"
    if status == "확인됨":
        return "상담사 확인 완료"
    return f"{status} 완료"


def build_profile_items(case: BusinessCase) -> list[ProfileEvidenceItem]:
    items: list[ProfileEvidenceItem] = []
    for field, label, _, _ in REQUIRED_FIELDS:
        status = (case.field_status or {}).get(field, "미확인")
        items.append(
            ProfileEvidenceItem(
                field_name=field,
                field_label=label,
                value=_field_display_value(case, field),
                information_source=_information_source(case, field),
                verification_status=status,
                basis_period=(case.field_basis_period or {}).get(field) or FIELD_BASIS_PERIOD.get(field),
                evidence=(case.field_evidence or {}).get(field, ""),
                evidence_location=(case.field_evidence_location or {}).get(field, ""),
                updated_by=(case.field_updated_by or {}).get(field, ""),
                approved_by=(case.field_approved_by or {}).get(field, ""),
                next_action=_profile_next_action(case, field, label),
            )
        )
    return items


def build_rule_comparisons(results: list[EligibilityResult]) -> list[RuleComparisonItem]:
    rows: list[RuleComparisonItem] = []
    for result in results:
        source = result.source or {}
        for condition in result.condition_results:
            rows.append(
                RuleComparisonItem(
                    policy_id=result.policy_id,
                    policy_name=result.policy_name,
                    institution=result.institution,
                    condition_name=condition.condition_name,
                    public_status=map_condition_status(condition.result),
                    customer_value=condition.customer_value,
                    public_requirement=condition.policy_requirement,
                    reason=condition.reason,
                    evidence=condition.evidence,
                    source_name=source.get("source_name", ""),
                    source_url=source.get("source_url", ""),
                    source_date=source.get("source_date", ""),
                )
            )
    return rows


def _package_status(results: list[EligibilityResult], missing_info: list) -> str:
    policy_statuses = [map_policy_status(r.final_status) for r in results]
    if missing_info or PUBLIC_STATUS_NEEDS_INFO in policy_statuses:
        return PUBLIC_STATUS_NEEDS_INFO
    if PUBLIC_STATUS_CONFIRMED in policy_statuses:
        return PUBLIC_STATUS_CONFIRMED
    if PUBLIC_STATUS_MISMATCH in policy_statuses:
        return PUBLIC_STATUS_MISMATCH
    return PUBLIC_STATUS_NEEDS_INFO


def _normalized_name(value: str) -> str:
    return (value or "").replace("[데모]", "").replace(" ", "").strip().lower()


def _matches_recommendation(result: EligibilityResult, recommendation: CuratedPolicyRecommendation) -> bool:
    result_name = _normalized_name(result.policy_name)
    rec_name = _normalized_name(get_attr_or_key(recommendation, "policy_name"))
    if not result_name or not rec_name:
        return False
    if result_name in rec_name or rec_name in result_name:
        return True
    result_inst = _normalized_name(result.institution)
    rec_inst = _normalized_name(get_attr_or_key(recommendation, "institution"))
    return bool(
        result_inst
        and rec_inst
        and result_inst == rec_inst
        and (result_name[:8] in rec_name or rec_name[:8] in result_name)
    )


def _focused_results(
    eligibility_results: list[EligibilityResult],
    recommendations: list[CuratedPolicyRecommendation],
    limit: int = 5,
) -> list[EligibilityResult]:
    """Pick the policies a counselor is likely to act on in this package."""
    if not eligibility_results:
        return []

    scored = score_policy_results(eligibility_results)
    focused: list[EligibilityResult] = []
    seen: set[str] = set()

    for recommendation in recommendations or []:
        for result in eligibility_results:
            if result.policy_id in seen:
                continue
            if _matches_recommendation(result, recommendation):
                focused.append(result)
                seen.add(result.policy_id)
                break

    actionable = [
        result
        for result in eligibility_results
        if map_policy_status(result.final_status) in (PUBLIC_STATUS_CONFIRMED, PUBLIC_STATUS_NEEDS_INFO)
    ]
    actionable.sort(key=lambda result: scored.get(result.policy_id, {}).get("score", 0), reverse=True)
    for result in actionable:
        if result.policy_id not in seen:
            focused.append(result)
            seen.add(result.policy_id)
        if len(focused) >= limit:
            return focused[:limit]

    if focused:
        return focused[:limit]

    fallback = sorted(
        eligibility_results,
        key=lambda result: scored.get(result.policy_id, {}).get("score", 0),
        reverse=True,
    )
    return fallback[:limit]


def _status_reason(status: str, focused_results: list[EligibilityResult], missing_labels: list[str]) -> str:
    count = len(focused_results)
    if status == PUBLIC_STATUS_CONFIRMED:
        return f"검토 후보 {count}건의 공개조건이 현재 입력값 기준으로 확인 완료 상태입니다."
    if status == PUBLIC_STATUS_NEEDS_INFO:
        if missing_labels:
            return f"검토 후보 {count}건 중 보완할 상담 정보 {len(missing_labels)}건이 있어 신청 전 추가 확인이 필요합니다."
        return f"검토 후보 {count}건 중 일부 조건이 미확인 또는 추가 확인 상태입니다."
    return "현재 입력값으로는 행동 가능한 후보보다 공개조건 불일치 후보가 우선 확인됩니다."


def _condition_followups(result: EligibilityResult, limit: int = 3) -> list[str]:
    followups: list[str] = []
    for condition in result.condition_results:
        public_status = map_condition_status(condition.result)
        if public_status == PUBLIC_STATUS_CONFIRMED:
            continue
        action = f"{result.policy_name}: {condition.condition_name} 확인"
        if condition.reason:
            action += f" ({condition.reason})"
        followups.append(action)
        if len(followups) >= limit:
            break
    return followups


def _markdown_cell(value: object) -> str:
    text = str(value or "").replace("\n", " ").replace("|", "/").strip()
    return text or "-"


def _profile_rows_for_markdown(items: list[ProfileEvidenceItem]) -> list[ProfileEvidenceItem]:
    by_field = {item.field_name: item for item in items}
    selected: list[ProfileEvidenceItem] = []
    seen: set[str] = set()
    for field in KEY_PROFILE_FIELD_ORDER:
        item = by_field.get(field)
        if item:
            selected.append(item)
            seen.add(field)
    for item in items:
        if item.field_name in seen:
            continue
        if item.verification_status in ("미확인", "추가 확인 필요"):
            selected.append(item)
    return selected[:12]


def _compact_rule_rows(rule_comparisons: list[RuleComparisonItem]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for row in rule_comparisons:
        key = row.policy_id or row.policy_name
        if key not in grouped:
            grouped[key] = {
                "policy_name": row.policy_name,
                "institution": row.institution,
                PUBLIC_STATUS_CONFIRMED: 0,
                PUBLIC_STATUS_NEEDS_INFO: 0,
                PUBLIC_STATUS_MISMATCH: 0,
                "followups": [],
            }
            order.append(key)
        grouped[key][row.public_status] = int(grouped[key].get(row.public_status, 0)) + 1
        if row.public_status != PUBLIC_STATUS_CONFIRMED and len(grouped[key]["followups"]) < 3:
            grouped[key]["followups"].append(f"{row.condition_name}: {row.reason or row.public_requirement}")
    return [grouped[key] for key in order]


def _missing_labels(missing_info: list) -> list[str]:
    labels = []
    for item in missing_info or []:
        label = get_attr_or_key(item, "field_label")
        reason = get_attr_or_key(item, "reason")
        if label and reason:
            labels.append(f"{label}: {reason}")
        elif label:
            labels.append(str(label))
    return labels


def _question_lines(next_questions: list) -> list[str]:
    lines = []
    for q in next_questions or []:
        question = get_attr_or_key(q, "question")
        reason = get_attr_or_key(q, "reason")
        priority = get_attr_or_key(q, "priority")
        if question:
            suffix = f" ({priority}, {reason})" if reason else ""
            lines.append(f"{question}{suffix}")
    return lines


def _source_warnings(results: list[EligibilityResult]) -> list[str]:
    warnings: list[str] = []
    if any((r.source or {}).get("is_sample_data") == "True" for r in results):
        warnings.append("현재 정책 데이터는 데모 샘플입니다. 실제 적용 전 공식 공고로 교체해야 합니다.")
    stale_sources = [r.policy_name for r in results if not (r.source or {}).get("source_url")]
    if stale_sources:
        warnings.append("일부 제도에 공식 출처 URL이 없습니다: " + ", ".join(stale_sources[:3]))
    return warnings


def build_readiness_package(
    case: BusinessCase,
    eligibility_results: list[EligibilityResult],
    recommendations: list[CuratedPolicyRecommendation],
    missing_info: list,
    next_questions: list,
    required_documents: list[RequiredDocumentItem],
    aftercare_tasks: list[AftercareTask],
) -> ReadinessPackage:
    eligibility_results = eligibility_results or []
    recommendations = recommendations or []
    missing_info = missing_info or []
    next_questions = next_questions or []
    required_documents = required_documents or []
    aftercare_tasks = aftercare_tasks or []

    profile_items = build_profile_items(case)
    focused_results = _focused_results(eligibility_results, recommendations, limit=5)
    rule_comparisons = build_rule_comparisons(focused_results)
    missing_labels = _missing_labels(missing_info)
    status = _package_status(focused_results, missing_info)
    top_recs = recommendations[:3]
    focused_names = [result.policy_name for result in focused_results[:3]]
    rec_summary = ", ".join(r.policy_name for r in top_recs) if top_recs else ", ".join(focused_names) or "검토 후보 없음"

    next_actions = []
    for q in _question_lines(next_questions)[:4]:
        next_actions.append(f"추가 질문: {q}")
    for result in focused_results[:3]:
        next_actions.extend(_condition_followups(result, limit=2))
    for doc in required_documents[:4]:
        next_actions.append(f"서류 준비: {doc.document_name}")
    next_actions.append("담당자가 공식 공고, 신청기간, 제출서류를 최종 확인")
    next_actions = list(dict.fromkeys(next_actions))

    today = case.consultation_date or date.today()
    reason = _status_reason(status, focused_results, missing_labels)
    summary = (
        f"{today} 기준 신청 준비 상태는 '{status}'입니다. "
        f"{reason} 주요 검토 제도는 {rec_summary}입니다."
    )

    return ReadinessPackage(
        case_id=case.case_id,
        customer_name=case.customer_name,
        business_name=case.business_name,
        package_status=status,
        readiness_summary=summary,
        profile_items=profile_items,
        rule_comparisons=rule_comparisons,
        missing_information=missing_labels,
        next_questions=_question_lines(next_questions),
        required_documents=required_documents,
        next_actions=next_actions,
        aftercare_tasks=aftercare_tasks,
        source_warnings=_source_warnings(focused_results),
        compliance_notes=[
            "AI는 승인·거절·개인별 한도·금리 판단을 하지 않습니다.",
            "공개조건 비교 결과는 상담 준비용이며 담당자가 확인해야 합니다.",
            DOCUMENT_DISCLAIMER,
        ],
    )


def render_readiness_package_markdown(package: ReadinessPackage) -> str:
    lines = [
        f"# {package.package_title}",
        "",
        f"**케이스 ID:** {package.case_id}",
        f"**고객:** {package.customer_name or '미입력'} / **사업체:** {package.business_name or '미입력'}",
        f"**신청 준비 상태:** {package.package_status}",
        "",
        "## 요약",
        package.readiness_summary,
        "",
        "## 상담 프로필 요약",
        "| 항목 | 값 | 확인상태 | 다음 행동 |",
        "|---|---|---|---|",
    ]
    for item in _profile_rows_for_markdown(package.profile_items):
        lines.append(
            "| "
            f"{_markdown_cell(item.field_label)} | {_markdown_cell(item.value)} | "
            f"{_markdown_cell(item.verification_status)} | {_markdown_cell(item.next_action)} |"
        )

    lines.extend(["", "## 공개규칙 비교 요약"])
    lines.append("| 제도 | 기관 | 확인 완료 | 추가 확인 | 불일치 | 핵심 확인사항 |")
    lines.append("|---|---|---:|---:|---:|---|")
    for row in _compact_rule_rows(package.rule_comparisons):
        followups = "; ".join(row["followups"]) if row["followups"] else "핵심 공개조건 확인 완료"
        lines.append(
            "| "
            f"{_markdown_cell(row['policy_name'])} | {_markdown_cell(row['institution'])} | "
            f"{row[PUBLIC_STATUS_CONFIRMED]} | {row[PUBLIC_STATUS_NEEDS_INFO]} | "
            f"{row[PUBLIC_STATUS_MISMATCH]} | {_markdown_cell(followups)} |"
        )

    if package.missing_information:
        lines.extend(["", "## 미확인 정보"])
    for item in package.missing_information[:8]:
        lines.append(f"- {item}")

    if package.next_questions:
        lines.extend(["", "## 다음 질문"])
    for question in package.next_questions[:6]:
        lines.append(f"- {question}")

    if package.required_documents:
        lines.extend(["", "## 필요서류"])
        lines.append("| 서류 | 우선순위 | 관련 제도 | 준비 방법 |")
        lines.append("|---|---|---|---|")
    for doc in package.required_documents[:8]:
        lines.append(
            "| "
            f"{_markdown_cell(doc.document_name)} | {_markdown_cell(doc.priority)} | "
            f"{_markdown_cell(doc.required_for)} | {_markdown_cell(doc.how_to_prepare or doc.reason)} |"
        )

    lines.extend(["", "## 다음 행동"])
    for i, action in enumerate(package.next_actions[:10], start=1):
        lines.append(f"{i}. {action}")

    if package.aftercare_tasks:
        lines.extend(["", "## 애프터케어"])
        lines.append("| 담당 | 작업 | 기한 | 이유 |")
        lines.append("|---|---|---|---|")
    for task in package.aftercare_tasks[:6]:
        lines.append(
            "| "
            f"{_markdown_cell(task.owner)} | {_markdown_cell(task.task_name)} | "
            f"{_markdown_cell(task.due_date or '기한 미정')} | {_markdown_cell(task.reason)} |"
        )

    if package.source_warnings:
        lines.extend(["", "## 출처 및 데이터 경고"])
        for warning in package.source_warnings:
            lines.append(f"- {warning}")

    lines.extend(["", "## 상담자 확인 필요사항"])
    for note in package.compliance_notes:
        lines.append(f"- {note}")
    return "\n".join(lines)
