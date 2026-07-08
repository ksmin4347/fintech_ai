"""Display status mapping aligned with the business plan."""

from __future__ import annotations

PUBLIC_STATUS_CONFIRMED = "확인 완료"
PUBLIC_STATUS_NEEDS_INFO = "추가 확인 필요"
PUBLIC_STATUS_MISMATCH = "공개조건 불일치"

PUBLIC_STATUSES = [
    PUBLIC_STATUS_CONFIRMED,
    PUBLIC_STATUS_NEEDS_INFO,
    PUBLIC_STATUS_MISMATCH,
]

PUBLIC_STATUS_ICONS = {
    PUBLIC_STATUS_CONFIRMED: "✅",
    PUBLIC_STATUS_NEEDS_INFO: "🟡",
    PUBLIC_STATUS_MISMATCH: "⚠️",
}

VERIFIED_FIELD_STATUSES = {"확인됨", "상담사 확인", "서류 확인", "기관 확인"}
UNCERTAIN_FIELD_STATUSES = {"미확인", "추가 확인 필요"}


def map_policy_status(status: str) -> str:
    """Map internal eligibility labels to the four public consultation states."""
    return {
        "검토 가능": PUBLIC_STATUS_CONFIRMED,
        "조건부 검토": PUBLIC_STATUS_NEEDS_INFO,
        "제외 가능성": PUBLIC_STATUS_MISMATCH,
        "판단 보류": PUBLIC_STATUS_NEEDS_INFO,
    }.get(status, PUBLIC_STATUS_NEEDS_INFO)


def map_condition_status(status: str) -> str:
    """Map condition-level rule results to the four public consultation states."""
    return {
        "충족": PUBLIC_STATUS_CONFIRMED,
        "해당 없음": PUBLIC_STATUS_CONFIRMED,
        "미확인": PUBLIC_STATUS_NEEDS_INFO,
        "추가 확인 필요": PUBLIC_STATUS_NEEDS_INFO,
        "미충족": PUBLIC_STATUS_MISMATCH,
        "판단 보류": PUBLIC_STATUS_NEEDS_INFO,
    }.get(status, PUBLIC_STATUS_NEEDS_INFO)


def public_status_icon(status: str) -> str:
    return PUBLIC_STATUS_ICONS.get(status, "")


def is_verified_field_status(status: str | None) -> bool:
    return (status or "") in VERIFIED_FIELD_STATUSES
