"""Expense forecasting service with user-specific historical modelling."""
from __future__ import annotations

import threading
from datetime import date, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from config import Config
from database import db
from utils.dates import add_months, month_label, today

_bundle = None
_lock = threading.Lock()
_global_history = None

CATEGORY_COLUMNS = [
    "food_expenses",
    "transport_expenses",
    "shopping_expenses",
    "bills_expenses",
    "health_expenses",
    "entertainment_expenses",
    "education_expenses",
    "other_expenses",
]
CATEGORY_TO_COLUMN = {value.replace("_expenses", "").title(): value for value in CATEGORY_COLUMNS}


class ForecastUnavailableError(RuntimeError):
    pass


def _load_bundle():
    global _bundle
    if _bundle is not None:
        return _bundle
    with _lock:
        if _bundle is not None:
            return _bundle
        path = Path(Config.FORECAST_MODEL)
        if not path.exists():
            raise ForecastUnavailableError(
                "Expense forecasting model is not trained. Run: python backend/ml/train_forecasting.py"
            )
        _bundle = joblib.load(path)
        return _bundle


def reload_model() -> None:
    global _bundle
    with _lock:
        _bundle = None


def _load_global_history() -> pd.DataFrame | None:
    global _global_history
    if _global_history is not None:
        return _global_history
    path = Path(Config.MONTHLY_DATASET)
    if not path.exists():
        return None
    try:
        frame = pd.read_csv(path)
        frame["month"] = frame["month"].astype(int)
        frame["year"] = frame["year"].astype(int)
        for column in CATEGORY_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).clip(lower=0)
        _global_history = frame.sort_values(["year", "month"]).tail(6).reset_index(drop=True)
        return _global_history
    except Exception:
        return None


def _feature_row(year: int, month: int, time_index: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "time_index": time_index,
                "year": year,
                "month": month,
                "month_sin": np.sin(2 * np.pi * month / 12),
                "month_cos": np.cos(2 * np.pi * month / 12),
                "quarter": (month - 1) // 3 + 1,
            }
        ]
    )


def _months_between(y1: int, m1: int, y2: int, m2: int) -> int:
    return (y2 - y1) * 12 + (m2 - m1)


def global_forecast(year: int, month: int) -> dict:
    bundle = _load_bundle()
    gap = _months_between(bundle["last_year"], bundle["last_month"], year, month)
    time_index = int(bundle["last_training_month"]) + gap
    features = _feature_row(year, month, time_index)
    values = {}
    for target, model_info in bundle["models"].items():
        model = model_info["model"]
        prediction = float(model.predict(features)[0])
        values[target] = max(0.0, prediction)
    total = sum(values.get(column, 0.0) for column in CATEGORY_COLUMNS)
    values["total_expenses"] = max(total, 0.0)
    return {key: round(value, 2) for key, value in values.items()}


def _global_category_ratios(next_year: int, next_month: int) -> dict[str, float]:
    """Return model-based seasonal ratios versus the recent global baseline."""
    history = _load_global_history()
    if history is None or history.empty:
        return {column: 1.0 for column in CATEGORY_COLUMNS}
    forecast = global_forecast(next_year, next_month)
    baseline = history[CATEGORY_COLUMNS].mean()
    ratios = {}
    for column in CATEGORY_COLUMNS:
        base = float(baseline.get(column, 0) or 0)
        ratios[column] = (forecast.get(column, 0) / base) if base > 0 else 1.0
        ratios[column] = float(np.clip(ratios[column], 0.55, 1.75))
    return ratios


def _month_items(start_year: int, start_month: int, end_year: int, end_month: int) -> list[tuple[int, int]]:
    count = _months_between(start_year, start_month, end_year, end_month) + 1
    count = max(1, min(count, 24))
    first_year, first_month = add_months(end_year, end_month, -(count - 1))
    return [add_months(first_year, first_month, index) for index in range(count)]


def _user_monthly_history(user_id: int, end_year: int, end_month: int, months: int = 12) -> tuple[list[dict], int]:
    start_year, start_month = add_months(end_year, end_month, -(months - 1))
    start_date = date(start_year, start_month, 1)
    rows = db.fetch_all(
        """
        SELECT date, category, amount
        FROM transactions
        WHERE user_id = %s AND type = 'Expense' AND date >= %s
        ORDER BY date ASC
        """,
        (user_id, start_date.isoformat()),
    )
    buckets: dict[str, dict] = {}
    for year, month in _month_items(start_year, start_month, end_year, end_month):
        key = month_label(year, month)
        buckets[key] = {
            "month": key,
            "year": year,
            "month_number": month,
            **{column: 0.0 for column in CATEGORY_COLUMNS},
            "total_expenses": 0.0,
        }

    for row in rows:
        raw_date = str(row["date"])[:10]
        key = raw_date[:7]
        if key not in buckets:
            continue
        column = CATEGORY_TO_COLUMN.get(str(row["category"]))
        if not column:
            column = "other_expenses"
        amount = float(row["amount"] or 0)
        buckets[key][column] += amount
        buckets[key]["total_expenses"] += amount

    history = []
    for item in buckets.values():
        for column in CATEGORY_COLUMNS:
            item[column] = round(item[column], 2)
        item["total_expenses"] = round(item["total_expenses"], 2)
        history.append(item)

    months_with_data = sum(1 for item in history if item["total_expenses"] > 0)
    return history, months_with_data


def user_forecast(user_id: int) -> dict:
    bundle = _load_bundle()
    current = today()
    end_year, end_month = current.year, current.month
    history, months_with_data = _user_monthly_history(user_id, end_year, end_month, months=12)

    next_year, next_month = add_months(end_year, end_month, 1)
    next_key = month_label(next_year, next_month)

    if months_with_data < 3:
        return {
            "insufficient_data": True,
            "message": (
                "We need at least three months of your expense transactions before making a forecast. "
                "Add more transactions to unlock an estimate."
            ),
            "historical": history,
            "predicted_month": next_key,
            "currency": "INR",
            "is_estimate": True,
        }

    # Recency: require at least one expense transaction in the last 90 days.
    recent_rows = db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM transactions
        WHERE user_id = %s AND type = 'Expense'
          AND date >= %s
        """,
        (user_id, (current.replace(day=1)).isoformat()),
    )
    if not recent_rows or int(recent_rows.get("count") or 0) == 0:
        return {
            "insufficient_data": True,
            "message": (
                "No expense transactions were found in the current month. "
                "Add recent transactions so the forecast reflects your current spending."
            ),
            "historical": history,
            "predicted_month": next_key,
            "currency": "INR",
            "is_estimate": True,
        }

    ratios = _global_category_ratios(next_year, next_month)
    recent = history[-3:]
    weights = np.array([0.2, 0.3, 0.5])[: len(recent)]
    weights = weights / weights.sum()

    predictions: dict[str, float] = {}
    for column in CATEGORY_COLUMNS:
        values = np.array([item[column] for item in recent], dtype=float)
        weighted_average = float(np.dot(values, weights))
        global_scaled = weighted_average * ratios[column]

        if months_with_data >= 6:
            # Fit a personal trend on up to 12 dense months. Zero-spend months are
            # genuine observations for this user and are retained.
            x = np.arange(len(history)).reshape(-1, 1)
            y = np.array([item[column] for item in history], dtype=float)
            try:
                model = LinearRegression()
                model.fit(x, y)
                trend_prediction = float(model.predict(np.array([[len(history)]]))[0])
            except Exception:
                trend_prediction = weighted_average
            trend_prediction = float(np.clip(trend_prediction, 0, weighted_average * 2.5 + 2000))
            prediction = 0.62 * trend_prediction + 0.38 * global_scaled
            method = "Personal trend regression blended with the trained seasonal model"
        else:
            prediction = 0.72 * weighted_average + 0.28 * global_scaled
            method = "Recent spending average adjusted by the trained seasonal model"

        predictions[column] = max(0.0, prediction)

    total = sum(predictions.values())
    predicted_categories = [
        {
            "category": column.replace("_expenses", "").title(),
            "amount": round(predictions[column], 2),
            "share": round((predictions[column] / total) * 100, 1) if total > 0 else 0,
        }
        for column in CATEGORY_COLUMNS
    ]
    predicted_categories.sort(key=lambda item: item["amount"], reverse=True)

    last_month_total = history[-1]["total_expenses"] if history else 0
    recent_average = float(np.mean([item["total_expenses"] for item in history[-3:]])) if history else 0
    comparison_base = last_month_total if last_month_total > 0 else recent_average
    change_pct = ((total - comparison_base) / comparison_base * 100) if comparison_base > 0 else 0
    base_confidence = float(bundle["models"]["total_expenses"]["metrics"].get("r2", 0.5))
    confidence = min(0.94, max(0.55, 0.58 + months_with_data * 0.025 + max(base_confidence, 0) * 0.18))

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return {
        "insufficient_data": False,
        "message": "This is an estimate based on your recent transactions and the trained forecasting model.",
        "predicted_month": next_key,
        "predicted_month_label": f"{month_names[next_month - 1]} {next_year}",
        "predicted_total": round(total, 2),
        "predicted_categories": predicted_categories,
        "change_percent": round(change_pct, 1),
        "comparison_base": round(comparison_base, 2),
        "confidence": round(confidence, 2),
        "method": method,
        "months_used": months_with_data,
        "historical": history,
        "currency": "INR",
        "is_estimate": True,
        "model_metrics": bundle["models"]["total_expenses"]["metrics"],
        "model_name": bundle["models"]["total_expenses"]["model_name"],
    }


def forecast_info() -> dict:
    try:
        bundle = _load_bundle()
    except ForecastUnavailableError as exc:
        return {"available": False, "message": str(exc)}
    return {
        "available": True,
        "trained_at": bundle.get("trained_at"),
        "next_month": f"{bundle.get('next_year')}-{bundle.get('next_month'):02d}",
        "training_rows": bundle.get("training_rows"),
        "validation_rows": bundle.get("validation_rows"),
        "best_models": {
            target: info.get("model_name") for target, info in bundle.get("models", {}).items()
        },
        "metrics": {
            target: info.get("metrics") for target, info in bundle.get("models", {}).items()
        },
    }
