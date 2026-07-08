"""Formatting utilities."""

from __future__ import annotations


def format_amount(amount: int | None) -> str:
    if amount is None:
        return "미확인"
    if amount >= 100_000_000:
        eok = amount / 100_000_000
        if eok == int(eok):
            return f"{int(eok)}억 원"
        return f"{eok:.1f}억 원"
    if amount >= 10_000:
        man = amount / 10_000
        if man == int(man):
            return f"{int(man):,}만 원"
        return f"{man:,.0f}만 원"
    return f"{amount:,}원"


def format_months(months: int | None) -> str:
    if months is None:
        return "미확인"
    if months >= 12:
        years = months // 12
        rem = months % 12
        if rem == 0:
            return f"{years}년"
        return f"{years}년 {rem}개월"
    return f"{months}개월"


def status_badge(status: str) -> str:
    icons = {
        "검토 가능": "✅",
        "조건부 검토": "🔵",
        "제외 가능성": "⚠️",
        "판단 보류": "⏸️",
        "확인됨": "✓",
        "미확인": "?",
        "추가 확인 필요": "!",
        "충족": "✓",
        "미충족": "✗",
    }
    return f"{icons.get(status, '')} {status}"
