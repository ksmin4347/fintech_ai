"""Shared structured profile progress calculation."""

from __future__ import annotations

from typing import Any

from models.schemas import BusinessCase
from services.status_mapper import is_verified_field_status


STRUCTURED_PROFILE_FIELDS: list[tuple[str, str]] = [
    ("industry", "업종"),
    ("region", "사업장 지역"),
    ("business_type", "사업자 형태"),
    ("business_months", "업력"),
    ("annual_revenue", "연매출"),
    ("revenue_trend", "매출 상황"),
    ("funding_purpose", "자금 용도"),
    ("required_amount", "필요 자금"),
    ("existing_loan", "기존 대출"),
    ("existing_guarantee", "기존 보증"),
    ("credit_band", "신용구간"),
    ("tax_arrears", "세금 체납"),
    ("business_status", "사업 상태"),
]


def _has_structured_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip() not in {"미확인", "확인 중"}
    return True


def _field_confirmed(case: BusinessCase, field: str) -> bool:
    return _has_structured_value(getattr(case, field, None)) and is_verified_field_status(
        (case.field_status or {}).get(field)
    )


def structured_profile_progress(case: BusinessCase) -> dict[str, int | list[dict[str, Any]]]:
    """Return progress based on the 13 structured profile fields shown in the app."""
    rows: list[dict[str, Any]] = []
    confirmed = 0
    partially_filled = 0

    for field, label in STRUCTURED_PROFILE_FIELDS:
        is_confirmed = _field_confirmed(case, field)
        is_partial = _has_structured_value(getattr(case, field, None))
        if is_confirmed:
            confirmed += 1
        elif is_partial:
            partially_filled += 1
        rows.append(
            {
                "id": field,
                "label": label,
                "fields": (field,),
                "confirmed": is_confirmed,
                "partial": is_partial and not is_confirmed,
            }
        )

    total = len(STRUCTURED_PROFILE_FIELDS)
    percent = round((confirmed / total) * 100) if total else 0
    needs_review = total - confirmed
    return {
        "total": total,
        "confirmed": confirmed,
        "needs_review": needs_review,
        "partial": partially_filled,
        "percent": max(0, min(100, percent)),
        "rows": rows,
    }
