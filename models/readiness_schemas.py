"""Application readiness package models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from models.report_schemas import AftercareTask, RequiredDocumentItem


class ProfileEvidenceItem(BaseModel):
    field_name: str
    field_label: str
    value: str
    information_source: str
    verification_status: str
    basis_period: str | None = None
    evidence: str = ""
    evidence_location: str = ""
    updated_by: str = ""
    approved_by: str = ""
    next_action: str = ""


class RuleComparisonItem(BaseModel):
    policy_id: str
    policy_name: str
    institution: str
    condition_name: str
    public_status: str
    customer_value: str
    public_requirement: str
    reason: str
    evidence: str = ""
    source_name: str = ""
    source_url: str = ""
    source_date: str = ""


class ReadinessPackage(BaseModel):
    package_title: str = "신청 준비 패키지"
    case_id: str
    customer_name: str | None = None
    business_name: str | None = None
    package_status: str
    readiness_summary: str
    profile_items: list[ProfileEvidenceItem] = Field(default_factory=list)
    rule_comparisons: list[RuleComparisonItem] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    required_documents: list[RequiredDocumentItem] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    aftercare_tasks: list[AftercareTask] = Field(default_factory=list)
    source_warnings: list[str] = Field(default_factory=list)
    compliance_notes: list[str] = Field(default_factory=list)
