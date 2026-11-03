"""Dashboard aggregation service. All values are derived from MySQL records."""
from __future__ import annotations

from datetime import date, timedelta

from database import db
from models.serializers import serialize_transaction
from services.budget_service import get_budgets
from utils.dates import (
    add_months,
    month_bounds,
    month_label,
    previous_period,
    resolve_range,
    today,
)


def _aggregate_period(user_id: int, start: date, end: date) -> dict:
    rows = db.fetch_all(
        """
        SELECT type, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
        FROM transactions
        WHERE user_id = %s AND date BETWEEN %s AND %s
        GROUP BY type
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )
    income = 0.0
    expenses = 0.0
    count = 0
    for row in rows:
        count += int(row["count"] or 0)
        if row["type"] == "Income":
            income = float(row["total"] or 0)
        elif row["type"] == "Expense":
            expenses = float(row["total"] or 0)
    return {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "balance": round(income - expenses, 2),
        "count": count,
        "savings_rate": round(((income - expenses) / income) * 100, 1) if income > 0 else 0,
    }


def _change(current: float, previous: float) -> float:
    if previous == 0:
        return 0 if current == 0 else 100.0
    return round(((current - previous) / abs(previous)) * 100, 1)


def _monthly_series(user_id: int, end_year: int, end_month: int, count: int = 12) -> list[dict]:
    start_year, start_month = add_months(end_year, end_month, -(count - 1))
    start = date(start_year, start_month, 1)
    end = month_bounds(end_year, end_month)[1]
    rows = db.fetch_all(
        """
        SELECT date, type, amount
        FROM transactions
        WHERE user_id = %s AND date BETWEEN %s AND %s
        ORDER BY date ASC
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )

    buckets: dict[str, dict] = {}
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for index in range(count):
        year, month = add_months(start_year, start_month, index)
        key = month_label(year, month)
        buckets[key] = {
            "month": key,
            "label": f"{month_names[month - 1]} {str(year)[2:]}",
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
        }

    for row in rows:
        key = str(row["date"])[:7]
        if key not in buckets:
            continue
        amount = float(row["amount"] or 0)
        if row["type"] == "Income":
            buckets[key]["income"] += amount
        else:
            buckets[key]["expenses"] += amount

    result = []
    for bucket in buckets.values():
        bucket["income"] = round(bucket["income"], 2)
        bucket["expenses"] = round(bucket["expenses"], 2)
        bucket["savings"] = round(bucket["income"] - bucket["expenses"], 2)
        result.append(bucket)
    return result


def _category_breakdown(user_id: int, start: date, end: date) -> list[dict]:
    rows = db.fetch_all(
        """
        SELECT category, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
        FROM transactions
        WHERE user_id = %s AND type = 'Expense' AND date BETWEEN %s AND %s
        GROUP BY category
        ORDER BY total DESC
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )
    total = sum(float(row["total"] or 0) for row in rows)
    result = []
    for row in rows:
        amount = round(float(row["total"] or 0), 2)
        result.append(
            {
                "category": row["category"],
                "amount": amount,
                "count": int(row["count"] or 0),
                "percentage": round((amount / total) * 100, 1) if total > 0 else 0,
            }
        )
    return result


def _weekly_spending(user_id: int, start: date, end: date) -> list[dict]:
    rows = db.fetch_all(
        """
        SELECT date, amount FROM transactions
        WHERE user_id = %s AND type = 'Expense' AND date BETWEEN %s AND %s
        ORDER BY date ASC
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )
    buckets: dict[tuple[int, int], dict] = {}
    for row in rows:
        raw = str(row["date"])[:10]
        try:
            current = date.fromisoformat(raw)
        except ValueError:
            continue
        iso_year, iso_week, iso_day = current.isocalendar()
        key = (iso_year, iso_week)
        if key not in buckets:
            week_start = current - timedelta(days=current.weekday())
            buckets[key] = {
                "week": f"W{iso_week}",
                "label": week_start.strftime("%d %b"),
                "spending": 0.0,
                "start": week_start.isoformat(),
            }
        buckets[key]["spending"] += float(row["amount"] or 0)
    result = list(buckets.values())
    for item in result:
        item["spending"] = round(item["spending"], 2)
    result.sort(key=lambda item: item["start"])
    return result


def _recent_transactions(user_id: int, start: date, end: date, limit: int = 6) -> list[dict]:
    rows = db.fetch_all(
        """
        SELECT * FROM transactions
        WHERE user_id = %s AND date BETWEEN %s AND %s
        ORDER BY date DESC, transaction_id DESC
        LIMIT %s
        """,
        (user_id, start.isoformat(), end.isoformat(), limit),
    )
    return [serialize_transaction(row) for row in rows]


def get_dashboard(user_id: int, args) -> dict:
    period = resolve_range(args)
    start = period["start_date"]
    end = period["end_date"]
    current = _aggregate_period(user_id, start, end)

    previous_start, previous_end = previous_period(start, end)
    previous = _aggregate_period(user_id, previous_start, previous_end)

    now = today()
    current_month_start, current_month_end = month_bounds(now.year, now.month)
    current_month = _aggregate_period(user_id, current_month_start, current_month_end)

    budget_data = get_budgets(user_id, month_label(now.year, now.month))
    categories = _category_breakdown(user_id, start, end)

    top_merchants = db.fetch_all(
        """
        SELECT merchant, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE user_id = %s AND type = 'Expense' AND date BETWEEN %s AND %s
          AND merchant IS NOT NULL AND merchant <> ''
        GROUP BY merchant
        ORDER BY total DESC
        LIMIT 5
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )

    return {
        "range": {
            "key": period["key"],
            "label": period["label"],
            "start": period["start"],
            "end": period["end"],
        },
        "summary": {
            "total_income": current["income"],
            "total_expenses": current["expenses"],
            "available_balance": current["balance"],
            "monthly_savings": current_month["balance"],
            "monthly_budget": budget_data["summary"]["total_budget"],
            "total_transactions": current["count"],
            "savings_rate": current_month["savings_rate"],
            "budget_utilization": budget_data["summary"]["utilization"],
        },
        "comparisons": {
            "income_change": _change(current["income"], previous["income"]),
            "expense_change": _change(current["expenses"], previous["expenses"]),
            "balance_change": _change(current["balance"], previous["balance"]),
            "transaction_change": _change(current["count"], previous["count"]),
        },
        "current_month": {
            "month": month_label(now.year, now.month),
            "income": current_month["income"],
            "expenses": current_month["expenses"],
            "savings": current_month["balance"],
            "transactions": current_month["count"],
        },
        "monthly_series": _monthly_series(user_id, now.year, now.month, count=12),
        "category_breakdown": categories,
        "top_categories": categories[:5],
        "weekly_spending": _weekly_spending(user_id, start, end),
        "recent_transactions": _recent_transactions(user_id, start, end),
        "budget_utilization": budget_data["budgets"],
        "budget_summary": budget_data["summary"],
        "top_merchants": [
            {"merchant": row["merchant"], "amount": round(float(row["total"] or 0), 2)}
            for row in top_merchants
        ],
        "generated_at": date.today().isoformat(),
    }
