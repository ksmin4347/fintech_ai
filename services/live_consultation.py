"""Live consultation transcript helpers."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from services.parser import parse_consultation


PROFILE_FIELDS: list[tuple[str, str]] = [
    ("customer_name", "고객명"),
    ("business_name", "사업체명"),
    ("industry", "업종"),
    ("region", "운영 지역"),
    ("business_type", "사업자 형태"),
    ("business_months", "업력"),
    ("annual_revenue", "연매출"),
    ("monthly_revenue", "월매출"),
    ("revenue_trend", "매출 추세"),
    ("funding_purpose", "자금 용도"),
    ("required_amount", "필요 자금"),
    ("existing_loan", "기존 대출"),
    ("existing_guarantee", "기존 보증"),
    ("credit_score", "신용점수"),
    ("credit_band", "신용구간"),
    ("collateral", "담보"),
    ("tax_arrears", "세금 체납"),
    ("business_status", "사업 상태"),
    ("requested_timeline", "희망 일정"),
]

STRUCTURED_FIELDS = {field for field, _ in PROFILE_FIELDS if field not in {"customer_name", "business_name"}}
UNKNOWN_VALUES = {"", "미확인", "None", "none", "null", "NULL"}
FINANCE_CONTEXT_WORDS = (
    "기존", "은행", "신용", "금리", "이자", "원금", "상환", "대환", "한도", "보증",
    "운영자금", "시설자금", "자금", "빌린", "빌리", "받", "갚", "연체", "차입",
)
SUBMISSION_CONTEXT_WORDS = (
    "서류", "신청서", "사업계획서", "증빙", "자료", "파일", "문서", "양식", "작성",
    "첨부", "업로드", "기관", "접수",
)


def clean_spoken_text(text: str | None) -> str:
    text = (text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def merge_transcript(existing: str | None, incoming: str | None) -> str:
    """Merge speech-recognition output without duplicating repeated final phrases."""
    current = clean_spoken_text(existing)
    new_text = clean_spoken_text(incoming)
    if not new_text:
        return current
    if not current:
        return new_text
    if new_text == current or current.endswith(new_text):
        return current
    if len(new_text) > len(current) and current in new_text:
        return new_text
    tail = current[-max(120, len(new_text) + 20) :]
    if new_text in tail:
        return current
    return f"{current}\n{new_text}"


def _near_context(text: str, start: int, end: int, words: tuple[str, ...], *, radius: int = 18) -> bool:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    window = text[left:right]
    return any(word in window for word in words)


def normalize_finance_transcript_for_analysis(text: str | None) -> tuple[str, list[dict[str, str]]]:
    """
    Keep the displayed transcript intact but correct common speech-recognition slips
    for downstream finance analysis.

    Example: "기존 제출이 있어요" is usually "기존 대출이 있어요" in this product,
    while "서류 제출" must stay as-is.
    """
    source = text or ""
    corrections: list[dict[str, str]] = []
    if not source.strip():
        return "", corrections

    corrected = source
    for match in list(re.finditer(r"제출|재출", source)):
        start, end = match.span()
        if _near_context(source, start, end, SUBMISSION_CONTEXT_WORDS, radius=16):
            continue
        if _near_context(source, start, end, FINANCE_CONTEXT_WORDS, radius=20):
            before = match.group(0)
            corrected = corrected[:start] + "대출" + corrected[end:]
            corrections.append(
                {
                    "원문": before,
                    "보정": "대출",
                    "근거": source[max(0, start - 20): min(len(source), end + 20)].strip(),
                }
            )

    replacements = [
        (r"운영\s+자금", "운영자금", "정책금융 자금용도 표현"),
        (r"시설\s+자금", "시설자금", "정책금융 자금용도 표현"),
        (r"신용\s*보증", "신용보증", "보증기관/보증상품 표현"),
        (r"사업자\s*등록", "사업자등록", "사업자 정보 표현"),
    ]
    for pattern, replacement, reason in replacements:
        next_text, count = re.subn(pattern, replacement, corrected)
        if count:
            corrections.append({"원문": pattern, "보정": replacement, "근거": reason})
            corrected = next_text

    return corrected, corrections


def should_refresh_live_analysis(
    transcript: str,
    last_analyzed_at: datetime | None,
    last_analyzed_length: int,
    *,
    interval_seconds: int = 7,
) -> bool:
    if not transcript.strip():
        return False
    if len(transcript.strip()) <= last_analyzed_length:
        return False
    if last_analyzed_at is None:
        return True
    return (datetime.now() - last_analyzed_at).total_seconds() >= interval_seconds


def _compact_summary(transcript: str) -> str:
    text = clean_spoken_text(transcript)
    if not text:
        return "아직 받아쓰기 내용이 없습니다."
    normalized = re.sub(r"(다\.|요\.|음\.|[.!?。])", r"\1\n", text)
    parts = re.split(r"\n+", normalized)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return text[-220:]
    return " / ".join(parts[-3:])[:420]


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return f"{value:,}"
    return str(value).strip()


def _case_has_value(value: Any) -> bool:
    return _format_value(value) not in UNKNOWN_VALUES


def apply_live_profile_to_case(case: Any, parsed: dict[str, Any], corrections: list[dict[str, str]] | None = None) -> bool:
    """Apply live speech extraction to empty profile fields only."""
    changed = False
    evidence = parsed.get("field_evidence", {}) or {}
    statuses = parsed.get("field_status", {}) or {}
    sources = parsed.get("field_source", {}) or {}
    basis_period = parsed.get("field_basis_period", {}) or {}
    locations = parsed.get("field_evidence_location", {}) or {}

    for field in STRUCTURED_FIELDS:
        value = parsed.get(field)
        if not _case_has_value(value):
            continue
        current = getattr(case, field, None)
        if _case_has_value(current):
            continue
        setattr(case, field, value)
        case.field_evidence[field] = str(evidence.get(field) or "실시간 음성 상담에서 추출")
        case.field_status[field] = str(statuses.get(field) or "확인됨")
        case.field_source[field] = str(sources.get(field) or "고객 진술/실시간 음성")
        case.field_basis_period[field] = str(basis_period.get(field) or "")
        case.field_evidence_location[field] = str(locations.get(field) or "실시간 음성 받아쓰기")
        changed = True

    if corrections:
        correction_text = "; ".join(
            f"{item.get('원문')}→{item.get('보정')}" for item in corrections[:5]
            if item.get("원문") and item.get("보정")
        )
        if correction_text:
            existing = case.special_notes or ""
            note = f"음성 문맥 보정: {correction_text}"
            if note not in existing:
                case.special_notes = f"{existing}\n{note}".strip()
                changed = True
    return changed


def analyze_live_customer_profile(transcript: str) -> dict[str, Any]:
    """
    Extract only customer/business profile fields for live counseling.

    This deliberately does not run policy eligibility, scoring, report generation,
    or notification logic. It is a lightweight profile preview for tab 1.
    """
    source_text, corrections = normalize_finance_transcript_for_analysis(transcript[-12000:])
    parsed = parse_consultation(source_text)
    evidence = parsed.get("field_evidence", {}) or {}
    statuses = parsed.get("field_status", {}) or {}
    rows: list[dict[str, str]] = []

    for field, label in PROFILE_FIELDS:
        if field not in STRUCTURED_FIELDS:
            continue
        value = _format_value(parsed.get(field))
        if value in UNKNOWN_VALUES:
            value = ""
        status = statuses.get(field) or ("확인 완료" if value else "미확인")
        if status in {"AI 후보", "확인됨"}:
            status = "확인 완료"
        rows.append(
            {
                "항목": label,
                "값": value or "미확인",
                "상태": status,
                "근거": str(evidence.get(field) or "상담 음성 맥락에서 아직 확인되지 않았습니다.")[:180],
            }
        )

    confirmed = sum(1 for row in rows if row["값"] != "미확인" and row["상태"] == "확인 완료")
    needs_review = sum(1 for row in rows if row["값"] == "미확인" or row["상태"] != "확인 완료")
    return {
        "summary": _compact_summary(transcript),
        "rows": rows,
        "confirmed": confirmed,
        "needs_review": needs_review,
        "parsed": parsed,
        "normalized_transcript": source_text,
        "corrections": corrections,
        "parser_mode": parsed.get("parser_mode", "rules"),
        "parser_error": parsed.get("parser_error", ""),
        "analyzed_at": datetime.now().strftime("%H:%M:%S"),
    }
