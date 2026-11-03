"""
Train the monthly expense forecasting models.

Usage:
    python backend/ml/train_forecasting.py

For the total expense target and every expense category, Linear Regression and
Random Forest Regression are compared using a chronological hold-out set.
MAE, RMSE and R² are recorded, and the best estimator per target is saved.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ML_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ML_DIR.parent.parent
DATASET = PROJECT_ROOT / "datasets" / "monthly_expenses.csv"
MODEL_PATH = ML_DIR / "expense_forecasting.pkl"
METRICS_PATH = ML_DIR / "forecasting_metrics.json"
PLOT_PATH = ML_DIR / "forecast_validation.png"

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
TARGETS = ["total_expenses"] + CATEGORY_COLUMNS
FEATURES = ["time_index", "year", "month", "month_sin", "month_cos", "quarter"]


def load_data() -> pd.DataFrame:
    if not DATASET.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET}. Run datasets/generate_datasets.py first.")
    df = pd.read_csv(DATASET)
    required = {"month", "year", *CATEGORY_COLUMNS, "total_expenses"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")

    for column in required:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["month", "year"])
    df = df.drop_duplicates(subset=["year", "month"]).copy()
    df["month"] = df["month"].astype(int).clip(1, 12)
    df["year"] = df["year"].astype(int)
    df["date"] = pd.to_datetime({"year": df["year"], "month": df["month"], "day": 1})
    df = df.sort_values("date").reset_index(drop=True)

    category_values = df[CATEGORY_COLUMNS].fillna(0).clip(lower=0)
    # Keep the total consistent with category rows (important for the dashboard).
    df["total_expenses"] = category_values.sum(axis=1)
    df[CATEGORY_COLUMNS] = category_values
    df["time_index"] = np.arange(len(df))
    df["quarter"] = ((df["month"] - 1) // 3 + 1).astype(int)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    return df


def build_estimators() -> dict[str, object]:
    return {
        "Linear Regression": LinearRegression(),
        "Random Forest Regressor": RandomForestRegressor(
            n_estimators=400,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
        ),
    }


def metrics_for(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = r2_score(y_true, y_pred)
    return {
        "mae": round(float(mae), 2),
        "rmse": round(rmse, 2),
        "r2": round(float(r2), 4),
    }


def main() -> None:
    df = load_data()
    if len(df) < 18:
        raise ValueError("At least 18 monthly records are required to train a reliable forecast.")

    # Time-series validation: the most recent 12 months are never used for fitting.
    test_size = 12
    train = df.iloc[:-test_size].copy()
    test = df.iloc[-test_size:].copy()
    if len(train) < 12:
        raise ValueError("At least 12 training months are required.")

    models: dict[str, dict] = {}
    comparison: dict[str, dict] = {}
    validation_predictions: dict[str, np.ndarray] = {}

    for target in TARGETS:
        comparison[target] = {}
        best_name = None
        best_score = -np.inf
        best_model = None
        for name, estimator in build_estimators().items():
            estimator.fit(train[FEATURES], train[target])
            predictions = estimator.predict(test[FEATURES])
            scores = metrics_for(test[target].to_numpy(), predictions)
            comparison[target][name] = scores
            # Prefer accuracy (R²); tie-break with lower RMSE.
            score = scores["r2"] - scores["rmse"] / 1_000_000
            if score > best_score:
                best_score = score
                best_name = name
                best_model = estimator
                validation_predictions[target] = predictions

        models[target] = {
            "model": best_model,
            "model_name": best_name,
            "metrics": comparison[target][best_name],
            "all_models": comparison[target],
        }

    # Validation chart for total expenses.
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(test["date"], test["total_expenses"], marker="o", label="Actual", linewidth=2.2)
    ax.plot(
        test["date"],
        validation_predictions["total_expenses"],
        marker="s",
        linestyle="--",
        label=f"Predicted ({models['total_expenses']['model_name']})",
        linewidth=2,
    )
    ax.set_title("Expense Forecast Validation - Last 12 Months")
    ax.set_xlabel("Month")
    ax.set_ylabel("Expenses (INR)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_PATH, dpi=160)
    plt.close(fig)

    last = df.iloc[-1]
    next_month_index = int(last["time_index"]) + 1
    next_month = int(last["month"]) + 1
    next_year = int(last["year"])
    if next_month > 12:
        next_month = 1
        next_year += 1

    trained_at = datetime.now(timezone.utc).isoformat()
    bundle = {
        "models": models,
        "features": FEATURES,
        "category_columns": CATEGORY_COLUMNS,
        "last_training_month": int(last["time_index"]),
        "last_month": int(last["month"]),
        "last_year": int(last["year"]),
        "next_month_index": next_month_index,
        "next_month": next_month,
        "next_year": next_year,
        "trained_at": trained_at,
        "training_rows": int(len(train)),
        "validation_rows": int(len(test)),
    }
    joblib.dump(bundle, MODEL_PATH)

    summary = {
        "trained_at": trained_at,
        "best_models": {target: models[target]["model_name"] for target in TARGETS},
        "metrics": {target: models[target]["metrics"] for target in TARGETS},
        "comparison": comparison,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "date_range": {
            "start": df["date"].iloc[0].strftime("%Y-%m"),
            "end": df["date"].iloc[-1].strftime("%Y-%m"),
        },
        "next_month": f"{next_year}-{next_month:02d}",
    }
    METRICS_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Total model: {models['total_expenses']['model_name']} {models['total_expenses']['metrics']}")
    print(f"Next month: {next_year}-{next_month:02d}")
    print(f"Saved model to {MODEL_PATH}")
    print(f"Saved metrics to {METRICS_PATH}")


if __name__ == "__main__":
    main()
