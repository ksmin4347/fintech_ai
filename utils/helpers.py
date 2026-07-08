"""Shared helpers for dict / Pydantic objects."""

from __future__ import annotations

from models.schemas import MissingInfoItem, NextQuestion


def get_attr_or_key(obj, attr: str, default: str = "") -> str:
    """Safely read attribute from Pydantic model or dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return str(obj.get(attr, default) or default)
    model_dump = getattr(obj, "model_dump", None)
    if callable(model_dump):
        return str(model_dump().get(attr, default) or default)
    try:
        val = getattr(obj, attr)
    except AttributeError:
        return default
    return str(val) if val is not None else default


def ensure_missing_info_items(items: list) -> list[MissingInfoItem]:
    result: list[MissingInfoItem] = []
    for item in items or []:
        if isinstance(item, MissingInfoItem):
            result.append(item)
        elif isinstance(item, dict):
            result.append(MissingInfoItem(**item))
        elif callable(getattr(item, "model_dump", None)):
            result.append(MissingInfoItem(**item.model_dump()))
    return result


def ensure_next_questions(items: list) -> list[NextQuestion]:
    result: list[NextQuestion] = []
    for item in items or []:
        if isinstance(item, NextQuestion):
            result.append(item)
        elif isinstance(item, dict):
            result.append(NextQuestion(**item))
        elif callable(getattr(item, "model_dump", None)):
            result.append(NextQuestion(**item.model_dump()))
    return result
