"""Transparent consultation-priority scoring for policy matches."""

from __future__ import annotations

from models.schemas import EligibilityResult


CONDITION_WEIGHTS = {
    "지역": 1.25,
    "사업자 형태": 1.25,
    "업종": 1.15,
    "업력": 1.10,
    "자금용도": 1.10,
    "신청기간": 1.10,
    "사업상태": 1.10,
    "세금 체납": 1.05,
    "연매출": 1.00,
    "신용": 1.00,
    "중복지원": 1.00,
}

RESULT_POINTS = {
    "충족": 1.0,
    "해당 없음": 1.0,
    "추가 확인 필요": 0.58,
    "미확인": 0.45,
    "판단 보류": 0.40,
    "미충족": 0.0,
}


def _weight(condition_name: str) -> float:
    return CONDITION_WEIGHTS.get(condition_name, 1.0)


def score_policy_fit(result: EligibilityResult) -> dict:
    """Return an explainable priority score.

    This is not an approval probability. It ranks consultation follow-up by public
    eligibility criteria, using only rule comparison results that are already
    shown to the user.
    """
    total_weight = 0.0
    earned_weight = 0.0
    confirmed = 0
    needs_info = 0
    mismatches = 0

    strong_reasons: list[str] = []
    review_reasons: list[str] = []
    mismatch_reasons: list[str] = []

    for condition in result.condition_results:
        weight = _weight(condition.condition_name)
        total_weight += weight
        earned_weight += weight * RESULT_POINTS.get(condition.result, 0.4)

        if condition.result in ("충족", "해당 없음"):
            confirmed += 1
            if condition.result == "충족":
                strong_reasons.append(f"{condition.condition_name}: {condition.reason}")
        elif condition.result in ("미확인", "추가 확인 필요", "판단 보류"):
            needs_info += 1
            review_reasons.append(f"{condition.condition_name}: {condition.reason}")
        elif condition.result == "미충족":
            mismatches += 1
            mismatch_reasons.append(f"{condition.condition_name}: {condition.reason}")

    raw_score = round((earned_weight / total_weight) * 100) if total_weight else 0
    if mismatches:
        score = min(raw_score, max(35, 64 - (mismatches - 1) * 8))
    elif needs_info:
        score = min(raw_score, 88)
    else:
        score = raw_score

    if mismatches:
        grade = "공개조건 불일치 우선 확인"
    elif needs_info:
        grade = "추가 확인 후 검토"
    elif score >= 85:
        grade = "우선 검토"
    else:
        grade = "보통 검토"

    return {
        "score": int(max(0, min(100, score))),
        "raw_score": int(max(0, min(100, raw_score))),
        "grade": grade,
        "confirmed_count": confirmed,
        "needs_info_count": needs_info,
        "mismatch_count": mismatches,
        "strong_reasons": strong_reasons[:4],
        "review_reasons": review_reasons[:4],
        "mismatch_reasons": mismatch_reasons[:4],
        "method": (
            "공개조건 비교 결과에 조건별 가중치를 적용하고, 미확인 항목은 부분점수로, "
            "공개조건 불일치는 점수 상한을 낮추는 방식입니다."
        ),
    }


def score_policy_results(results: list[EligibilityResult]) -> dict[str, dict]:
    return {result.policy_id: score_policy_fit(result) for result in results}
