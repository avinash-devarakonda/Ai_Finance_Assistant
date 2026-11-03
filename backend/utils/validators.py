"""Input validation shared by API routes."""
from __future__ import annotations

import re
from datetime import date, datetime

EXPENSE_CATEGORIES = [
    "Food",
    "Transport",
    "Shopping",
    "Bills",
    "Entertainment",
    "Health",
    "Education",
    "Other",
]
INCOME_CATEGORIES = ["Salary", "Freelance", "Business", "Investments", "Gift", "Other"]
ALL_CATEGORIES = EXPENSE_CATEGORIES + ["Salary", "Freelance", "Business", "Investments", "Gift"]
TRANSACTION_TYPES = ["Income", "Expense"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ValidationError(ValueError):
    """Raised for malformed client input."""


def require_fields(payload: dict, fields: list[str]) -> None:
    missing = [field for field in fields if payload.get(field) in (None, "")]
    if missing:
        raise ValidationError(f"Missing required field(s): {', '.join(missing)}")


def parse_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 190:
        raise ValidationError("Enter a valid email address")
    return email


def parse_password(value: str) -> str:
    password = str(value or "")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long")
    if len(password) > 128:
        raise ValidationError("Password must be 128 characters or fewer")
    return password


def parse_name(value: str) -> str:
    name = " ".join(str(value or "").strip().split())
    if len(name) < 2 or len(name) > 120:
        raise ValidationError("Name must be between 2 and 120 characters")
    return name


def parse_description(value: str) -> str:
    description = " ".join(str(value or "").strip().split())
    if len(description) < 2:
        raise ValidationError("Description must be at least 2 characters")
    if len(description) > 255:
        raise ValidationError("Description must be 255 characters or fewer")
    return description


def parse_amount(value) -> float:
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Amount must be a number") from exc
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero")
    if amount > 1_000_000_000:
        raise ValidationError("Amount is too large")
    return amount


def parse_transaction_type(value: str) -> str:
    transaction_type = str(value or "").strip().title()
    if transaction_type not in TRANSACTION_TYPES:
        raise ValidationError("Transaction type must be Income or Expense")
    return transaction_type


def parse_date(value: str, *, allow_future: bool = False) -> str:
    try:
        parsed = datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError("Date must use YYYY-MM-DD format") from exc
    if not allow_future and parsed > date.today():
        raise ValidationError("Transaction date cannot be in the future")
    if parsed.year < 2000:
        raise ValidationError("Transaction date must be after 2000")
    return parsed.isoformat()


def parse_category(value: str, transaction_type: str = "Expense") -> str:
    category = str(value or "").strip().title()
    allowed = INCOME_CATEGORIES if transaction_type == "Income" else EXPENSE_CATEGORIES
    if category not in allowed:
        raise ValidationError(
            f"Category must be one of: {', '.join(allowed)}"
        )
    return category


def parse_month_value(value: str) -> str:
    try:
        parsed = datetime.strptime(str(value or ""), "%Y-%m")
    except ValueError as exc:
        raise ValidationError("Month must use YYYY-MM format") from exc
    return parsed.strftime("%Y-%m")


def parse_optional_text(value, max_length: int = 150) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    if not text:
        return None
    if len(text) > max_length:
        raise ValidationError(f"Text must be {max_length} characters or fewer")
    return text


def validate_registration(payload: dict) -> dict:
    require_fields(payload, ["name", "email", "password"])
    return {
        "name": parse_name(payload.get("name")),
        "email": parse_email(payload.get("email")),
        "password": parse_password(payload.get("password")),
    }


def validate_login(payload: dict) -> dict:
    require_fields(payload, ["email", "password"])
    return {
        "email": parse_email(payload.get("email")),
        "password": str(payload.get("password") or ""),
    }


def validate_transaction(payload: dict, *, partial: bool = False) -> dict:
    required = [] if partial else ["date", "description", "amount", "transaction_type"]
    require_fields(payload, required)

    transaction_type = parse_transaction_type(payload.get("transaction_type", "Expense"))
    result = {
        "date": parse_date(payload["date"]) if payload.get("date") else None,
        "description": parse_description(payload["description"]) if payload.get("description") is not None else None,
        "amount": parse_amount(payload["amount"]) if payload.get("amount") is not None else None,
        "transaction_type": transaction_type,
        "category": None,
        "merchant": parse_optional_text(payload.get("merchant"), 150),
    }
    category = payload.get("category")
    if category and str(category).strip().lower() not in {"auto", "auto-detect", "automatic"}:
        result["category"] = parse_category(category, transaction_type)
    elif transaction_type == "Income":
        result["category"] = "Salary"
    return result


def validate_budget(payload: dict, *, partial: bool = False) -> dict:
    required = [] if partial else ["month", "category", "limit_amount"]
    require_fields(payload, required)
    return {
        "month": parse_month_value(payload["month"]) if payload.get("month") else None,
        "category": parse_category(payload["category"]) if payload.get("category") else None,
        "limit_amount": parse_amount(payload["limit_amount"]) if payload.get("limit_amount") is not None else None,
    }
