"""Pydantic data models for SOHO Finance Copilot."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class FieldStatus(str, Enum):
    CONFIRMED = "확인됨"
    UNKNOWN = "미확인"
    NEEDS_CONFIRMATION = "추가 확인 필요"


class ConditionResultStatus(str, Enum):
    MET = "충족"
    NOT_MET = "미충족"
    UNKNOWN = "미확인"
    NEEDS_CONFIRMATION = "추가 확인 필요"
    NOT_APPLICABLE = "해당 없음"


class EligibilityStatus(str, Enum):
    REVIEWABLE = "검토 가능"
    CONDITIONAL = "조건부 검토"
    EXCLUDED = "제외 가능성"
    PENDING = "판단 보류"


class QuestionPriority(str, Enum):
    HIGH = "높음"
    MEDIUM = "중간"
    LOW = "낮음"


UNKNOWN = "미확인"


class BusinessCase(BaseModel):
    case_id: str = ""
    customer_name: str = ""
    business_name: str = ""
    raw_consultation: str = ""
    consultation_memo: str = ""
    transcript: str | None = None  # 향후 STT 결과 입력용
    consultation_date: Optional[date] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    business_type: Optional[str] = None
    business_start_date: Optional[str] = None
    business_months: Optional[int] = None
    annual_revenue: Optional[int] = None
    monthly_revenue: Optional[int] = None
    revenue_trend: Optional[str] = None
    funding_purpose: Optional[str] = None
    required_amount: Optional[int] = None
    existing_loan: Optional[str] = None
    existing_guarantee: Optional[str] = None
    credit_score: Optional[int] = None
    credit_band: Optional[str] = None
    collateral: Optional[str] = None
    tax_arrears: Optional[str] = None
    business_status: Optional[str] = None
    requested_timeline: Optional[str] = None
    special_notes: Optional[str] = None
    field_evidence: dict[str, str] = Field(default_factory=dict)
    field_status: dict[str, str] = Field(default_factory=dict)
    field_source: dict[str, str] = Field(default_factory=dict)
    field_basis_period: dict[str, str] = Field(default_factory=dict)
    field_evidence_location: dict[str, str] = Field(default_factory=dict)
    field_updated_by: dict[str, str] = Field(default_factory=dict)
    field_approved_by: dict[str, str] = Field(default_factory=dict)
    field_audit_log: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def get_value(self, field: str) -> Any:
        val = getattr(self, field, None)
        if val is None or val == "":
            return UNKNOWN
        return val

    def is_unknown(self, field: str) -> bool:
        val = getattr(self, field, None)
        return val is None or val == "" or val == UNKNOWN


class PolicyProduct(BaseModel):
    policy_id: str
    policy_name: str
    institution: str
    policy_type: str
    target_description: str = ""
    allowed_industries: list[str] = Field(default_factory=list)
    excluded_industries: list[str] = Field(default_factory=list)
    allowed_regions: list[str] = Field(default_factory=list)
    allowed_business_types: list[str] = Field(default_factory=list)
    min_business_months: Optional[int] = None
    max_business_months: Optional[int] = None
    min_revenue: Optional[int] = None
    max_revenue: Optional[int] = None
    credit_score_min: Optional[int] = None
    credit_score_max: Optional[int] = None
    funding_purposes: list[str] = Field(default_factory=list)
    max_amount: Optional[int] = None
    interest_or_fee_description: str = ""
    guarantee_description: str = ""
    application_start_date: Optional[str] = None
    application_end_date: Optional[str] = None
    required_documents: list[str] = Field(default_factory=list)
    duplicate_support_restriction: str = ""
    exclusion_conditions: list[str] = Field(default_factory=list)
    source_name: str = ""
    source_url: str = ""
    source_date: str = ""
    rule_version: str = "v0.1-demo"
    rule_review_status: str = "대학생 MVP 규칙"
    public_rule_scope: str = "공개 대상·제외조건·신청기간·필요서류 기준"
    rule_limitations: list[str] = Field(default_factory=lambda: ["내부심사", "예외", "재량", "개인별 한도", "금리 판단 제외"])
    is_sample_data: bool = True
    notes: str = ""


class ConditionResult(BaseModel):
    condition_name: str
    customer_value: str
    policy_requirement: str
    result: str
    reason: str
    evidence: str = ""
    needs_confirmation: bool = False


class EligibilityResult(BaseModel):
    policy_id: str
    policy_name: str
    institution: str
    final_status: str
    summary_reason: str = ""
    condition_results: list[ConditionResult] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    exclusion_reasons: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    source: dict[str, str] = Field(default_factory=dict)


class MissingInfoItem(BaseModel):
    field_name: str
    field_label: str
    current_status: str
    reason: str
    sample_question: str

    def get(self, key: str, default=None):
        return getattr(self, key, default)


class NextQuestion(BaseModel):
    question: str
    reason: str
    related_policy: str
    priority: str

    def get(self, key: str, default=None):
        return getattr(self, key, default)
