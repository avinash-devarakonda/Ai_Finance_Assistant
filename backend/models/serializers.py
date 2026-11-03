"""Serialization helpers for API resources."""
from __future__ import annotations

from utils.formatters import to_float


def serialize_user(user: dict) -> dict:
    return {
        "user_id": user["user_id"],
        "name": user["name"],
        "email": user["email"],
        "created_at": user.get("created_at"),
    }


def serialize_transaction(row: dict) -> dict:
    return {
        "transaction_id": row["transaction_id"],
        "date": str(row["date"])[:10],
        "description": row["description"],
        "amount": round(to_float(row["amount"]), 2),
        "transaction_type": row.get("type") or row.get("transaction_type"),
        "category": row["category"],
        "merchant": row.get("merchant") or "",
        "created_at": row.get("created_at"),
        "predicted_category": row.get("predicted_category"),
        "confidence": (
            round(to_float(row["confidence"]), 4)
            if row.get("confidence") is not None
            else None
        ),
        "was_corrected": bool(row.get("was_corrected")) if row.get("was_corrected") is not None else False,
    }


def serialize_budget(row: dict) -> dict:
    limit_amount = round(to_float(row["limit_amount"]), 2)
    actual_expense = round(to_float(row.get("actual_expense")), 2)
    remaining = round(limit_amount - actual_expense, 2)
    utilization = round((actual_expense / limit_amount) * 100, 1) if limit_amount > 0 else 0
    if utilization > 100:
        status = "exceeded"
    elif utilization >= 85:
        status = "warning"
    elif utilization >= 60:
        status = "watch"
    else:
        status = "healthy"
    return {
        "budget_id": row["budget_id"],
        "month": row["month"],
        "category": row["category"],
        "limit_amount": limit_amount,
        "actual_expense": actual_expense,
        "remaining": remaining,
        "utilization": utilization,
        "status": status,
        "created_at": row.get("created_at"),
    }
