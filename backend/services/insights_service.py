"""Rule-based AI financial insights powered only by the user's own records."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from config import Config
from database import db
from services.budget_service import get_budgets
from services.forecast_service import ForecastUnavailableError, user_forecast
from utils.dates import month_bounds, month_label, previous_month, today
from utils.formatters import format_inr

TEMPLATES: dict[str, str] = {}


def load_templates() -> dict[str, str]:
    global TEMPLATES
    if TEMPLATES:
        return TEMPLATES
    path = Path(Config.INSIGHTS_DATASET)
    if not path.exists():
        TEMPLATES = {}
        return TEMPLATES
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        TEMPLATES = {
            row["condition"].strip(): row["insight"].strip()
            for row in reader
            if row.get("condition") and row.get("insight")
        }
    return TEMPLATES


def _text(condition: str, fallback: str, **kwargs) -> str:
    template = load_templates().get(condition, fallback)
    try:
        return template.format(**kwargs)
    except KeyError:
        return fallback.format(**kwargs)


def _period_totals(user_id: int, start: date, end: date) -> dict:
    rows = db.fetch_all(
        """
        SELECT type, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
        FROM transactions
        WHERE user_id = %s AND date BETWEEN %s AND %s
        GROUP BY type
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )
    result = {"income": 0.0, "expenses": 0.0, "count": 0}
    for row in rows:
        result["count"] += int(row["count"] or 0)
        if row["type"] == "Income":
            result["income"] = float(row["total"] or 0)
        else:
            result["expenses"] = float(row["total"] or 0)
    return result


def _category_totals(user_id: int, start: date, end: date) -> dict[str, float]:
    rows = db.fetch_all(
        """
        SELECT category, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE user_id = %s AND type = 'Expense' AND date BETWEEN %s AND %s
        GROUP BY category
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )
    return {row["category"]: float(row["total"] or 0) for row in rows}


def _append(insights: list[dict], text: str, severity: str, condition: str, icon: str = "sparkles") -> None:
    if not any(item["text"] == text for item in insights):
        insights.append(
            {
                "text": text,
                "severity": severity,
                "condition": condition,
                "icon": icon,
            }
        )


def generate_insights(user_id: int, month: str | None = None) -> list[dict]:
    now = today()
    if month:
        try:
            year, month_number = (int(part) for part in month.split("-", 1))
        except (ValueError, TypeError):
            year, month_number = now.year, now.month
    else:
        year, month_number = now.year, now.month

    start, end = month_bounds(year, month_number)
    prev_year, prev_month = previous_month(year, month_number)
    prev_start, prev_end = month_bounds(prev_year, prev_month)

    current = _period_totals(user_id, start, end)
    previous = _period_totals(user_id, prev_start, prev_end)
    current_categories = _category_totals(user_id, start, end)
    previous_categories = _category_totals(user_id, prev_start, prev_end)
    month_value = f"{year:04d}-{month_number:02d}"
    insights: list[dict] = []

    if current["count"] == 0 and previous["count"] == 0:
        _append(
            insights,
            _text("no_transactions", "No transactions found for this period. Add your first transaction to get insights."),
            "info",
            "no_transactions",
            "receipt",
        )
        return insights

    category_labels = {
        "Food": "food",
        "Transport": "transport",
        "Shopping": "shopping",
        "Bills": "bills",
        "Entertainment": "entertainment",
        "Health": "health",
        "Education": "education",
        "Other": "other",
    }

    # Month-over-month category movements (only where both records support a comparison).
    movements = []
    for category, label in category_labels.items():
        curr = current_categories.get(category, 0)
        prev = previous_categories.get(category, 0)
        if prev > 0 and curr > 0:
            change = ((curr - prev) / prev) * 100
            if abs(change) >= 10 and max(curr, prev) >= 500:
                movements.append((abs(change), category, label, change, curr))
    movements.sort(reverse=True)
    for _, category, label, change, _amount in movements[:3]:
        condition = f"{label}_{'up' if change > 0 else 'down'}"
        fallback = (
            f"Your {label} expenses increased by {{change}}% compared with last month."
            if change > 0
            else f"Your {label} expenses decreased by {{change}}% compared with last month."
        )
        _append(
            insights,
            _text(condition, fallback, change=abs(round(change, 1))),
            "warning" if change > 0 else "positive",
            condition,
            "trending-up" if change > 0 else "trending-down",
        )

    income = current["income"]
    expenses = current["expenses"]
    if expenses > 0:
        highest_category, highest_amount = max(current_categories.items(), key=lambda item: item[1])
        _append(
            insights,
            _text(
                "highest_category",
                "Your highest spending category is {category} at INR {amount}.",
                category=highest_category,
                amount=format_inr(highest_amount, symbol=False),
            ),
            "info",
            "highest_category",
            "pie-chart",
        )

    if income > 0 and expenses > income:
        _append(
            insights,
            _text("expenses_over_income", "Your expenses are higher than your income this month."),
            "danger",
            "expenses_over_income",
            "alert-triangle",
        )

    if income > 0:
        savings = income - expenses
        rate = round((savings / income) * 100, 1)
        _append(
            insights,
            _text(
                "savings_rate",
                "Your savings rate this month is {rate}% of your income.",
                rate=rate,
            ),
            "positive" if rate >= 20 else "warning",
            "savings_rate",
            "piggy-bank",
        )
        if previous["income"] > 0:
            previous_savings = previous["income"] - previous["expenses"]
            difference = savings - previous_savings
            if abs(difference) >= 500:
                if difference > 0:
                    _append(
                        insights,
                        _text(
                            "savings_improved",
                            "Your monthly savings improved by INR {amount} compared with last month.",
                            amount=format_inr(abs(difference), symbol=False),
                        ),
                        "positive",
                        "savings_improved",
                        "arrow-up-right",
                    )
                else:
                    _append(
                        insights,
                        _text(
                            "savings_declined",
                            "Your monthly savings declined by INR {amount} compared with last month.",
                            amount=format_inr(abs(difference), symbol=False),
                        ),
                        "warning",
                        "savings_declined",
                        "arrow-down-right",
                    )

    # Budget findings are based on actual transaction spend, never sample values.
    budgets = get_budgets(user_id, month_value)
    if budgets["budgets"]:
        exceeded = [item for item in budgets["budgets"] if item["status"] == "exceeded"]
        warning = [item for item in budgets["budgets"] if item["status"] == "warning"]
        for item in exceeded[:2]:
            _append(
                insights,
                _text(
                    "category_exceeded",
                    "You have exceeded your {category} budget by INR {amount}.",
                    category=item["category"],
                    amount=format_inr(abs(item["remaining"]), symbol=False),
                ),
                "danger",
                "category_exceeded",
                "circle-alert",
            )
        for item in warning[:2]:
            _append(
                insights,
                _text(
                    "category_near_limit",
                    "Your {category} budget is {percent}% utilized. You are close to the limit.",
                    category=item["category"],
                    percent=round(item["utilization"], 1),
                ),
                "warning",
                "category_near_limit",
                "gauge",
            )
        if exceeded:
            _append(
                insights,
                _text(
                    "budget_exceeded_count",
                    "You have exceeded {count} category budget(s) this month.",
                    count=len(exceeded),
                ),
                "danger",
                "budget_exceeded_count",
                "circle-alert",
            )
        on_track = len(budgets["budgets"]) - len(exceeded) - len(warning)
        if on_track > 0:
            _append(
                insights,
                _text(
                    "budget_on_track",
                    "You are within budget in {count} categories this month. Keep it up.",
                    count=on_track,
                ),
                "positive",
                "budget_on_track",
                "circle-check",
            )
    elif current["count"] > 0:
        _append(
            insights,
            _text(
                "no_budget",
                "You have not set budgets for {month}. Add budgets to track spending limits.",
                month=date(year, month_number, 1).strftime("%B %Y"),
            ),
            "info",
            "no_budget",
            "target",
        )

    # Top merchant from actual records.
    merchant_row = db.fetch_one(
        """
        SELECT merchant, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE user_id = %s AND type = 'Expense' AND date BETWEEN %s AND %s
          AND merchant IS NOT NULL AND merchant <> ''
        GROUP BY merchant
        ORDER BY total DESC
        LIMIT 1
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )
    if merchant_row and float(merchant_row["total"] or 0) > 0:
        _append(
            insights,
            _text(
                "top_merchant",
                "Your top merchant this month is {merchant}, with spending of INR {amount}.",
                merchant=merchant_row["merchant"],
                amount=format_inr(merchant_row["total"], symbol=False),
            ),
            "info",
            "top_merchant",
            "store",
        )

    if income > 0:
        _append(
            insights,
            _text(
                "income_added",
                "Your income this month is INR {amount}.",
                amount=format_inr(income, symbol=False),
            ),
            "info",
            "income_added",
            "wallet",
        )

    if current["count"] > 0 and previous["count"] == 0:
        _append(
            insights,
            _text(
                "low_data",
                "Add transactions across at least two months to unlock month-over-month insights.",
            ),
            "info",
            "low_data",
            "info",
        )

    try:
        forecast = user_forecast(user_id)
        if not forecast.get("insufficient_data") and forecast.get("predicted_total", 0) > 0:
            base = forecast.get("comparison_base") or 0
            if base > 0 and abs(forecast.get("change_percent", 0)) >= 8:
                rising = forecast["change_percent"] > 0
                condition = "forecast_rise" if rising else "forecast_fall"
                fallback = (
                    "Your estimated expenses for next month are INR {amount}, a {change}% rise."
                    if rising
                    else "Your estimated expenses for next month are INR {amount}, a {change}% fall."
                )
                _append(
                    insights,
                    _text(
                        condition,
                        fallback,
                        amount=format_inr(forecast["predicted_total"], symbol=False),
                        change=abs(forecast["change_percent"]),
                    ),
                    "warning" if rising else "positive",
                    condition,
                    "line-chart",
                )
    except (ForecastUnavailableError, Exception):
        pass

    # Persist the latest generated set so the insights table has an audit trail.
    try:
        db.execute("DELETE FROM insights WHERE user_id = %s", (user_id,))
        for item in insights:
            db.execute(
                "INSERT INTO insights (user_id, insight_text, insight_type) VALUES (%s, %s, %s)",
                (user_id, item["text"], item["severity"]),
            )
    except Exception:
        pass

    return insights
