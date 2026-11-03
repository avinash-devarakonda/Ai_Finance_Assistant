"""
End-to-end API smoke tests.

Run from the project root:
    python backend/test_api.py

The test uses a temporary SQLite database so that it does not modify MySQL or
your development data. The production application uses MySQL.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

TEMP_DB = Path(tempfile.gettempdir()) / "finora_api_test.sqlite3"
if TEMP_DB.exists():
    TEMP_DB.unlink()
os.environ["DB_ENGINE"] = "sqlite"
os.environ["SQLITE_PATH"] = str(TEMP_DB)
os.environ["FLASK_ENV"] = "testing"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["JWT_SECRET"] = "test-jwt-secret"

from app import create_app  # noqa: E402

app = create_app()
client = app.test_client()
failures: list[str] = []


def check(condition, message):
    if condition:
        print(f"  PASS  {message}")
    else:
        print(f"  FAIL  {message}")
        failures.append(message)


def add_months(base: date, offset: int) -> date:
    month_index = base.month - 1 + offset
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base.day, 28)
    return date(year, month, day)


def main():
    print("Finora API smoke tests")
    health = client.get("/api/health")
    check(health.status_code == 200 and health.get_json()["data"]["database"]["connected"], "Health check")

    unauthorized = client.get("/api/dashboard")
    check(unauthorized.status_code == 401, "Protected route rejects anonymous access")

    register = client.post(
        "/api/register",
        json={"name": "Test Student", "email": "student@example.com", "password": "StrongPass123"},
    )
    check(register.status_code == 201, "User registration")
    token = register.get_json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    duplicate = client.post(
        "/api/register",
        json={"name": "Test Student", "email": "student@example.com", "password": "StrongPass123"},
    )
    check(duplicate.status_code == 409, "Duplicate email rejected")

    bad_login = client.post("/api/login", json={"email": "student@example.com", "password": "wrong"})
    check(bad_login.status_code == 401, "Incorrect password rejected")

    login = client.post(
        "/api/login", json={"email": "student@example.com", "password": "StrongPass123"}
    )
    check(login.status_code == 200, "User login")
    token = login.get_json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    prediction = client.post(
        "/api/predict-category",
        json={"description": "Swiggy dinner", "amount": 450, "transaction_type": "Expense"},
        headers=headers,
    )
    prediction_data = prediction.get_json().get("data", {})
    check(prediction.status_code == 200, "ML category prediction endpoint")
    check(prediction_data.get("predicted_category") == "Food", "Classifier predicts Food for Swiggy")
    check(0 <= prediction_data.get("confidence", -1) <= 1, "Prediction confidence is in [0, 1]")

    today = date.today()
    created_ids = []
    # Three months of history power forecasting and insights.
    for offset in (-3, -2, -1, 0):
        expense_date = add_months(today, offset)
        for description, amount, merchant in [
            ("Swiggy dinner order", 850, "Swiggy"),
            ("Uber ride to office", 450, "Uber"),
            ("Electricity bill payment", 1600, "Electricity Board"),
        ]:
            response = client.post(
                "/api/transactions",
                json={
                    "date": expense_date.isoformat(),
                    "description": description,
                    "amount": amount,
                    "transaction_type": "Expense",
                    "merchant": merchant,
                },
                headers=headers,
            )
            check(response.status_code == 201, f"Create expense: {description}")
            created_ids.append(response.get_json()["data"]["transaction"]["transaction_id"])
        income = client.post(
            "/api/transactions",
            json={
                "date": expense_date.isoformat(),
                "description": "Monthly salary",
                "amount": 50000,
                "transaction_type": "Income",
                "category": "Salary",
                "merchant": "Employer",
            },
            headers=headers,
        )
        check(income.status_code == 201, "Create income transaction")

    listing = client.get("/api/transactions?per_page=50", headers=headers)
    check(listing.status_code == 200, "List transactions")
    check(listing.get_json()["data"]["pagination"]["total"] == 16, "Transaction count is accurate")

    first_txn = created_ids[0]
    update = client.put(
        f"/api/transactions/{first_txn}",
        json={"category": "Health"},
        headers=headers,
    )
    check(update.status_code == 200, "Update transaction")
    updated = update.get_json()["data"]["transaction"]
    check(updated["category"] == "Health", "Corrected category persisted")
    check(updated.get("was_corrected") is True, "Prediction correction recorded")

    delete_response = client.delete(f"/api/transactions/{created_ids[-1]}", headers=headers)
    check(delete_response.status_code == 200, "Delete transaction")

    month_value = today.strftime("%Y-%m")
    budget = client.post(
        "/api/budgets",
        json={"month": month_value, "category": "Food", "limit_amount": 5000},
        headers=headers,
    )
    check(budget.status_code == 201, "Create budget")
    budgets = client.get(f"/api/budgets?month={month_value}", headers=headers)
    budget_data = budgets.get_json().get("data", {})
    check(budgets.status_code == 200, "Get budgets")
    check(len(budget_data.get("budgets", [])) == 1, "Budget list returned")
    check(
        budget_data["budgets"][0]["actual_expense"] > 0,
        "Budget actual spend comes from transactions",
    )
    budget_id = budget_data["budgets"][0]["budget_id"]
    edit = client.put(
        f"/api/budgets/{budget_id}", json={"limit_amount": 6000}, headers=headers
    )
    check(edit.status_code == 200, "Edit budget")

    dashboard = client.get("/api/dashboard?range=this_month", headers=headers)
    dashboard_data = dashboard.get_json().get("data", {})
    check(dashboard.status_code == 200, "Dashboard endpoint")
    check(dashboard_data["summary"]["total_expenses"] > 0, "Dashboard expenses are dynamic")
    check(dashboard_data["summary"]["total_income"] > 0, "Dashboard income is dynamic")
    check(len(dashboard_data["monthly_series"]) == 12, "Monthly series returned")

    insights = client.get("/api/insights", headers=headers)
    insight_data = insights.get_json().get("data", {})
    check(insights.status_code == 200, "Insights endpoint")
    check(insight_data.get("count", 0) > 0, "Personalized insights generated")

    forecast = client.post("/api/predict-expenses", json={}, headers=headers)
    check(forecast.status_code == 200, "Forecast endpoint")
    check(
        forecast.get_json()["data"]["forecast"].get("insufficient_data") is False,
        "Forecast uses user history",
    )

    chat = client.post(
        "/api/chatbot",
        json={"message": "What is my highest spending category?"},
        headers=headers,
    )
    check(chat.status_code == 200, "Chatbot endpoint")
    check("category" in chat.get_json()["data"]["reply"].lower(), "Chatbot answers with user data")

    report = client.get(f"/api/reports?month={month_value}", headers=headers)
    check(report.status_code == 200, "Reports endpoint")

    csv_export = client.get(f"/api/reports/export?format=csv&month={month_value}", headers=headers)
    check(csv_export.status_code == 200 and csv_export.data.startswith(b"\xef\xbb\xbf"), "CSV export")
    pdf_export = client.get(f"/api/reports/export?format=pdf&month={month_value}", headers=headers)
    check(pdf_export.status_code == 200 and pdf_export.data.startswith(b"%PDF"), "PDF export")

    models = client.get("/api/ml/models", headers=headers)
    check(models.status_code == 200, "ML model metadata endpoint")

    logout = client.post("/api/logout", headers=headers)
    check(logout.status_code == 200, "Logout")
    after_logout = client.get("/api/dashboard", headers=headers)
    check(after_logout.status_code == 401, "Revoked token rejected")

    print()
    if failures:
        print(f"{len(failures)} test(s) failed")
        return 1
    print("All API smoke tests passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        if TEMP_DB.exists():
            try:
                TEMP_DB.unlink()
            except OSError:
                pass
