"""Report and aftercare Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RequiredDocumentItem(BaseModel):
    document_name: str
    reason: str
    required_for: str | None = None
    priority: str = "중간"
    how_to_prepare: str | None = None


class AftercareTask(BaseModel):
    task_name: str
    owner: str
    due_date: str | None = None
    reason: str
    status: str = "예정"


class ReviewReport(BaseModel):
    report_title: str
    case_id: str
    customer_name: str | None = None
    business_name: str | None = None
    counselor_summary: str
    business_overview: str
    funding_needs: str
    verified_information: list[str]
    missing_information: list[str]
    recommended_policies: list[str]
    conditional_policies: list[str]
    exclusion_risks: list[str]
    required_documents: list[RequiredDocumentItem]
    next_actions: list[str]
    aftercare_tasks: list[AftercareTask]
    compliance_notes: list[str]
    caution_message: str


class NotificationPayload(BaseModel):
    recipient_name: str | None = None
    recipient_phone: str | None = None
    recipient_email: str | None = None
    message_type: str = "mock_kakao_alimtalk"
    message_title: str
    message_body: str
    required_documents: list[RequiredDocumentItem]
    application_links: list[str] = Field(default_factory=list)
    caution_message: str


class NotificationSendResult(BaseModel):
    success: bool
    mode: str
    provider: str
    message: str
    payload_preview: dict
