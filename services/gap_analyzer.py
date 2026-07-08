"""Gap analysis for eligibility results."""

from __future__ import annotations

from models.schemas import BusinessCase, EligibilityResult, PolicyProduct


def analyze_gaps(
    case: BusinessCase,
    results: list[EligibilityResult],
    policies: list[PolicyProduct],
) -> list[dict]:
    """Analyze qualification gaps for conditional/excluded policies."""
    policy_map = {p.policy_id: p for p in policies}
    gaps: list[dict] = []

    for result in results:
        if result.final_status not in ("제외 가능성", "조건부 검토"):
            continue

        policy = policy_map.get(result.policy_id)
        gap_items = []
        recoverable = []
        review_timing = []

        for cond in result.condition_results:
            if cond.result == "미충족":
                item = {
                    "condition": cond.condition_name,
                    "gap": cond.reason,
                    "customer_value": cond.customer_value,
                    "policy_requirement": cond.policy_requirement,
                }
                gap_items.append(item)

                if cond.condition_name == "업력" and case.business_months and policy and policy.min_business_months:
                    remaining = policy.min_business_months - case.business_months
                    if remaining > 0:
                        recoverable.append(f"약 {remaining}개월 후 업력 조건 재검토 가능")
                        review_timing.append(f"{remaining}개월 후")

            elif cond.result in ("미확인", "추가 확인 필요"):
                gap_items.append({
                    "condition": cond.condition_name,
                    "gap": "정보 미확인",
                    "customer_value": cond.customer_value,
                    "policy_requirement": cond.policy_requirement,
                })

        alternatives = [
            r.policy_name
            for r in results
            if r.final_status in ("검토 가능", "조건부 검토")
            and r.policy_id != result.policy_id
        ][:3]

        gaps.append({
            "policy_name": result.policy_name,
            "institution": result.institution,
            "status": result.final_status,
            "gap_items": gap_items,
            "why_difficult": result.summary_reason,
            "recoverable": recoverable,
            "review_timing": review_timing,
            "alternatives": alternatives,
            "next_actions": result.next_actions,
            "contact": result.institution,
        })

    return gaps


def generate_gap_summary(gaps: list[dict]) -> str:
    if not gaps:
        return "현재 검토 결과, 주요 자격격차가 확인된 상품이 없거나 추가 정보 확인이 우선 필요합니다."

    lines = []
    for gap in gaps:
        lines.append(f"### {gap['policy_name']} ({gap['status']})")
        lines.append(f"- 검토 어려운 이유: {gap['why_difficult']}")
        for item in gap["gap_items"]:
            lines.append(f"  - {item['condition']}: {item['gap']} (고객: {item['customer_value']} / 기준: {item['policy_requirement']})")
        if gap["recoverable"]:
            lines.append(f"- 시간 경과 후 충족 가능: {', '.join(gap['recoverable'])}")
        if gap["alternatives"]:
            lines.append(f"- 대체 검토 상품: {', '.join(gap['alternatives'])}")
        lines.append(f"- 문의 기관: {gap['contact']}")
        lines.append("")
    return "\n".join(lines)
