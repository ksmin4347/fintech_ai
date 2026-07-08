"""Rule-based policy eligibility engine."""

from __future__ import annotations

from datetime import date, datetime

from models.schemas import (
    BusinessCase,
    ConditionResult,
    EligibilityResult,
    PolicyProduct,
)
from utils.constants import UNKNOWN
from utils.formatters import format_amount, format_months


def _make_condition(
    name: str,
    customer: str,
    policy_req: str,
    result: str,
    reason: str,
    evidence: str = "",
    needs_confirmation: bool = False,
) -> ConditionResult:
    return ConditionResult(
        condition_name=name,
        customer_value=customer,
        policy_requirement=policy_req,
        result=result,
        reason=reason,
        evidence=evidence,
        needs_confirmation=needs_confirmation,
    )


def _str_val(case: BusinessCase, field: str) -> str:
    val = getattr(case, field, None)
    if val is None or val == "":
        return UNKNOWN
    return str(val)


UNRESTRICTED_BUSINESS_TYPE_TERMS = (
    "제한 없음",
    "제한없음",
    "무관",
    "전체",
    "사업자 전체",
    "모든 사업자",
)

SMALL_BUSINESS_TARGET_TERMS = (
    "소상공인",
    "소기업",
    "중소기업",
    "자영업자",
)

SMALL_BUSINESS_CONTEXT_TERMS = (
    "음식점",
    "식당",
    "카페",
    "커피",
    "요식",
    "외식",
    "분식",
    "베이커리",
    "제과",
    "미용",
    "네일",
    "도소매",
    "소매",
    "편의점",
    "마트",
    "온라인",
    "쇼핑몰",
    "공방",
    "학원",
    "세탁",
    "숙박",
    "제조",
    "서비스",
    "매장",
    "점포",
)

INDIVIDUAL_BUSINESS_TERMS = ("개인사업자", "개인 사업자", "개인")
CORPORATE_BUSINESS_TERMS = ("법인사업자", "법인 사업자", "법인")


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    compact = text.replace(" ", "")
    return any(term in text or term.replace(" ", "") in compact for term in terms)


def _looks_like_small_business_context(text: str) -> bool:
    return _contains_any(text, SMALL_BUSINESS_TARGET_TERMS) or _contains_any(text, SMALL_BUSINESS_CONTEXT_TERMS)


def _business_type_match(customer: str, allowed: str) -> tuple[str, str]:
    if allowed in customer or customer in allowed:
        return "met", "허용 사업자 형태에 포함"

    if _contains_any(allowed, UNRESTRICTED_BUSINESS_TYPE_TERMS):
        return "not_applicable", "사업자 형태 제한 없음"

    customer_individual = _contains_any(customer, INDIVIDUAL_BUSINESS_TERMS)
    customer_corporate = _contains_any(customer, CORPORATE_BUSINESS_TERMS)
    allowed_individual = _contains_any(allowed, INDIVIDUAL_BUSINESS_TERMS)
    allowed_corporate = _contains_any(allowed, CORPORATE_BUSINESS_TERMS)

    if customer_individual and allowed_corporate and not allowed_individual:
        return "not_met", "개인사업자와 법인사업자 조건 불일치"
    if customer_corporate and allowed_individual and not allowed_corporate:
        return "not_met", "법인사업자와 개인사업자 조건 불일치"

    if _contains_any(allowed, SMALL_BUSINESS_TARGET_TERMS):
        if _looks_like_small_business_context(customer):
            return "met", "음식점·카페 등 업종 표현은 소상공인 대상 조건과 충돌하지 않음"
        if customer_individual:
            return "met", "개인사업자는 상담 기준 소상공인 대상 조건으로 정규화"
        if customer_corporate:
            return "needs_confirmation", "법인사업자는 소상공인 규모요건 추가 확인 필요"

    if (allowed_individual or allowed_corporate) and _looks_like_small_business_context(customer):
        return "needs_confirmation", "고객 값은 업종 표현이므로 개인/법인 여부 추가 확인 필요"

    return "no_match", ""


def _check_industry(case: BusinessCase, policy: PolicyProduct) -> ConditionResult:
    customer = _str_val(case, "industry")
    if customer == UNKNOWN:
        return _make_condition("업종", customer, str(policy.allowed_industries), "미확인", "업종 정보 확인 필요")
    for exc in policy.excluded_industries:
        if exc in customer or customer in exc:
            return _make_condition("업종", customer, f"제외: {policy.excluded_industries}", "미충족", f"제외업종 '{exc}'에 해당 가능")
    if policy.allowed_industries:
        for allowed in policy.allowed_industries:
            if allowed in customer or customer in allowed or "전업종" in allowed:
                return _make_condition("업종", customer, str(policy.allowed_industries), "충족", "허용 업종에 포함")
        return _make_condition("업종", customer, str(policy.allowed_industries), "미충족", "허용 업종에 포함되지 않음")
    return _make_condition("업종", customer, "제한 없음", "해당 없음", "업종 제한 없음")


def _check_region(case: BusinessCase, policy: PolicyProduct) -> ConditionResult:
    customer = _str_val(case, "region")
    if not policy.allowed_regions or "전국" in policy.allowed_regions:
        return _make_condition("지역", customer, "전국", "해당 없음", "지역 제한 없음")
    policy_req = ", ".join(policy.allowed_regions)
    if customer == UNKNOWN:
        return _make_condition("지역", customer, policy_req, "미확인", "사업장 소재지 확인 필요")
    for region in policy.allowed_regions:
        if region in customer or customer in region:
            return _make_condition("지역", customer, policy_req, "충족", "허용 지역에 포함")
    return _make_condition("지역", customer, policy_req, "미충족", "허용 지역 외")


def _check_business_type(case: BusinessCase, policy: PolicyProduct) -> ConditionResult:
    customer = _str_val(case, "business_type")
    if not policy.allowed_business_types:
        return _make_condition("사업자 형태", customer, "미구조화", "판단 보류", "사업자 형태 조건 공식문서 대조 필요", needs_confirmation=True)
    policy_req = ", ".join(policy.allowed_business_types)
    if customer == UNKNOWN:
        return _make_condition("사업자 형태", customer, policy_req, "미확인", "개인사업자/법인사업자 여부 확인 필요")
    needs_confirmation_reason = ""
    for allowed in policy.allowed_business_types:
        relation, reason = _business_type_match(customer, allowed)
        if relation == "met":
            return _make_condition("사업자 형태", customer, policy_req, "충족", reason)
        if relation == "not_applicable":
            return _make_condition("사업자 형태", customer, policy_req, "해당 없음", reason)
        if relation == "not_met":
            return _make_condition("사업자 형태", customer, policy_req, "미충족", reason)
        if relation == "needs_confirmation" and not needs_confirmation_reason:
            needs_confirmation_reason = reason
    if needs_confirmation_reason:
        return _make_condition(
            "사업자 형태",
            customer,
            policy_req,
            "추가 확인 필요",
            needs_confirmation_reason,
            needs_confirmation=True,
        )
    return _make_condition("사업자 형태", customer, policy_req, "미충족", "허용 사업자 형태와 불일치")


def _check_business_months(case: BusinessCase, policy: PolicyProduct) -> ConditionResult:
    months = case.business_months
    customer = format_months(months) if months else UNKNOWN
    parts = []
    if policy.min_business_months:
        parts.append(f"최소 {policy.min_business_months}개월")
    if policy.max_business_months:
        parts.append(f"최대 {policy.max_business_months}개월")
    policy_req = ", ".join(parts) if parts else "제한 없음"
    if months is None:
        return _make_condition("업력", customer, policy_req, "미확인", "업력 정보 확인 필요")
    if policy.min_business_months and months < policy.min_business_months:
        return _make_condition("업력", customer, policy_req, "미충족", f"최소 업력 {policy.min_business_months}개월 미달")
    if policy.max_business_months and months > policy.max_business_months:
        return _make_condition("업력", customer, policy_req, "미충족", f"최대 업력 {policy.max_business_months}개월 초과")
    return _make_condition("업력", customer, policy_req, "충족", "업력 조건 충족")


def _check_revenue(case: BusinessCase, policy: PolicyProduct) -> ConditionResult:
    revenue = case.annual_revenue
    customer = format_amount(revenue) if revenue else UNKNOWN
    parts = []
    if policy.min_revenue:
        parts.append(f"최소 {format_amount(policy.min_revenue)}")
    if policy.max_revenue:
        parts.append(f"최대 {format_amount(policy.max_revenue)}")
    policy_req = ", ".join(parts) if parts else "제한 없음"
    if not policy.min_revenue and not policy.max_revenue:
        return _make_condition("연매출", customer, policy_req, "해당 없음", "매출 제한 없음")
    if revenue is None:
        return _make_condition("연매출", customer, policy_req, "미확인", "연매출 확인 필요")
    if policy.min_revenue and revenue < policy.min_revenue:
        return _make_condition("연매출", customer, policy_req, "미충족", "최소 매출 기준 미달")
    if policy.max_revenue and revenue > policy.max_revenue:
        return _make_condition("연매출", customer, policy_req, "미충족", "최대 매출 기준 초과")
    return _make_condition("연매출", customer, policy_req, "충족", "매출 조건 충족")


def _check_credit(case: BusinessCase, policy: PolicyProduct) -> ConditionResult:
    score = case.credit_score
    band = _str_val(case, "credit_band")
    customer = str(score) if score else band
    if not policy.credit_score_min and not policy.credit_score_max:
        return _make_condition("신용", customer, "제한 없음", "해당 없음", "신용 제한 없음")
    policy_req = f"{policy.credit_score_min or 0}~{policy.credit_score_max or 1000}점"
    if score is None and band == UNKNOWN:
        return _make_condition("신용", customer, policy_req, "미확인", "신용정보 확인 필요")
    if score is not None:
        if policy.credit_score_min and score < policy.credit_score_min:
            return _make_condition("신용", customer, policy_req, "미충족", "최소 신용점수 미달")
        if policy.credit_score_max and score > policy.credit_score_max:
            return _make_condition("신용", customer, policy_req, "미충족", "최대 신용점수 초과")
        return _make_condition("신용", customer, policy_req, "충족", "신용 조건 충족")
    return _make_condition("신용", customer, policy_req, "추가 확인 필요", "신용구간 상세 확인 필요", needs_confirmation=True)


def _check_funding_purpose(case: BusinessCase, policy: PolicyProduct) -> ConditionResult:
    customer = _str_val(case, "funding_purpose")
    policy_req = ", ".join(policy.funding_purposes) if policy.funding_purposes else "제한 없음"
    if not policy.funding_purposes:
        return _make_condition("자금용도", customer, policy_req, "해당 없음", "자금용도 제한 없음")
    if customer == UNKNOWN:
        return _make_condition("자금용도", customer, policy_req, "미확인", "자금용도 확인 필요")
    for purpose in policy.funding_purposes:
        if purpose in customer or customer in purpose:
            return _make_condition("자금용도", customer, policy_req, "충족", "자금용도 일치")
    return _make_condition("자금용도", customer, policy_req, "미충족", "허용 자금용도와 불일치")


def _check_application_period(policy: PolicyProduct, reference_date: date) -> ConditionResult:
    if not policy.application_start_date and not policy.application_end_date:
        return _make_condition("신청기간", str(reference_date), "상시", "해당 없음", "신청기간 제한 없음")
    try:
        start = datetime.strptime(policy.application_start_date, "%Y-%m-%d").date() if policy.application_start_date else None
        end = datetime.strptime(policy.application_end_date, "%Y-%m-%d").date() if policy.application_end_date else None
    except ValueError:
        return _make_condition("신청기간", str(reference_date), "불명확", "판단 보류", "신청기간 데이터 불완전")
    policy_req = f"{policy.application_start_date} ~ {policy.application_end_date}"
    if start and reference_date < start:
        return _make_condition("신청기간", str(reference_date), policy_req, "미충족", "신청 시작 전")
    if end and reference_date > end:
        return _make_condition("신청기간", str(reference_date), policy_req, "미충족", "신청 기간 종료")
    return _make_condition("신청기간", str(reference_date), policy_req, "충족", "신청 기간 내")


def _check_tax_arrears(case: BusinessCase, policy: PolicyProduct) -> ConditionResult:
    customer = _str_val(case, "tax_arrears")
    has_exclusion = any("체납" in c for c in policy.exclusion_conditions)
    if not has_exclusion:
        return _make_condition("세금 체납", customer, "체납 제외", "해당 없음", "체납 관련 제외조건 없음")
    if customer == UNKNOWN:
        return _make_condition("세금 체납", customer, "체납 시 제외", "추가 확인 필요", "체납 여부 확인 필요", needs_confirmation=True)
    if customer == "있음":
        return _make_condition("세금 체납", customer, "체납 시 제외", "미충족", "세금 체납으로 제외 가능")
    return _make_condition("세금 체납", customer, "체납 시 제외", "충족", "체납 없음 확인")


def _check_business_status(case: BusinessCase, policy: PolicyProduct) -> ConditionResult:
    customer = _str_val(case, "business_status")
    if customer == "휴폐업":
        return _make_condition("사업상태", customer, "정상운영 필요", "미충족", "휴폐업 상태로 검토 어려움")
    if customer == UNKNOWN:
        return _make_condition("사업상태", customer, "정상운영 필요", "미확인", "사업 운영 여부 확인 필요")
    return _make_condition("사업상태", customer, "정상운영 필요", "충족", "정상 운영 확인")


def _check_duplicate_support(case: BusinessCase, policy: PolicyProduct) -> ConditionResult:
    if not policy.duplicate_support_restriction:
        return _make_condition("중복지원", _str_val(case, "existing_guarantee"), "제한 없음", "해당 없음", "중복지원 제한 없음")
    guarantee = _str_val(case, "existing_guarantee")
    loan = _str_val(case, "existing_loan")
    if guarantee == UNKNOWN and loan == UNKNOWN:
        return _make_condition("중복지원", guarantee, policy.duplicate_support_restriction, "미확인", "기존 지원 이용 여부 확인 필요")
    if guarantee == "있음" or loan == "있음":
        return _make_condition("중복지원", f"보증:{guarantee}, 대출:{loan}", policy.duplicate_support_restriction, "추가 확인 필요", "중복지원 가능 여부 확인 필요", needs_confirmation=True)
    return _make_condition("중복지원", f"보증:{guarantee}, 대출:{loan}", policy.duplicate_support_restriction, "충족", "중복지원 제한 해당 없음")


def _determine_final_status(conditions: list[ConditionResult]) -> str:
    core = [c for c in conditions if c.result not in ("해당 없음",)]
    if not core:
        return "판단 보류"
    if any(c.result == "미충족" for c in core):
        return "제외 가능성"
    if any(c.result in ("미확인", "추가 확인 필요") for c in core):
        return "조건부 검토"
    if all(c.result == "충족" for c in core):
        return "검토 가능"
    return "판단 보류"


def evaluate_policy(
    case: BusinessCase,
    policy: PolicyProduct,
    reference_date: date,
) -> EligibilityResult:
    conditions = [
        _check_industry(case, policy),
        _check_region(case, policy),
        _check_business_type(case, policy),
        _check_business_months(case, policy),
        _check_revenue(case, policy),
        _check_credit(case, policy),
        _check_funding_purpose(case, policy),
        _check_application_period(policy, reference_date),
        _check_tax_arrears(case, policy),
        _check_business_status(case, policy),
        _check_duplicate_support(case, policy),
    ]

    final_status = _determine_final_status(conditions)
    exclusion = [c.reason for c in conditions if c.result == "미충족"]
    missing = [c.condition_name for c in conditions if c.result in ("미확인", "추가 확인 필요")]

    met_reasons = [c.reason for c in conditions if c.result == "충족"]
    summary = met_reasons[0] if met_reasons and final_status == "검토 가능" else (
        exclusion[0] if exclusion else (f"{missing[0]} 확인 필요" if missing else "추가 검토 필요")
    )

    return EligibilityResult(
        policy_id=policy.policy_id,
        policy_name=policy.policy_name,
        institution=policy.institution,
        final_status=final_status,
        summary_reason=summary,
        condition_results=conditions,
        missing_fields=missing,
        exclusion_reasons=exclusion,
        required_documents=policy.required_documents,
        next_actions=[f"{m} 추가 확인" for m in missing[:3]],
        source={
            "source_name": policy.source_name,
            "source_url": policy.source_url,
            "source_date": policy.source_date,
            "is_sample_data": str(policy.is_sample_data),
        },
    )


def evaluate_all_policies(
    case: BusinessCase,
    policies: list[PolicyProduct],
    reference_date: date,
) -> list[EligibilityResult]:
    return [evaluate_policy(case, p, reference_date) for p in policies]
