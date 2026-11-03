"""Formatting helpers for API messages, reports and exports."""
from __future__ import annotations

from datetime import date


def to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_inr(value, symbol: bool = True) -> str:
    amount = to_float(value)
    negative = amount < 0
    amount = abs(amount)
    rounded = f"{amount:.0f}"
    if len(rounded) <= 3:
        grouped = rounded
    else:
        last_three = rounded[-3:]
        rest = rounded[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last_three
    prefix = "₹" if symbol else "INR "
    return f"{'-' if negative else ''}{prefix}{grouped}"


def pct(change: float) -> float:
    return round(change, 1)


def safe_month_label(value: date) -> str:
    return value.strftime("%b %Y")


def human_date(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y")
    return str(value)
