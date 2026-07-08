"""Consultation text parser with rule-based fallback and optional LLM."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from services.llm_client import LLMClient
from utils.constants import (
    DEFAULT_EVIDENCE_LOCATION,
    DEFAULT_FIELD_SOURCE,
    FIELD_BASIS_PERIOD,
    FIELD_STATUS_OPTIONS,
    FUNDING_PURPOSE_KEYWORDS,
    INDUSTRY_KEYWORDS,
    REGION_KEYWORDS,
    UNKNOWN,
)

EXTRACTABLE_FIELDS = [
    "industry",
    "region",
    "business_type",
    "business_start_date",
    "business_months",
    "annual_revenue",
    "monthly_revenue",
    "revenue_trend",
    "funding_purpose",
    "required_amount",
    "existing_loan",
    "existing_guarantee",
    "credit_score",
    "credit_band",
    "collateral",
    "tax_arrears",
    "business_status",
    "requested_timeline",
    "special_notes",
]

LAST_LLM_PARSE_ERROR = ""

SEOUL_DISTRICTS = [
    "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
    "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구",
    "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구",
]


def _metadata_for_extracted_fields(result: dict[str, Any], evidence: dict[str, str]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    sources: dict[str, str] = {}
    basis_periods: dict[str, str] = {}
    evidence_locations: dict[str, str] = {}
    for field in EXTRACTABLE_FIELDS:
        if field in result or field in evidence:
            sources[field] = DEFAULT_FIELD_SOURCE
            basis_periods[field] = FIELD_BASIS_PERIOD.get(field, "상담일 현재")
            evidence_locations[field] = DEFAULT_EVIDENCE_LOCATION
    return sources, basis_periods, evidence_locations


def _parse_amount(text: str) -> int | None:
    patterns = [
        (r"(\d+(?:\.\d+)?)\s*억", 100_000_000),
        (r"(\d+(?:\.\d+)?)\s*천\s*만", 10_000_000),
        (r"(\d+(?:,\d+)?)\s*만\s*원?", 10_000),
        (r"(\d+(?:,\d+)?)\s*원", 1),
    ]
    for pattern, multiplier in patterns:
        m = re.search(pattern, text)
        if m:
            num = float(m.group(1).replace(",", ""))
            return int(num * multiplier)
    return None


def _parse_business_months(text: str) -> tuple[int | None, str]:
    m = re.search(r"(\d+)\s*년\s*(\d+)\s*개월", text)
    if m:
        months = int(m.group(1)) * 12 + int(m.group(2))
        return months, f"원문에서 '{m.group(0)}' 추출"
    m = re.search(r"(\d+)\s*년", text)
    if m:
        months = int(m.group(1)) * 12
        return months, f"원문에서 '{m.group(0)}' 추출"
    m = re.search(r"(\d+)\s*개월", text)
    if m:
        return int(m.group(1)), f"원문에서 '{m.group(0)}' 추출"
    return None, ""


def _extract_keyword_field(text: str, mapping: dict[str, str]) -> tuple[str | None, str]:
    for keyword, value in mapping.items():
        if keyword in text:
            return value, f"원문에 '{keyword}' 언급"
    return None, ""


def _extract_region(text: str) -> tuple[str | None, str]:
    for district in SEOUL_DISTRICTS:
        if district in text:
            return f"서울 {district}", f"원문에 '{district}' 언급"
    for region in REGION_KEYWORDS:
        if region in text:
            return region, f"원문에 '{region}' 언급"
    return None, ""


def _extract_business_type(text: str) -> tuple[str | None, str]:
    if "개인사업자" in text:
        return "소상공인", "원문에 '개인사업자' 언급, 상담 기준 사업자 형태는 소상공인으로 정규화"
    if "법인사업자" in text or "법인" in text:
        return "법인사업자", "원문에 '법인사업자/법인' 언급"
    if "사업자등록증" in text or "사업자" in text:
        return UNKNOWN, "원문에 사업자 형태 관련 단서가 있으나 개인/법인 여부는 불명확"
    return None, ""


def _detect_revenue_trend(text: str) -> tuple[str | None, str]:
    decline_keywords = ["매출 감소", "매출 줄", "매출 하락", "매출이 줄", "매출이 감소", "매출이 떨어", "어려워"]
    for kw in decline_keywords:
        if kw in text:
            return "감소", f"원문에 '{kw}' 언급"
    if "매출 증가" in text or "매출이 늘" in text:
        return "증가", "원문에 매출 증가 언급"
    return None, ""


def _detect_yes_no(
    text: str,
    positive: list[str],
    negative: list[str] | None = None,
    subject_keywords: list[str] | None = None,
) -> tuple[str | None, str]:
    negative = negative or []
    subject_keywords = subject_keywords or []
    uncertain = ["기억이 안", "기억 안", "정확히 기억", "모르", "불명확", "확인 전"]
    mentions_subject = any(kw in text for kw in positive + negative + subject_keywords)
    if any(kw in text for kw in uncertain) and mentions_subject:
        return UNKNOWN, "원문에서 해당 여부가 불명확하다고 언급"
    for kw in positive:
        if kw in text:
            return "있음", f"원문에 '{kw}' 언급"
    for kw in negative:
        if kw in text:
            return "없음", f"원문에 '{kw}' 언급"
    return None, ""


def parse_consultation_text(raw_text: str) -> dict[str, Any]:
    """Rule-based parser for consultation text."""
    text = raw_text.strip()
    result: dict[str, Any] = {}
    evidence: dict[str, str] = {}
    status: dict[str, str] = {}

    def set_field(field: str, value: Any, ev: str = "", confirmed: bool = True):
        if value is not None:
            result[field] = value
            if ev:
                evidence[field] = ev
            if value == UNKNOWN:
                status[field] = "추가 확인 필요" if ev else "미확인"
            else:
                status[field] = "확인됨" if confirmed else "추가 확인 필요"
        else:
            status[field] = "미확인"

    industry, ev = _extract_keyword_field(text, INDUSTRY_KEYWORDS)
    set_field("industry", industry, ev)

    region, ev = _extract_region(text)
    set_field("region", region, ev)

    business_type, ev = _extract_business_type(text)
    set_field("business_type", business_type, ev)

    purpose, ev = _extract_keyword_field(text, FUNDING_PURPOSE_KEYWORDS)
    set_field("funding_purpose", purpose, ev)

    trend, ev = _detect_revenue_trend(text)
    set_field("revenue_trend", trend, ev)

    loan, ev = _detect_yes_no(text, ["기존 대출", "대출 있", "대출이 있", "대출도"], subject_keywords=["대출"])
    set_field("existing_loan", loan, ev)

    guarantee, ev = _detect_yes_no(text, ["보증 이용", "보증을", "보증 있"], subject_keywords=["보증"])
    set_field("existing_guarantee", guarantee, ev)

    months, ev = _parse_business_months(text)
    set_field("business_months", months, ev)

    amount = _parse_amount(text)
    if amount:
        if "연매출" in text or "년 매출" in text:
            set_field("annual_revenue", amount, "원문 금액 표현에서 추출")
        elif "월" in text and "매출" in text:
            set_field("monthly_revenue", amount, "원문 금액 표현에서 추출")
        elif "필요" in text or "자금" in text:
            set_field("required_amount", amount, "원문 금액 표현에서 추출 (용도 확인 필요)", confirmed=False)

    if "체납" in text:
        if "없" in text[max(0, text.index("체납") - 5): text.index("체납") + 10]:
            set_field("tax_arrears", "없음", "원문 체납 관련 언급")
        else:
            set_field("tax_arrears", "있음", "원문 체납 관련 언급")

    if "폐업" in text or "휴업" in text:
        set_field("business_status", "휴폐업", "원문 휴폐업 언급")
    elif "운영" in text or "영업" in text:
        set_field("business_status", "정상운영", "원문 운영 관련 언급")

    field_source, field_basis_period, field_evidence_location = _metadata_for_extracted_fields(result, evidence)
    result["field_evidence"] = evidence
    result["field_status"] = status
    result["field_source"] = field_source
    result["field_basis_period"] = field_basis_period
    result["field_evidence_location"] = field_evidence_location
    return result


def _to_int(value: Any) -> int | None:
    if value in (None, "", UNKNOWN):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value)
    amount = _parse_amount(text)
    if amount:
        return amount
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None


def _normalize_yes_no(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    if any(x in text for x in ["불명확", "모름", "기억", "확인", UNKNOWN]):
        return UNKNOWN
    if any(x in text for x in ["없", "미이용", "아니"]):
        return "없음"
    if any(x in text for x in ["있", "이용", "받"]):
        return "있음"
    return text


INDUSTRY_LIKE_BUSINESS_TYPE_TERMS = tuple(
    set(INDUSTRY_KEYWORDS.keys())
    | set(INDUSTRY_KEYWORDS.values())
    | {
        "식당",
        "요식",
        "외식",
        "분식",
        "베이커리",
        "제과",
        "네일",
        "편의점",
        "마트",
        "공방",
        "세탁",
        "숙박",
        "서비스업",
        "매장",
        "점포",
    }
)

BUSINESS_FORM_TERMS = (
    "개인사업자",
    "개인 사업자",
    "법인사업자",
    "법인 사업자",
    "법인",
    "소상공인",
    "소기업",
    "중소기업",
)


def _normalize_business_type_value(value: Any) -> str | None:
    if value in (None, "", UNKNOWN):
        return None if value in (None, "") else UNKNOWN
    text = str(value).strip()
    compact = text.replace(" ", "")
    if "개인사업자" in compact:
        return "소상공인"
    return text


def _looks_like_industry_value(value: Any) -> bool:
    if value in (None, "", UNKNOWN):
        return False
    text = str(value)
    if any(term in text for term in BUSINESS_FORM_TERMS):
        return False
    return any(term in text for term in INDUSTRY_LIKE_BUSINESS_TYPE_TERMS)


def _normalize_llm_result(data: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in EXTRACTABLE_FIELDS:
        value = data.get(field)
        if field in ("business_months", "annual_revenue", "monthly_revenue", "required_amount", "credit_score"):
            value = _to_int(value)
        elif field == "business_type":
            value = _normalize_business_type_value(value)
        elif field in ("existing_loan", "existing_guarantee", "tax_arrears"):
            value = _normalize_yes_no(value)
        if value not in (None, ""):
            normalized[field] = value

    evidence = data.get("field_evidence") or {}
    status = data.get("field_status") or {}
    source = data.get("field_source") or {}
    basis_period = data.get("field_basis_period") or {}
    evidence_location = data.get("field_evidence_location") or {}
    if not isinstance(evidence, dict):
        evidence = {}
    if not isinstance(status, dict):
        status = {}
    if not isinstance(source, dict):
        source = {}
    if not isinstance(basis_period, dict):
        basis_period = {}
    if not isinstance(evidence_location, dict):
        evidence_location = {}

    business_type_value = normalized.get("business_type")
    if _looks_like_industry_value(business_type_value):
        if "industry" not in normalized:
            normalized["industry"] = str(business_type_value)
            evidence["industry"] = evidence.get("industry") or evidence.get("business_type") or "업종 표현을 industry로 보정"
            status["industry"] = status.get("industry") or "확인됨"
        normalized.pop("business_type", None)
        evidence["business_type"] = evidence.get("business_type") or "업종 표현이므로 사업자 형태에서는 제외"
        status["business_type"] = "추가 확인 필요"

    normalized["field_evidence"] = {k: str(v) for k, v in evidence.items() if k in EXTRACTABLE_FIELDS and v}
    normalized["field_status"] = {}
    for field in EXTRACTABLE_FIELDS:
        if field not in normalized and field not in normalized["field_evidence"]:
            continue
        raw_status = str(status.get(field, "확인됨"))
        if raw_status not in FIELD_STATUS_OPTIONS:
            raw_status = "확인됨"
        if normalized.get(field) == UNKNOWN:
            normalized["field_status"][field] = "추가 확인 필요"
        elif raw_status in ("미확인", "추가 확인 필요"):
            normalized["field_status"][field] = raw_status
        else:
            normalized["field_status"][field] = "확인됨"

    metadata_fields = {
        field
        for field in EXTRACTABLE_FIELDS
        if field in normalized or field in normalized["field_evidence"] or field in normalized["field_status"]
    }
    normalized["field_source"] = {
        field: str(source.get(field) or DEFAULT_FIELD_SOURCE)
        for field in metadata_fields
    }
    normalized["field_basis_period"] = {
        field: str(basis_period.get(field) or FIELD_BASIS_PERIOD.get(field, "상담일 현재"))
        for field in metadata_fields
    }
    normalized["field_evidence_location"] = {
        field: str(evidence_location.get(field) or DEFAULT_EVIDENCE_LOCATION)
        for field in metadata_fields
    }
    for field in EXTRACTABLE_FIELDS:
        if normalized.get(field) == UNKNOWN:
            normalized["field_status"][field] = "추가 확인 필요"
    return normalized


def parse_with_llm(raw_text: str) -> dict[str, Any] | None:
    """Use an LLM to extract structured consultation fields when configured."""
    global LAST_LLM_PARSE_ERROR
    LAST_LLM_PARSE_ERROR = ""
    client = LLMClient()
    if not client.is_available():
        LAST_LLM_PARSE_ERROR = client.setup_message()
        return None

    system_prompt = (
        "너는 정책금융 초기상담 메모를 금융상담 프로필로 구조화하는 전문가다. "
        "고객이 말한 내용만 근거로 삼고, 승인 가능성·한도·금리는 판단하지 않는다. "
        "확실하지 않은 값은 null 또는 '미확인'으로 둔다. "
        "원문 근거가 있는 값은 field_status를 '확인됨'으로 두고, 추정이나 모호한 값은 '추가 확인 필요'로 둔다."
    )
    user_prompt = f"""
다음 상담 원문에서 아래 JSON 스키마로만 추출해라.

허용 필드:
industry, region, business_type, business_start_date, business_months, annual_revenue, monthly_revenue,
revenue_trend, funding_purpose, required_amount, existing_loan, existing_guarantee,
credit_score, credit_band, collateral, tax_arrears, business_status, requested_timeline, special_notes

field_evidence에는 각 필드가 나온 원문 근거 문장을 짧게 넣어라.
field_status에는 각 필드의 확인상태를 '확인됨', '추가 확인 필요', '미확인' 중 하나로 넣어라.
field_source에는 고객 발언에서 추출한 필드는 '고객 진술/상담 원문'으로 넣어라.
field_basis_period에는 기준 기간이 명확하면 넣고, 아니면 비워도 된다.
field_evidence_location에는 원문 근거 위치를 짧게 넣어라. 예: '상담 원문'
금액은 원 단위 숫자로, 업력은 개월 수 숫자로 반환해라.
business_type에는 법인사업자/소상공인/중소기업 같은 사업자 형태만 넣어라.
원문에 개인사업자라고 나오면 business_type은 '소상공인'으로 반환해라.
음식점, 카페, 미용실, 도소매, 쇼핑몰 같은 업종은 industry에 넣고,
개인/법인 여부가 원문에 없으면 business_type은 null 또는 '미확인'으로 둬라.

상담 원문:
{raw_text}

반환 예:
{{
  "industry": "음식점",
  "region": "서울 마포구",
  "business_months": 36,
  "funding_purpose": "운영자금",
  "required_amount": null,
  "existing_guarantee": "미확인",
  "field_evidence": {{"region": "마포구에서 음식점을 한 지 3년 정도"}},
  "field_status": {{"region": "확인됨", "existing_guarantee": "추가 확인 필요"}},
  "field_source": {{"region": "고객 진술/상담 원문"}},
  "field_evidence_location": {{"region": "상담 원문"}}
}}
"""
    data = client.generate_json(system_prompt, user_prompt, "consultation_extraction")
    if not data:
        LAST_LLM_PARSE_ERROR = client.last_error or "GPT 응답이 비어 있어 규칙 파서로 처리했습니다."
        return None
    normalized = _normalize_llm_result(data)
    normalized["parser_mode"] = client.provider_name()
    return normalized


def parse_consultation(raw_text: str) -> dict[str, Any]:
    """Parse consultation with optional LLM, always falls back to rules."""
    llm_result = parse_with_llm(raw_text)
    rule_result = parse_consultation_text(raw_text)
    if llm_result:
        metadata_keys = {
            "field_evidence",
            "field_status",
            "field_source",
            "field_basis_period",
            "field_evidence_location",
        }
        merged = {**rule_result, **{k: v for k, v in llm_result.items() if k not in metadata_keys and v is not None}}
        merged["field_evidence"] = {
            **rule_result.get("field_evidence", {}),
            **llm_result.get("field_evidence", {}),
        }
        merged["field_status"] = {
            **rule_result.get("field_status", {}),
            **llm_result.get("field_status", {}),
        }
        merged["field_source"] = {
            **rule_result.get("field_source", {}),
            **llm_result.get("field_source", {}),
        }
        merged["field_basis_period"] = {
            **rule_result.get("field_basis_period", {}),
            **llm_result.get("field_basis_period", {}),
        }
        merged["field_evidence_location"] = {
            **rule_result.get("field_evidence_location", {}),
            **llm_result.get("field_evidence_location", {}),
        }
        merged["parser_mode"] = "llm+rules"
        return merged
    rule_result["parser_mode"] = "rules"
    if LAST_LLM_PARSE_ERROR:
        rule_result["parser_error"] = LAST_LLM_PARSE_ERROR
    return rule_result
