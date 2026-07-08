"""Explain why a policy is or is not a good consultation candidate."""

from __future__ import annotations

from models.rag_schemas import CuratedPolicyRecommendation
from models.schemas import EligibilityResult
from services.status_mapper import map_policy_status


def _dedupe(items: list[str], limit: int = 6) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def build_eligibility_rationale(result: EligibilityResult) -> dict[str, list[str] | str]:
    positive: list[str] = []
    negative: list[str] = []
    uncertain: list[str] = []

    for condition in result.condition_results:
        label = condition.condition_name
        reason = condition.reason
        detail = f"{label}: {reason}"
        if condition.result == "충족":
            positive.append(detail)
        elif condition.result == "미충족":
            negative.append(detail)
        elif condition.result in ("미확인", "추가 확인 필요", "판단 보류"):
            uncertain.append(detail)

    for reason in result.exclusion_reasons:
        negative.append(reason)
    for field in result.missing_fields:
        uncertain.append(f"{field} 확인 필요")

    if not positive:
        positive.append("현재 확인된 정보만으로는 명확한 추천 근거가 부족합니다.")
    if not negative:
        negative.append("현재 확인된 공개조건 기준 명확한 비추천 사유는 없습니다.")
    if not uncertain:
        uncertain.append("추가 확인 필요 항목이 없습니다.")

    return {
        "display_status": map_policy_status(result.final_status),
        "recommend_reasons": _dedupe(positive),
        "caution_reasons": _dedupe(negative),
        "missing_reasons": _dedupe(uncertain),
    }


def build_recommendation_rationale(rec: CuratedPolicyRecommendation) -> dict[str, list[str] | str]:
    positive: list[str] = []
    negative: list[str] = []
    uncertain: list[str] = []

    positive.extend(rec.why_recommended or [])
    positive.extend([f"조건 일치: {item}" for item in rec.matched_conditions or []])
    if rec.evidence:
        positive.append(f"정책 문서 근거 {len(rec.evidence)}건 검색됨")

    negative.extend(rec.exclusion_risks or [])
    uncertain.extend([f"{item} 확인 필요" for item in rec.missing_or_uncertain_conditions or []])

    if not positive:
        positive.append("상담 케이스와 정책 문서의 기본 연관성으로 후보에 포함되었습니다.")
    if not negative:
        negative.append("현재 확인된 공개조건 기준 명확한 비추천 사유는 없습니다.")
    if not uncertain:
        uncertain.append("추가 확인 필요 항목이 없습니다.")

    return {
        "display_status": map_policy_status(rec.review_status),
        "recommend_reasons": _dedupe(positive),
        "caution_reasons": _dedupe(negative),
        "missing_reasons": _dedupe(uncertain),
    }
