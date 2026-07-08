"""Missing information detection."""

from __future__ import annotations

from models.schemas import BusinessCase, MissingInfoItem
from utils.constants import REQUIRED_FIELDS, UNKNOWN


def detect_missing_info(case: BusinessCase) -> list[MissingInfoItem]:
    items: list[MissingInfoItem] = []
    for field, label, reason, question in REQUIRED_FIELDS:
        val = getattr(case, field, None)
        if val is None or val == "" or val == UNKNOWN:
            items.append(
                MissingInfoItem(
                    field_name=field,
                    field_label=label,
                    current_status=UNKNOWN,
                    reason=reason,
                    sample_question=question,
                )
            )
        elif case.field_status.get(field) == "추가 확인 필요":
            items.append(
                MissingInfoItem(
                    field_name=field,
                    field_label=label,
                    current_status="추가 확인 필요",
                    reason=reason,
                    sample_question=question,
                )
            )
    return items
