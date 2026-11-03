"""Transaction CRUD with ML-assisted category prediction."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, g, request

from database import db
from models.serializers import serialize_transaction
from services.classifier_service import ModelUnavailableError, predict_category
from utils.dates import parse_month, month_bounds
from utils.responses import error, success
from utils.validators import ValidationError, parse_date, validate_transaction

transactions_bp = Blueprint("transactions", __name__)

SORT_COLUMNS = {
    "date": "date",
    "amount": "amount",
    "description": "description",
    "created_at": "created_at",
}


def _hydrate_predictions(user_id: int, rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    ids = [row["transaction_id"] for row in rows]
    placeholders = ",".join(["%s"] * len(ids))
    predictions = db.fetch_all(
        f"""
        SELECT transaction_id, predicted_category, confidence, was_corrected, corrected_category
        FROM predictions
        WHERE user_id = %s AND transaction_id IN ({placeholders})
        ORDER BY prediction_id DESC
        """,
        (user_id, *ids),
    )
    prediction_map = {}
    for prediction in predictions:
        if prediction["transaction_id"] not in prediction_map:
            prediction_map[prediction["transaction_id"]] = prediction
    hydrated = []
    for row in rows:
        merged = dict(row)
        prediction = prediction_map.get(row["transaction_id"])
        if prediction:
            merged["predicted_category"] = prediction["predicted_category"]
            merged["confidence"] = prediction["confidence"]
            merged["was_corrected"] = prediction["was_corrected"]
            merged["corrected_category"] = prediction["corrected_category"]
        hydrated.append(serialize_transaction(merged))
    return hydrated


def _get_owned_transaction(user_id: int, transaction_id: int) -> dict | None:
    return db.fetch_one(
        "SELECT * FROM transactions WHERE transaction_id = %s AND user_id = %s",
        (transaction_id, user_id),
    )


def _store_prediction(
    user_id: int,
    transaction_id: int,
    predicted_category: str | None,
    confidence: float | None,
    actual_category: str | None = None,
) -> int | None:
    if not predicted_category:
        return None
    corrected = bool(actual_category and actual_category != predicted_category)
    prediction_id = db.execute(
        """
        INSERT INTO predictions
            (user_id, transaction_id, predicted_category, confidence, corrected_category, was_corrected)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            transaction_id,
            predicted_category,
            float(confidence or 0),
            actual_category if corrected else None,
            1 if corrected else 0,
        ),
        return_id=True,
    )
    return prediction_id


@transactions_bp.get("")
@transactions_bp.get("/")
def list_transactions_redirect():
    return list_transactions()


@transactions_bp.get("/list")
def list_transactions():
    user_id = g.current_user["user_id"]
    args = request.args

    filters = ["user_id = %s"]
    params: list = [user_id]

    search = (args.get("search") or "").strip()
    if search:
        like = f"%{search}%"
        filters.append("(description LIKE %s OR merchant LIKE %s OR category LIKE %s)")
        params.extend([like, like, like])

    transaction_type = (args.get("type") or "").strip().title()
    if transaction_type in {"Income", "Expense"}:
        filters.append("type = %s")
        params.append(transaction_type)

    category = (args.get("category") or "").strip()
    if category:
        filters.append("category = %s")
        params.append(category)

    month_value = (args.get("month") or "").strip()
    if month_value:
        try:
            year, month = parse_month(month_value)
            start, end = month_bounds(year, month)
            filters.append("date BETWEEN %s AND %s")
            params.extend([start.isoformat(), end.isoformat()])
        except ValueError as exc:
            return error(str(exc), 422)

    if args.get("date_from"):
        try:
            filters.append("date >= %s")
            params.append(parse_date(args["date_from"], allow_future=True))
        except ValidationError as exc:
            return error(str(exc), 422)
    if args.get("date_to"):
        try:
            filters.append("date <= %s")
            params.append(parse_date(args["date_to"], allow_future=True))
        except ValidationError as exc:
            return error(str(exc), 422)

    try:
        page = max(1, int(args.get("page", 1)))
        per_page = min(100, max(1, int(args.get("per_page", 20))))
    except ValueError:
        return error("Pagination values must be integers", 422)

    sort = SORT_COLUMNS.get((args.get("sort") or "date").lower(), "date")
    direction = "ASC" if (args.get("order") or "desc").lower() == "asc" else "DESC"
    where = " AND ".join(filters)

    count_row = db.fetch_one(f"SELECT COUNT(*) AS total FROM transactions WHERE {where}", tuple(params))
    total = int((count_row or {}).get("total") or 0)
    offset = (page - 1) * per_page
    rows = db.fetch_all(
        f"""
        SELECT * FROM transactions
        WHERE {where}
        ORDER BY {sort} {direction}, transaction_id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, per_page, offset),
    )

    return success(
        {
            "transactions": _hydrate_predictions(user_id, rows),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
            },
        }
    )


@transactions_bp.get("/meta")
def transactions_meta():
    user_id = g.current_user["user_id"]
    row = db.fetch_one(
        """
        SELECT COUNT(*) AS total,
               MIN(date) AS first_date,
               MAX(date) AS last_date
        FROM transactions WHERE user_id = %s
        """,
        (user_id,),
    )
    return success(
        {
            "total": int((row or {}).get("total") or 0),
            "first_date": str((row or {}).get("first_date"))[:10] if (row or {}).get("first_date") else None,
            "last_date": str((row or {}).get("last_date"))[:10] if (row or {}).get("last_date") else None,
        }
    )


@transactions_bp.post("")
@transactions_bp.post("/")
def create_transaction():
    user_id = g.current_user["user_id"]
    payload = request.get_json(silent=True) or {}
    try:
        data = validate_transaction(payload)
    except ValidationError as exc:
        return error(str(exc), 422)

    predicted_category = None
    confidence = None
    if not data["category"]:
        try:
            result = predict_category(data["description"], data["amount"], data["transaction_type"])
            data["category"] = result["predicted_category"]
            predicted_category = result["predicted_category"]
            confidence = result["confidence"]
        except ModelUnavailableError as exc:
            return error(str(exc), 503)
    else:
        # The frontend sends the prediction it displayed. Keeping it even when
        # the user changes the category lets us record a correction for future
        # model improvement.
        submitted_prediction = payload.get("predicted_category")
        submitted_confidence = payload.get("prediction_confidence")
        if submitted_prediction:
            from utils.validators import parse_category

            try:
                predicted_category = parse_category(submitted_prediction, "Expense")
            except ValidationError:
                predicted_category = None
            try:
                confidence = float(submitted_confidence)
            except (TypeError, ValueError):
                confidence = None

    transaction_id = db.execute(
        """
        INSERT INTO transactions (user_id, date, description, amount, type, category, merchant)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            data["date"],
            data["description"],
            data["amount"],
            data["transaction_type"],
            data["category"],
            data["merchant"],
        ),
        return_id=True,
    )
    _store_prediction(user_id, transaction_id, predicted_category, confidence, data["category"])

    row = _get_owned_transaction(user_id, transaction_id)
    return success(
        {"transaction": _hydrate_predictions(user_id, [row])[0]},
        "Transaction added successfully",
        201,
    )


@transactions_bp.put("/<int:transaction_id>")
def update_transaction(transaction_id: int):
    user_id = g.current_user["user_id"]
    existing = _get_owned_transaction(user_id, transaction_id)
    if not existing:
        return error("Transaction not found", 404)

    payload = request.get_json(silent=True) or {}
    try:
        data = validate_transaction(payload, partial=True)
    except ValidationError as exc:
        return error(str(exc), 422)

    transaction_type = data.get("transaction_type") or existing["type"]
    category = data.get("category")
    if transaction_type == "Income" and not category:
        category = existing["category"] if existing["type"] == "Income" else "Salary"
    if transaction_type == "Expense" and not category:
        category = existing["category"] if existing["type"] == "Expense" else "Other"

    # Validate the merged category against the merged transaction type.
    from utils.validators import parse_category

    try:
        category = parse_category(category, transaction_type)
    except ValidationError as exc:
        return error(str(exc), 422)

    description = data.get("description") or existing["description"]
    amount = data.get("amount") if data.get("amount") is not None else float(existing["amount"])
    date_value = data.get("date") or str(existing["date"])[:10]
    merchant = data.get("merchant") if "merchant" in payload else existing.get("merchant")

    db.execute(
        """
        UPDATE transactions
        SET date = %s, description = %s, amount = %s, type = %s, category = %s, merchant = %s
        WHERE transaction_id = %s AND user_id = %s
        """,
        (date_value, description, amount, transaction_type, category, merchant, transaction_id, user_id),
    )

    prediction = db.fetch_one(
        """
        SELECT prediction_id, predicted_category FROM predictions
        WHERE transaction_id = %s AND user_id = %s
        ORDER BY prediction_id DESC LIMIT 1
        """,
        (transaction_id, user_id),
    )
    if prediction:
        corrected = category != prediction["predicted_category"]
        db.execute(
            """
            UPDATE predictions
            SET corrected_category = %s, was_corrected = %s
            WHERE prediction_id = %s AND user_id = %s
            """,
            (category if corrected else None, 1 if corrected else 0, prediction["prediction_id"], user_id),
        )

    row = _get_owned_transaction(user_id, transaction_id)
    return success(
        {"transaction": _hydrate_predictions(user_id, [row])[0]},
        "Transaction updated successfully",
    )


@transactions_bp.delete("/<int:transaction_id>")
def delete_transaction(transaction_id: int):
    user_id = g.current_user["user_id"]
    existing = _get_owned_transaction(user_id, transaction_id)
    if not existing:
        return error("Transaction not found", 404)
    db.execute(
        "DELETE FROM transactions WHERE transaction_id = %s AND user_id = %s",
        (transaction_id, user_id),
    )
    return success(message="Transaction deleted successfully")
