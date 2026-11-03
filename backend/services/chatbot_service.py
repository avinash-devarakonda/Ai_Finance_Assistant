"""Rule-based finance assistant. Every answer is grounded in the user's records."""
from __future__ import annotations

import re
from datetime import date

from database import db
from services.budget_service import get_budgets
from services.forecast_service import ForecastUnavailableError, user_forecast
from utils.dates import month_bounds, month_label, previous_month, today
from utils.formatters import format_inr
from utils.validators import EXPENSE_CATEGORIES

DISCLAIMER = (
    "I can help you understand your recorded finances, but I am not a licensed financial, "
    "investment or tax adviser. For major decisions, consult a qualified professional."
)


def _summary(user_id: int, start: date, end: date) -> dict:
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


def _categories(user_id: int, start: date, end: date) -> dict[str, float]:
    rows = db.fetch_all(
        """
        SELECT category, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE user_id = %s AND type = 'Expense' AND date BETWEEN %s AND %s
        GROUP BY category
        ORDER BY total DESC
        """,
        (user_id, start.isoformat(), end.isoformat()),
    )
    return {row["category"]: float(row["total"] or 0) for row in rows}


def _all_time_balance(user_id: int) -> dict:
    rows = db.fetch_all(
        """
        SELECT type, COALESCE(SUM(amount), 0) AS total
        FROM transactions WHERE user_id = %s GROUP BY type
        """,
        (user_id,),
    )
    income = expenses = 0.0
    for row in rows:
        if row["type"] == "Income":
            income = float(row["total"] or 0)
        else:
            expenses = float(row["total"] or 0)
    return {"income": income, "expenses": expenses, "balance": income - expenses}


def _find_category(message: str) -> str | None:
    lowered = message.lower()
    aliases = {
        "food": "Food",
        "restaurant": "Food",
        "groceries": "Food",
        "transport": "Transport",
        "travel": "Transport",
        "cab": "Transport",
        "shopping": "Shopping",
        "bills": "Bills",
        "utilities": "Bills",
        "entertainment": "Entertainment",
        "health": "Health",
        "medical": "Health",
        "education": "Education",
        "other": "Other",
    }
    for alias, category in aliases.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return category
    return None


def answer(user_id: int, message: str) -> dict:
    text = " ".join(str(message or "").strip().split())
    lowered = text.lower()
    if not text:
        return {
            "reply": "Ask me about your spending, savings, budgets or next month's expense estimate.",
            "intent": "empty",
        }

    now = today()
    start, end = month_bounds(now.year, now.month)
    prev_year, prev_month = previous_month(now.year, now.month)
    prev_start, prev_end = month_bounds(prev_year, prev_month)
    current = _summary(user_id, start, end)
    previous = _summary(user_id, prev_start, prev_end)
    categories = _categories(user_id, start, end)
    month_name = now.strftime("%B %Y")

    if any(word in lowered for word in ["invest", "stock", "mutual fund", "crypto", "tax", "insurance advice"]):
        return {
            "reply": (
                "I cannot provide investment, stock, tax or insurance advice. I can, however, summarise your "
                "recorded income, expenses, savings and budgets. " + DISCLAIMER
            ),
            "intent": "out_of_scope",
        }

    if lowered in {"hi", "hello", "hey", "help", "what can you do", "what can you do?"}:
        return {
            "reply": (
                "Hi! I can answer questions such as:\n"
                "• How much did I spend this month?\n"
                "• What is my highest spending category?\n"
                "• How much did I save?\n"
                "• What is my remaining budget?\n"
                "• How much did I spend on food?\n"
                "• Predict my next month's expenses.\n"
                "• Which category should I reduce spending in?\n\n"
                "All answers use your own recorded transactions."
            ),
            "intent": "help",
            "suggestions": [
                "How much did I spend this month?",
                "What is my remaining budget?",
                "Predict my next month's expenses",
            ],
        }

    if any(word in lowered for word in ["forecast", "predict", "next month"]):
        try:
            forecast = user_forecast(user_id)
        except ForecastUnavailableError as exc:
            return {"reply": str(exc), "intent": "forecast_unavailable"}
        if forecast.get("insufficient_data"):
            return {"reply": forecast.get("message"), "intent": "forecast_insufficient"}
        top = forecast["predicted_categories"][:3]
        top_lines = "\n".join(
            f"• {item['category']}: {format_inr(item['amount'])}" for item in top
        )
        direction = "higher" if forecast["change_percent"] >= 0 else "lower"
        return {
            "reply": (
                f"Estimated expenses for {forecast['predicted_month_label']}: "
                f"{format_inr(forecast['predicted_total'])}. That is {abs(forecast['change_percent'])}% "
                f"{direction} than your comparison month.\n\nLargest estimated categories:\n{top_lines}\n\n"
                "This is a statistical estimate, not a guarantee. It uses "
                f"{forecast['months_used']} months of your transaction history."
            ),
            "intent": "forecast",
            "data": forecast,
        }

    if "reduce" in lowered or "cut" in lowered or "save on" in lowered:
        budgets = get_budgets(user_id, month_label(now.year, now.month))
        exceeded = [item for item in budgets["budgets"] if item["status"] == "exceeded"]
        if exceeded:
            top = max(exceeded, key=lambda item: item["actual_expense"] - item["limit_amount"])
            return {
                "reply": (
                    f"Your clearest overspend is {top['category']}: "
                    f"{format_inr(top['actual_expense'])} spent against a {format_inr(top['limit_amount'])} budget "
                    f"({format_inr(abs(top['remaining']))} over). Reducing this category is the most direct way to "
                    "bring your budget back in line."
                ),
                "intent": "reduce_spending",
            }
        if categories:
            top_category, amount = max(categories.items(), key=lambda item: item[1])
            total = sum(categories.values())
            share = round((amount / total) * 100, 1) if total else 0
            return {
                "reply": (
                    f"Your largest recorded expense category this month is {top_category} at {format_inr(amount)} "
                    f"({share}% of expenses). Consider setting a realistic {top_category} budget and reviewing the "
                    "transactions in that category. I can only base this on your recorded data."
                ),
                "intent": "reduce_spending",
            }
        return {
            "reply": "I do not see any expenses recorded this month yet, so I cannot suggest a category to reduce.",
            "intent": "reduce_spending",
        }

    if "remaining budget" in lowered or "budget left" in lowered or "budget" in lowered:
        budgets = get_budgets(user_id, month_label(now.year, now.month))
        summary = budgets["summary"]
        if summary["budget_count"] == 0:
            return {
                "reply": (
                    f"You have not set any budgets for {month_name}. Open the Budgets page to add category limits."
                ),
                "intent": "budget",
            }
        lines = [
            f"• {item['category']}: {format_inr(item['remaining'])} remaining "
            f"({item['utilization']}% used)"
            for item in budgets["budgets"]
        ]
        status = ""
        if summary["exceeded_count"]:
            status = f"\nYou have exceeded {summary['exceeded_count']} budget(s) this month."
        elif summary["warning_count"]:
            status = f"\n{summary['warning_count']} budget(s) are close to their limit."
        return {
            "reply": (
                f"Your total budget for {month_name} is {format_inr(summary['total_budget'])}, with "
                f"{format_inr(summary['budgeted_spend'])} spent across budgeted categories. "
                f"Remaining: {format_inr(summary['remaining'])}.\n" + "\n".join(lines) + status
            ),
            "intent": "budget",
        }

    if "highest" in lowered or "most" in lowered and "category" in lowered:
        if not categories:
            return {
                "reply": f"You have no expenses recorded for {month_name}, so there is no highest category yet.",
                "intent": "highest_category",
            }
        category, amount = max(categories.items(), key=lambda item: item[1])
        total = sum(categories.values())
        share = round((amount / total) * 100, 1) if total else 0
        return {
            "reply": (
                f"Your highest spending category in {month_name} is {category}: {format_inr(amount)}, "
                f"which is {share}% of your recorded expenses."
            ),
            "intent": "highest_category",
        }

    category = _find_category(lowered)
    if category and any(word in lowered for word in ["spend", "spent", "expense", "cost", "pay"]):
        amount = categories.get(category, 0)
        count_row = db.fetch_one(
            """
            SELECT COUNT(*) AS count FROM transactions
            WHERE user_id = %s AND type = 'Expense' AND category = %s AND date BETWEEN %s AND %s
            """,
            (user_id, category, start.isoformat(), end.isoformat()),
        )
        count = int((count_row or {}).get("count") or 0)
        if amount <= 0:
            return {
                "reply": f"You have no recorded {category.lower()} expenses in {month_name}.",
                "intent": "category_spend",
            }
        return {
            "reply": (
                f"You spent {format_inr(amount)} on {category.lower()} in {month_name} across {count} "
                f"transaction{'s' if count != 1 else ''}."
            ),
            "intent": "category_spend",
        }

    if "save" in lowered or "saving" in lowered:
        savings = current["income"] - current["expenses"]
        if current["income"] <= 0:
            return {
                "reply": (
                    f"You have recorded {format_inr(current['expenses'])} in expenses for {month_name}, but no "
                    "income. Add income transactions or check whether income was recorded under another month."
                ),
                "intent": "savings",
            }
        rate = round((savings / current["income"]) * 100, 1)
        previous_savings = previous["income"] - previous["expenses"]
        comparison = ""
        if previous["count"] > 0:
            diff = savings - previous_savings
            if diff > 0:
                comparison = f" That is {format_inr(diff)} more than last month."
            elif diff < 0:
                comparison = f" That is {format_inr(abs(diff))} less than last month."
        return {
            "reply": (
                f"You saved {format_inr(savings)} in {month_name} (income {format_inr(current['income'])} minus "
                f"expenses {format_inr(current['expenses'])}), a savings rate of {rate}% of income.{comparison}"
            ),
            "intent": "savings",
        }

    if "income" in lowered and not "expense" in lowered:
        if current["income"] <= 0:
            return {"reply": f"No income is recorded for {month_name}.", "intent": "income"}
        return {
            "reply": f"Your recorded income for {month_name} is {format_inr(current['income'])}.",
            "intent": "income",
        }

    if "balance" in lowered or "available" in lowered:
        all_time = _all_time_balance(user_id)
        return {
            "reply": (
                f"Across all your recorded transactions, income is {format_inr(all_time['income'])}, expenses are "
                f"{format_inr(all_time['expenses'])}, leaving an available balance of {format_inr(all_time['balance'])}."
            ),
            "intent": "balance",
        }

    if "largest" in lowered or "biggest" in lowered or "most expensive" in lowered:
        row = db.fetch_one(
            """
            SELECT description, amount, category, date FROM transactions
            WHERE user_id = %s AND type = 'Expense' AND date BETWEEN %s AND %s
            ORDER BY amount DESC LIMIT 1
            """,
            (user_id, start.isoformat(), end.isoformat()),
        )
        if not row:
            return {"reply": f"No expenses are recorded for {month_name}.", "intent": "largest_expense"}
        return {
            "reply": (
                f"Your largest expense in {month_name} is {row['description']} for {format_inr(row['amount'])} "
                f"({row['category']}) on {str(row['date'])[:10]}."
            ),
            "intent": "largest_expense",
        }

    if "merchant" in lowered or "where" in lowered:
        row = db.fetch_one(
            """
            SELECT merchant, COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE user_id = %s AND type = 'Expense' AND date BETWEEN %s AND %s
              AND merchant IS NOT NULL AND merchant <> ''
            GROUP BY merchant ORDER BY total DESC LIMIT 1
            """,
            (user_id, start.isoformat(), end.isoformat()),
        )
        if not row:
            return {"reply": f"No merchant spending is recorded for {month_name}.", "intent": "top_merchant"}
        return {
            "reply": f"Your top merchant in {month_name} is {row['merchant']}, with {format_inr(row['total'])} spent.",
            "intent": "top_merchant",
        }

    if "transaction" in lowered or "how many" in lowered:
        return {
            "reply": (
                f"You have {current['count']} transaction{'s' if current['count'] != 1 else ''} recorded in "
                f"{month_name}."
            ),
            "intent": "transaction_count",
        }

    if any(phrase in lowered for phrase in ["spend", "spent", "expense", "spending"]):
        if current["count"] == 0:
            return {"reply": f"You have no transactions recorded for {month_name}.", "intent": "spend"}
        top = sorted(categories.items(), key=lambda item: item[1], reverse=True)[:3]
        top_text = ", ".join(f"{category} {format_inr(amount)}" for category, amount in top)
        return {
            "reply": (
                f"You spent {format_inr(current['expenses'])} in {month_name} across {current['count']} "
                f"transaction{'s' if current['count'] != 1 else ''}. Top categories: {top_text}."
            ),
            "intent": "spend",
        }

    return {
        "reply": (
            "I could not match that question to your records. Try asking:\n"
            "• How much did I spend this month?\n"
            "• What is my highest spending category?\n"
            "• What is my remaining budget?\n"
            "• How much did I spend on food?\n"
            "• Predict my next month's expenses."
        ),
        "intent": "fallback",
    }
