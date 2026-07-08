"""Policy rule table builder based on the business plan section 7."""

from __future__ import annotations

from typing import Any

import pandas as pd

from models.schemas import PolicyProduct
from utils.formatters import format_amount, format_months


def _join(values: list[str] | None, empty: str = "공식문서 대조 필요") -> str:
    values = [str(v) for v in values or [] if str(v).strip()]
    return ", ".join(values) if values else empty


def _period(policy: PolicyProduct) -> str:
    if not policy.application_start_date and not policy.application_end_date:
        return "상시 또는 미구조화"
    return f"{policy.application_start_date or '시작일 미정'} ~ {policy.application_end_date or '종료일 미정'}"


def _business_month_rule(policy: PolicyProduct) -> str:
    parts = []
    if policy.min_business_months is not None:
        parts.append(f"최소 {format_months(policy.min_business_months)}")
    if policy.max_business_months is not None:
        parts.append(f"최대 {format_months(policy.max_business_months)}")
    return ", ".join(parts) if parts else "업력 제한 없음 또는 미구조화"


def _amount_rule(min_value: int | None, max_value: int | None, label: str) -> str:
    parts = []
    if min_value is not None:
        parts.append(f"최소 {format_amount(min_value)}")
    if max_value is not None:
        parts.append(f"최대 {format_amount(max_value)}")
    return ", ".join(parts) if parts else f"{label} 제한 없음 또는 미구조화"


def _credit_rule(policy: PolicyProduct) -> str:
    if policy.credit_score_min is None and policy.credit_score_max is None:
        return "신용 조건 없음 또는 공개자료 미구조화"
    low = policy.credit_score_min if policy.credit_score_min is not None else "하한 없음"
    high = policy.credit_score_max if policy.credit_score_max is not None else "상한 없음"
    return f"{low} ~ {high}"


def _base_row(policy: PolicyProduct, rule_item: str, structured_content: str, system_process: str, data_fields: str) -> dict[str, Any]:
    return {
        "policy_id": policy.policy_id,
        "제도명": policy.policy_name,
        "기관": policy.institution,
        "정책유형": policy.policy_type,
        "규칙항목": rule_item,
        "구조화 내용": structured_content,
        "시스템 처리": system_process,
        "고객 프로필 필드": data_fields,
        "규칙버전": policy.rule_version,
        "검수상태": policy.rule_review_status,
        "공개자료 범위": policy.public_rule_scope,
        "출처명": policy.source_name,
        "출처URL": policy.source_url,
        "출처기준일": policy.source_date,
        "샘플데이터": policy.is_sample_data,
    }


def build_policy_rule_rows(policies: list[PolicyProduct]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for policy in policies:
        rows.extend([
            _base_row(
                policy,
                "사업장 소재지",
                _join(policy.allowed_regions, "지역 제한 없음 또는 미구조화"),
                "고객 사업장 지역과 허용 지역을 비교",
                "region",
            ),
            _base_row(
                policy,
                "사업자 형태",
                _join(policy.allowed_business_types),
                "개인사업자/법인사업자 등 허용 대상과 비교. 미구조화 시 추가 확인 필요",
                "business_type",
            ),
            _base_row(
                policy,
                "업종·제외업종",
                f"허용: {_join(policy.allowed_industries, '제한 없음 또는 미구조화')} / 제외: {_join(policy.excluded_industries, '없음 또는 미구조화')}",
                "업종 키워드 또는 업종코드와 허용·제외 목록을 비교",
                "industry",
            ),
            _base_row(
                policy,
                "업력 기준",
                _business_month_rule(policy),
                "상담 기준일과 개업일/업력 개월 수로 기간 계산",
                "business_start_date, business_months",
            ),
            _base_row(
                policy,
                "매출 기준",
                _amount_rule(policy.min_revenue, policy.max_revenue, "매출"),
                "최근 1년 또는 공고 기준기간의 매출 증빙과 비교",
                "annual_revenue, monthly_revenue",
            ),
            _base_row(
                policy,
                "신용 기준",
                _credit_rule(policy),
                "신용점수·신용구간이 공개 기준에 해당하는지 비교",
                "credit_score, credit_band",
            ),
            _base_row(
                policy,
                "자금 목적",
                _join(policy.funding_purposes, "자금 목적 제한 없음 또는 미구조화"),
                "고객 발언의 자금 용도를 분류하고 상담자 확인 후 비교",
                "funding_purpose",
            ),
            _base_row(
                policy,
                "신청기간",
                _period(policy),
                "상담 기준일이 공개 신청기간 안에 있는지 비교",
                "consultation_date",
            ),
            _base_row(
                policy,
                "공개 지원한도",
                format_amount(policy.max_amount) if policy.max_amount else "공개 한도 없음 또는 미구조화",
                "공개 한도와 고객 요청금액을 참고 비교. 개인별 한도는 판단하지 않음",
                "required_amount",
            ),
            _base_row(
                policy,
                "필요서류",
                _join(policy.required_documents, "필요서류 미구조화"),
                "기본·조건부 제출서류를 체크리스트로 생성",
                "uploaded_documents, checklist_items",
            ),
            _base_row(
                policy,
                "중복지원·제외조건",
                f"중복: {policy.duplicate_support_restriction or '제한 없음 또는 미구조화'} / 제외: {_join(policy.exclusion_conditions, '없음 또는 미구조화')}",
                "기존 보증·대출, 체납, 휴폐업 등 공개 제외조건과 비교",
                "existing_guarantee, existing_loan, tax_arrears, business_status",
            ),
            _base_row(
                policy,
                "내부심사 항목",
                _join(policy.rule_limitations, "내부심사·예외·재량 항목 미구조화"),
                "공개자료에 없는 판단요소는 비교하지 않고 추가 확인 필요로 표시",
                "human_review_required",
            ),
        ])
    return rows


def build_policy_rule_table(policies: list[PolicyProduct]) -> pd.DataFrame:
    return pd.DataFrame(build_policy_rule_rows(policies))


def rule_table_summary(rule_df: pd.DataFrame) -> dict[str, int]:
    if rule_df.empty:
        return {"policies": 0, "rule_rows": 0, "needs_review": 0, "sample_sources": 0}
    needs_review = rule_df["구조화 내용"].astype(str).str.contains("미구조화|대조 필요", regex=True).sum()
    return {
        "policies": int(rule_df["policy_id"].nunique()),
        "rule_rows": int(len(rule_df)),
        "needs_review": int(needs_review),
        "sample_sources": int(rule_df.drop_duplicates("policy_id")["샘플데이터"].sum()),
    }
