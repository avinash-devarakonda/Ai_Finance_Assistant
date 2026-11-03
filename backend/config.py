"""Application configuration loaded from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = Path(__file__).resolve().parent

# Load root .env first, then allow backend/.env to override during development.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BASE_DIR / ".env", override=True)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = ENV == "development"
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
    JWT_SECRET = os.getenv("JWT_SECRET", SECRET_KEY)
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRES_HOURS = _int("JWT_EXPIRES_HOURS", 24)
    JWT_EXPIRES_SECONDS = JWT_EXPIRES_HOURS * 3600

    DB_ENGINE = os.getenv("DB_ENGINE", "mysql").strip().lower()
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = _int("DB_PORT", 3306)
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "finora")
    SQLITE_PATH = os.getenv("SQLITE_PATH", str(BASE_DIR / "finora.sqlite3"))

    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
        ).split(",")
        if origin.strip()
    ]

    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    JSON_SORT_KEYS = False

    DATASETS_DIR = PROJECT_ROOT / "datasets"
    ML_DIR = BASE_DIR / "ml"
    TRANSACTIONS_DATASET = DATASETS_DIR / "expense_transactions.csv"
    MONTHLY_DATASET = DATASETS_DIR / "monthly_expenses.csv"
    INSIGHTS_DATASET = DATASETS_DIR / "financial_insights.csv"
    CLASSIFIER_MODEL = ML_DIR / "expense_classifier.pkl"
    FORECAST_MODEL = ML_DIR / "expense_forecasting.pkl"


def mysql_settings(include_database: bool = True) -> dict:
    settings = {
        "host": Config.DB_HOST,
        "port": Config.DB_PORT,
        "user": Config.DB_USER,
        "password": Config.DB_PASSWORD,
        "charset": "utf8mb4",
        "autocommit": False,
    }
    if include_database:
        settings["database"] = Config.DB_NAME
    return settings
