"""Budget management service. Actual spending always comes from transactions."""
from __future__ import annotations

from datetime import date

from database import db
from models.serializers import serialize_budget
from utils.dates import month_bounds, parse_month, today
from utils.validators import EXPENSE_CATEGORIES


def _actual_spending(user_id: int, start: date, end: date) -> dict[str, float]:
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


def get_budgets(user_id: int, month: str | None = None) -> dict:
    year, month_number = parse_month(month)
    month_value = f"{year:04d}-{month_number:02d}"
    start, end = month_bounds(year, month_number)

    rows = db.fetch_all(
        """
        SELECT b.budget_id, b.month, b.category, b.limit_amount, b.created_at,
               COALESCE((
                   SELECT SUM(t.amount) FROM transactions t
                   WHERE t.user_id = b.user_id
                     AND t.type = 'Expense'
                     AND t.category = b.category
                     AND t.date BETWEEN %s AND %s
               ), 0) AS actual_expense
        FROM budgets b
        WHERE b.user_id = %s AND b.month = %s
        ORDER BY b.category ASC
        """,
        (start.isoformat(), end.isoformat(), user_id, month_value),
    )
    budgets = [serialize_budget(row) for row in rows]
    spending = _actual_spending(user_id, start, end)
    budgeted_categories = {budget["category"] for budget in budgets}
    unbudgeted = [
        {
            "category": category,
            "actual_expense": round(amount, 2),
        }
        for category, amount in sorted(spending.items(), key=lambda item: item[1], reverse=True)
        if category not in budgeted_categories
    ]

    total_budget = round(sum(budget["limit_amount"] for budget in budgets), 2)
    total_spent_in_budgets = round(sum(budget["actual_expense"] for budget in budgets), 2)
    total_spent = round(sum(spending.values()), 2)
    remaining = round(total_budget - total_spent_in_budgets, 2)
    utilization = round((total_spent_in_budgets / total_budget) * 100, 1) if total_budget > 0 else 0
    exceeded = sum(1 for budget in budgets if budget["status"] == "exceeded")
    warnings = sum(1 for budget in budgets if budget["status"] == "warning")

    return {
        "month": month_value,
        "month_label": date(year, month_number, 1).strftime("%B %Y"),
        "budgets": budgets,
        "summary": {
            "total_budget": total_budget,
            "total_spent": total_spent,
            "budgeted_spend": total_spent_in_budgets,
            "remaining": remaining,
            "utilization": utilization,
            "exceeded_count": exceeded,
            "warning_count": warnings,
            "budget_count": len(budgets),
        },
        "unbudgeted": unbudgeted,
        "categories": EXPENSE_CATEGORIES,
    }


def create_budget(user_id: int, payload: dict) -> dict:
    existing = db.fetch_one(
        "SELECT budget_id FROM budgets WHERE user_id = %s AND month = %s AND category = %s",
        (user_id, payload["month"], payload["category"]),
    )
    if existing:
        raise ValueError("A budget already exists for this category and month. Edit the existing budget instead.")
    budget_id = db.execute(
        "INSERT INTO budgets (user_id, month, category, limit_amount) VALUES (%s, %s, %s, %s)",
        (user_id, payload["month"], payload["category"], payload["limit_amount"]),
        return_id=True,
    )
    return get_budget_by_id(user_id, budget_id)


def get_budget_by_id(user_id: int, budget_id: int) -> dict:
    row = db.fetch_one(
        """
        SELECT b.budget_id, b.month, b.category, b.limit_amount, b.created_at,
               COALESCE((
                   SELECT SUM(t.amount) FROM transactions t
                   WHERE t.user_id = b.user_id
                     AND t.type = 'Expense'
                     AND t.category = b.category
                     AND SUBSTRING(b.month, 1, 4) = SUBSTRING(t.date, 1, 4)
                     AND SUBSTRING(b.month, 6, 2) = SUBSTRING(t.date, 6, 2)
               ), 0) AS actual_expense
        FROM budgets b
        WHERE b.budget_id = %s AND b.user_id = %s
        """,
        (budget_id, user_id),
    )
    if not row:
        raise LookupError("Budget not found")
    return serialize_budget(row)


def update_budget(user_id: int, budget_id: int, payload: dict) -> dict:
    existing = db.fetch_one(
        "SELECT * FROM budgets WHERE budget_id = %s AND user_id = %s",
        (budget_id, user_id),
    )
    if not existing:
        raise LookupError("Budget not found")

    month_value = payload.get("month") or existing["month"]
    category = payload.get("category") or existing["category"]
    limit_amount = payload.get("limit_amount")
    if limit_amount is None:
        limit_amount = existing["limit_amount"]

    conflict = db.fetch_one(
        """
        SELECT budget_id FROM budgets
        WHERE user_id = %s AND month = %s AND category = %s AND budget_id <> %s
        """,
        (user_id, month_value, category, budget_id),
    )
    if conflict:
        raise ValueError("Another budget already exists for this category and month.")

    db.execute(
        "UPDATE budgets SET month = %s, category = %s, limit_amount = %s WHERE budget_id = %s AND user_id = %s",
        (month_value, category, limit_amount, budget_id, user_id),
    )
    return get_budget_by_id(user_id, budget_id)


def delete_budget(user_id: int, budget_id: int) -> None:
    existing = db.fetch_one(
        "SELECT budget_id FROM budgets WHERE budget_id = %s AND user_id = %s",
        (budget_id, user_id),
    )
    if not existing:
        raise LookupError("Budget not found")
    db.execute("DELETE FROM budgets WHERE budget_id = %s AND user_id = %s", (budget_id, user_id))


def current_month_summary(user_id: int) -> dict:
    current = today()
    return get_budgets(user_id, f"{current.year:04d}-{current.month:02d}")
