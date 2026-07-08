"""Date utilities for aftercare tasks."""

from __future__ import annotations

from datetime import date, timedelta


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, 28)
    return date(year, month, day)


def format_due_date(days_from_now: int, base: date | None = None) -> str:
    base = base or date.today()
    return (base + timedelta(days=days_from_now)).isoformat()
