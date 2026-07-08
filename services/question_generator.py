"""Next best question generator."""

from __future__ import annotations

from models.schemas import BusinessCase, MissingInfoItem, NextQuestion
from utils.constants import REQUIRED_FIELDS


PRIORITY_MAP = {
    "business_status": "높음",
    "tax_arrears": "높음",
    "region": "높음",
    "business_type": "높음",
    "industry": "높음",
    "business_months": "높음",
    "funding_purpose": "높음",
    "required_amount": "중간",
    "annual_revenue": "중간",
    "credit_band": "중간",
    "existing_guarantee": "중간",
    "existing_loan": "낮음",
}

POLICY_RELATED = {
    "region": "지역 기반 보증·정책자금 조건",
    "business_type": "사업자 형태 대상 조건",
    "industry": "업종 허용·제외 조건",
    "business_months": "업력 제한 조건",
    "funding_purpose": "자금용도별 상품 매칭",
    "required_amount": "한도 조건",
    "annual_revenue": "매출 기준 조건",
    "credit_band": "신용 조건",
    "existing_guarantee": "중복지원·보증 제한",
    "existing_loan": "중복지원 제한",
    "tax_arrears": "제외조건(체납)",
    "business_status": "휴폐업 제외조건",
}


def generate_next_questions(
    case: BusinessCase,
    missing_items: list[MissingInfoItem] | None = None,
) -> list[NextQuestion]:
    if missing_items is None:
        from services.missing_info import detect_missing_info
        missing_items = detect_missing_info(case)

    questions: list[NextQuestion] = []
    field_labels = {f[0]: f for f in REQUIRED_FIELDS}

    for item in missing_items:
        field = item.field_name
        priority = PRIORITY_MAP.get(field, "중간")
        related = POLICY_RELATED.get(field, "정책 조건 검토")
        questions.append(
            NextQuestion(
                question=item.sample_question,
                reason=item.reason,
                related_policy=related,
                priority=priority,
            )
        )

    priority_order = {"높음": 0, "중간": 1, "낮음": 2}
    questions.sort(key=lambda q: priority_order.get(q.priority, 1))
    return questions
