"""Machine learning API routes."""
from __future__ import annotations

from flask import Blueprint, g, request

from database import db
from services.classifier_service import (
    ModelUnavailableError,
    model_info,
    predict_category,
)
from services.forecast_service import ForecastUnavailableError, forecast_info, user_forecast
from utils.responses import error, success
from utils.validators import ValidationError, parse_amount, parse_description, parse_transaction_type

ml_bp = Blueprint("ml", __name__)


@ml_bp.post("/predict-category")
def predict_expense_category():
    user_id = g.current_user["user_id"]
    payload = request.get_json(silent=True) or {}
    try:
        description = parse_description(payload.get("description"))
        amount = parse_amount(payload.get("amount", 1))
        transaction_type = parse_transaction_type(payload.get("transaction_type", "Expense"))
    except ValidationError as exc:
        return error(str(exc), 422)

    if transaction_type == "Income":
        return error("The category classifier is trained for expense transactions only", 422)

    try:
        result = predict_category(description, amount, transaction_type)
    except ModelUnavailableError as exc:
        return error(str(exc), 503)

    transaction_id = payload.get("transaction_id")
    if transaction_id:
        try:
            transaction_id = int(transaction_id)
        except (TypeError, ValueError):
            return error("transaction_id must be an integer", 422)
        owned = db.fetch_one(
            "SELECT transaction_id FROM transactions WHERE transaction_id = %s AND user_id = %s",
            (transaction_id, user_id),
        )
        if not owned:
            return error("Transaction not found", 404)
        db.execute(
            """
            INSERT INTO predictions (user_id, transaction_id, predicted_category, confidence)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, transaction_id, result["predicted_category"], result["confidence"]),
        )

    return success(
        {
            "predicted_category": result["predicted_category"],
            "confidence": result["confidence"],
            "alternatives": result.get("alternatives", []),
            "model": result.get("model"),
        }
    )


@ml_bp.post("/predict-expenses")
def predict_expenses():
    try:
        forecast = user_forecast(g.current_user["user_id"])
        return success({"forecast": forecast})
    except ForecastUnavailableError as exc:
        return error(str(exc), 503)
    except Exception as exc:  # pragma: no cover - defensive API boundary
        return error(f"Unable to generate forecast: {exc}", 500)


@ml_bp.get("/models")
@ml_bp.get("/ml/models")
def models():
    return success({"classifier": model_info(), "forecaster": forecast_info()})
