"""Aftercare task manager."""

from __future__ import annotations

from models.rag_schemas import CuratedPolicyRecommendation
from models.report_schemas import AftercareTask
from models.schemas import BusinessCase
from pydantic import BaseModel
from utils.dates import format_due_date


def _raw_attr_or_key(obj, attr: str, default=None):
    """Read a raw value from dicts, Pydantic models, or plain objects."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    if isinstance(obj, BaseModel):
        return obj.model_dump().get(attr, default)
    try:
        return getattr(obj, attr)
    except AttributeError:
        return default


def generate_aftercare_tasks(
    case: BusinessCase,
    recommendations: list[CuratedPolicyRecommendation],
    missing_info: list,
    gap_analysis: list | None = None,
) -> list[AftercareTask]:
    tasks: list[AftercareTask] = []
    missing_fields = set()
    for item in missing_info or []:
        field_name = _raw_attr_or_key(item, "field_name", "")
        if field_name:
            missing_fields.add(str(field_name))

    field_tasks = {
        "region": ("사업장 소재지 확인", "상담자", "지역별 상품 매칭"),
        "business_months": ("사업자등록증상 개업일 확인", "고객", "업력 조건 검토"),
        "annual_revenue": ("최근 1년 매출자료 요청", "고객", "매출 기준 확인"),
        "existing_guarantee": ("기존 보증 이용 여부 확인", "고객", "중복지원 검토"),
        "tax_arrears": ("세금 체납 여부 확인", "고객", "제외조건 검토"),
        "credit_band": ("신용평점 구간 확인", "고객", "신용 조건 검토"),
    }

    for field, (name, owner, reason) in field_tasks.items():
        if field in missing_fields:
            tasks.append(AftercareTask(
                task_name=name, owner=owner, due_date=format_due_date(7),
                reason=reason, status="예정",
            ))

    for rec in recommendations:
        if rec.review_status in ("검토 가능", "조건부 검토"):
            tasks.append(AftercareTask(
                task_name=f"{rec.policy_name} 공식 공고 재확인",
                owner="상담자", due_date=format_due_date(3),
                reason="신청기한·조건 최신화", status="예정",
            ))

    if gap_analysis:
        for gap in gap_analysis:
            recoverable = _raw_attr_or_key(gap, "recoverable", [])
            alternatives = _raw_attr_or_key(gap, "alternatives", [])
            policy_name = _raw_attr_or_key(gap, "policy_name", "")

            if recoverable:
                tasks.append(AftercareTask(
                    task_name=f"{policy_name} 업력 조건 재검토",
                    owner="시스템", due_date=format_due_date(120),
                    reason="업력 조건 충족 예상 시점", status="예정",
                ))
            if alternatives:
                tasks.append(AftercareTask(
                    task_name="대체 상품 상담 연결",
                    owner="상담자", due_date=format_due_date(14),
                    reason="대체 검토 상품 안내", status="예정",
                ))

    tasks.append(AftercareTask(
        task_name="고객 안내문 및 서류 체크리스트 전달",
        owner="상담자", due_date=format_due_date(1),
        reason="후속 상담 준비", status="예정",
    ))

    seen = set()
    unique: list[AftercareTask] = []
    for t in tasks:
        key = t.task_name
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique[:12]
