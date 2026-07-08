"""RAG-related Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PolicyDocument(BaseModel):
    doc_id: str
    title: str
    institution: str | None = None
    file_path: str
    source_name: str | None = None
    source_url: str | None = None
    source_date: str | None = None
    is_sample_data: bool = True
    raw_text: str


class RagChunk(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    text: str
    metadata: dict = Field(default_factory=dict)


class RetrievedEvidence(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    text: str
    score: float
    source_name: str | None = None
    source_url: str | None = None
    source_date: str | None = None
    is_sample_data: bool = True


class CuratedPolicyRecommendation(BaseModel):
    policy_name: str
    institution: str
    priority_rank: int
    fit_score: float
    review_status: str
    why_recommended: list[str]
    matched_conditions: list[str]
    missing_or_uncertain_conditions: list[str]
    exclusion_risks: list[str]
    required_documents: list[str]
    next_actions: list[str]
    evidence: list[RetrievedEvidence]
    caution_message: str
