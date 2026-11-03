"""Create (or reset) a fully populated demo account.

Usage:
    python backend/seed_demo.py

The demo account is:
    Email:    demo@finora.local
    Password: Demo@1234

Running the script is idempotent: it removes only the demo user's records and
regenerates eight months of deterministic transactions and budgets. The
current month always contains expenses so forecasting and dashboards work
immediately.
"""
from __future__ import annotations

import calendar
import random
from datetime import date

from werkzeug.security import generate_password_hash

from config import Config
from database import db
from services.classifier_service import ModelUnavailableError, predict_category
from utils.dates import add_months, month_label, today

DEMO_NAME = "Aarav Mehta"
DEMO_EMAIL = "demo@finora.local"
DEMO_PASSWORD = "Demo@1234"

BUDGETS = {
    "Food": 9000,
    "Transport": 4500,
    "Shopping": 6000,
    "Bills": 5500,
    "Entertainment": 2500,
    "Health": 3000,
    "Education": 2200,
}

FOOD = [
    ("Swiggy dinner order", "Swiggy", 220, 850),
    ("Zomato lunch order", "Zomato", 180, 700),
    ("BigBasket monthly groceries", "BigBasket", 1200, 3200),
    ("DMart grocery run", "DMart", 800, 2600),
    ("Local cafe coffee and snacks", "Third Wave Coffee", 180, 550),
    ("Bakery breakfast", "Bakery", 90, 320),
    ("Dinner with friends", "Barbeque Nation", 900, 2400),
]

TRANSPORT = [
    ("Uber ride to office", "Uber", 110, 420),
    ("Ola cab back home", "Ola", 120, 480),
    ("Metro card recharge", "Delhi Metro", 200, 500),
    ("Petrol refill", "Indian Oil", 1500, 3200),
    ("Auto rickshaw fare", "Local Auto", 60, 180),
    ("Rapido bike ride", "Rapido", 60, 240),
]

SHOPPING = [
    ("Amazon household order", "Amazon", 450, 2800),
    ("Flipkart electronics accessory", "Flipkart", 600, 3500),
    ("Myntra clothing purchase", "Myntra", 800, 3200),
    ("Decathlon sports gear", "Decathlon", 700, 2600),
    ("Home decor from Ikea", "Ikea", 500, 2200),
]

ENTERTAINMENT = [
    ("Netflix monthly subscription", "Netflix", 199, 649),
    ("PVR movie tickets", "PVR Cinemas", 400, 1200),
    ("Spotify premium", "Spotify", 119, 199),
    ("Weekend gaming purchase", "Steam", 300, 1500),
]

HEALTH = [
    ("Apollo Pharmacy medicines", "Apollo Pharmacy", 250, 1400),
    ("Gym monthly membership", "Cult.fit", 1200, 2200),
    ("Doctor consultation fee", "Apollo Clinic", 500, 1500),
    ("Diagnostic lab tests", "Dr Lal PathLabs", 700, 2400),
]

EDUCATION = [
    ("Udemy course purchase", "Udemy", 500, 1800),
    ("Coursera subscription", "Coursera", 900, 2600),
    ("Technical books order", "Amazon Books", 400, 1500),
    ("Stationery and printing", "Local Stationery", 150, 600),
]

OTHER = [
    ("Gift for family", "Gift Shop", 500, 2000),
    ("Bank service charge", "HDFC Bank", 50, 250),
    ("Donation to charity", "Give India", 300, 1500),
    ("Household miscellaneous", "Local Store", 200, 1200),
]

BILLS = [
    ("Electricity bill payment", "BSES", 1100, 2900, 5),
    ("Airtel broadband bill", "Airtel", 999, 999, 3),
    ("Jio mobile recharge", "Jio", 399, 799, 8),
    ("LPG cylinder booking", "Indane Gas", 850, 1100, 12),
]


def _ensure_schema() -> None:
    if Config.DB_ENGINE == "sqlite":
        db.init_sqlite()
        return
    try:
        db.fetch_one("SELECT user_id FROM users LIMIT 1")
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "MySQL schema not found. Run `python backend/init_db.py` after configuring .env, "
            f"or set DB_ENGINE=sqlite for a local demo. Details: {exc}"
        ) from exc


def _month_days(year: int, month: int, current: date) -> int:
    last_day = calendar.monthrange(year, month)[1]
    if (year, month) == (current.year, current.month):
        return max(1, current.day)
    return last_day


def _rows_for_month(year: int, month: int, current: date) -> list[dict]:
    rng = random.Random(year * 100 + month)
    max_day = _month_days(year, month, current)
    rows: list[dict] = []

    def add(day: int, description: str, merchant: str, amount: float, category: str, kind: str) -> None:
        safe_day = max(1, min(day, max_day))
        rows.append(
            {
                "date": date(year, month, safe_day).isoformat(),
                "description": description,
                "merchant": merchant,
                "amount": round(amount, 2),
                "category": category,
                "type": kind,
            }
        )

    # Income
    add(1, "Monthly salary credit", "Infosys Ltd", 92000, "Salary", "Income")
    if month % 3 == 0:
        add(18, "Freelance web project payment", "Upwork", rng.randint(12000, 26000), "Freelance", "Income")
    if month % 4 == 0:
        add(22, "Mutual fund dividend", "Groww", rng.randint(1200, 4200), "Investments", "Income")

    # Bills
    for description, merchant, low, high, day in BILLS:
        add(day, description, merchant, rng.randint(low, high), "Bills", "Expense")

    # Food
    for _ in range(rng.randint(6, 9)):
        description, merchant, low, high = rng.choice(FOOD)
        add(rng.randint(1, max_day), description, merchant, rng.randint(low, high), "Food", "Expense")

    # Transport
    for _ in range(rng.randint(4, 6)):
        description, merchant, low, high = rng.choice(TRANSPORT)
        add(rng.randint(1, max_day), description, merchant, rng.randint(low, high), "Transport", "Expense")

    # Shopping
    for _ in range(rng.randint(2, 4)):
        description, merchant, low, high = rng.choice(SHOPPING)
        add(rng.randint(1, max_day), description, merchant, rng.randint(low, high), "Shopping", "Expense")

    # Entertainment
    for _ in range(rng.randint(1, 3)):
        description, merchant, low, high = rng.choice(ENTERTAINMENT)
        add(rng.randint(1, max_day), description, merchant, rng.randint(low, high), "Entertainment", "Expense")

    # Health
    for _ in range(rng.randint(1, 2)):
        description, merchant, low, high = rng.choice(HEALTH)
        add(rng.randint(1, max_day), description, merchant, rng.randint(low, high), "Health", "Expense")

    # Education
    for _ in range(rng.randint(0, 2)):
        description, merchant, low, high = rng.choice(EDUCATION)
        add(rng.randint(1, max_day), description, merchant, rng.randint(low, high), "Education", "Expense")

    # Other
    for _ in range(rng.randint(1, 2)):
        description, merchant, low, high = rng.choice(OTHER)
        add(rng.randint(1, max_day), description, merchant, rng.randint(low, high), "Other", "Expense")

    # In some months, deliberately overshoot one budget so demo insights show
    # a warning and an exceeded budget instead of an artificially perfect month.
    if month % 5 == 0:
        add(
            rng.randint(10, max_day),
            "Festival shopping haul",
            "Amazon",
            rng.randint(4500, 7500),
            "Shopping",
            "Expense",
        )

    rows.sort(key=lambda item: (item["date"], item["description"]))
    return rows


def _insert_transaction(user_id: int, item: dict) -> None:
    transaction_id = db.execute(
        """
        INSERT INTO transactions (user_id, date, description, amount, type, category, merchant)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            item["date"],
            item["description"],
            item["amount"],
            item["type"],
            item["category"],
            item["merchant"],
        ),
        return_id=True,
    )

    if item["type"] != "Expense":
        return

    try:
        result = predict_category(item["description"], item["amount"], "Expense")
    except ModelUnavailableError:
        return

    predicted = result["predicted_category"]
    corrected = predicted != item["category"]
    db.execute(
        """
        INSERT INTO predictions
            (user_id, transaction_id, predicted_category, confidence, corrected_category, was_corrected)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            transaction_id,
            predicted,
            float(result["confidence"]),
            item["category"] if corrected else None,
            1 if corrected else 0,
        ),
    )


def seed() -> dict:
    _ensure_schema()

    user = db.fetch_one("SELECT user_id FROM users WHERE email = %s", (DEMO_EMAIL,))
    if user:
        user_id = int(user["user_id"])
        db.execute("DELETE FROM predictions WHERE user_id = %s", (user_id,))
        db.execute("DELETE FROM transactions WHERE user_id = %s", (user_id,))
        db.execute("DELETE FROM budgets WHERE user_id = %s", (user_id,))
        db.execute(
            "UPDATE users SET name = %s, password_hash = %s WHERE user_id = %s",
            (DEMO_NAME, generate_password_hash(DEMO_PASSWORD), user_id),
        )
    else:
        user_id = int(
            db.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
                (DEMO_NAME, DEMO_EMAIL, generate_password_hash(DEMO_PASSWORD)),
                return_id=True,
            )
        )

    current = today()
    start_year, start_month = add_months(current.year, current.month, -7)
    transaction_count = 0

    for offset in range(8):
        year, month = add_months(start_year, start_month, offset)
        if (year, month) > (current.year, current.month):
            break
        for item in _rows_for_month(year, month, current):
            _insert_transaction(user_id, item)
            transaction_count += 1

        for category, limit in BUDGETS.items():
            db.execute(
                "INSERT INTO budgets (user_id, month, category, limit_amount) VALUES (%s, %s, %s, %s)",
                (user_id, month_label(year, month), category, limit),
            )

    return {
        "user_id": user_id,
        "transactions": transaction_count,
        "budgets": 8 * len(BUDGETS),
        "first_month": f"{start_year:04d}-{start_month:02d}",
        "last_month": f"{current.year:04d}-{current.month:02d}",
    }


def main() -> None:
    summary = seed()
    print("Demo account ready")
    print(f"  Email:       {DEMO_EMAIL}")
    print(f"  Password:    {DEMO_PASSWORD}")
    print(f"  Name:        {DEMO_NAME}")
    print(f"  Transactions:{summary['transactions']:>4} ({summary['first_month']} to {summary['last_month']})")
    print(f"  Budgets:     {summary['budgets']:>4}")
    if Config.DB_ENGINE == "sqlite":
        print(f"  Database:    SQLite at {Config.SQLITE_PATH}")
    else:
        print(f"  Database:    MySQL {Config.DB_NAME} at {Config.DB_HOST}:{Config.DB_PORT}")


if __name__ == "__main__":
    main()
