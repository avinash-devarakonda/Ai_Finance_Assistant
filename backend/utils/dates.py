"""Date range and month helpers used across dashboard, reports and forecasts."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta


RANGE_LABELS = {
    "this_week": "This Week",
    "this_month": "This Month",
    "last_month": "Last Month",
    "last_3_months": "Last 3 Months",
    "this_year": "This Year",
    "all": "All Time",
    "custom": "Custom Range",
}


def today() -> date:
    return date.today()


def to_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_month(value: str | None) -> tuple[int, int]:
    if not value:
        current = today()
        return current.year, current.month
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise ValueError("Month must use YYYY-MM format") from exc
    return parsed.year, parsed.month


def month_label(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    return first_day, last_day


def previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def add_months(year: int, month: int, offset: int) -> tuple[int, int]:
    base = year * 12 + (month - 1) + offset
    return base // 12, base % 12 + 1


def month_sequence(end_year: int, end_month: int, count: int) -> list[tuple[int, int]]:
    start_year, start_month = add_months(end_year, end_month, -(count - 1))
    return [add_months(start_year, start_month, offset) for offset in range(count)]


def resolve_range(args) -> dict:
    """Resolve ?range=...&date_from=...&date_to=... into an inclusive range."""
    range_key = (args.get("range") or "this_month").strip().lower()
    if range_key not in RANGE_LABELS:
        range_key = "this_month"

    end = today()
    if range_key == "custom":
        start = to_date(args.get("date_from"))
        custom_end = to_date(args.get("date_to"))
        if not start or not custom_end:
            raise ValueError("Custom range requires date_from and date_to")
        if start > custom_end:
            raise ValueError("date_from cannot be after date_to")
        end = custom_end
        label = f"{start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')}"
    elif range_key == "this_week":
        start = end - timedelta(days=end.weekday())
        label = RANGE_LABELS[range_key]
    elif range_key == "this_month":
        start = end.replace(day=1)
        label = RANGE_LABELS[range_key]
    elif range_key == "last_month":
        first_this_month = end.replace(day=1)
        previous_end = first_this_month - timedelta(days=1)
        start = previous_end.replace(day=1)
        end = previous_end
        label = RANGE_LABELS[range_key]
    elif range_key == "last_3_months":
        first_this_month = end.replace(day=1)
        start_year, start_month = add_months(first_this_month.year, first_this_month.month, -2)
        start = date(start_year, start_month, 1)
        label = RANGE_LABELS[range_key]
    elif range_key == "this_year":
        start = date(end.year, 1, 1)
        label = RANGE_LABELS[range_key]
    else:
        start = date(2000, 1, 1)
        label = RANGE_LABELS[range_key]

    return {
        "key": range_key,
        "label": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "start_date": start,
        "end_date": end,
    }


def previous_period(start: date, end: date) -> tuple[date, date]:
    length = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=length - 1)
    return previous_start, previous_end


def month_key(value: date) -> str:
    return value.strftime("%Y-%m")
