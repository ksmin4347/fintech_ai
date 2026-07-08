"""Privacy masking utilities."""

from __future__ import annotations

import re


def mask_phone_number(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 4:
        return "***"
    return digits[:3] + "-****-" + digits[-4:]


def mask_customer_name(name: str) -> str:
    if not name:
        return ""
    if len(name) <= 1:
        return "*"
    return name[0] + "*" * (len(name) - 1)


def mask_sensitive_text(text: str) -> str:
    if not text:
        return ""
    masked = re.sub(r"(\d{3})-?(\d{3,4})-?(\d{4})", r"\1-****-\3", text)
    return masked
