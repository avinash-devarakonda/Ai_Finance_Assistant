"""
Generate realistic, privacy-safe synthetic datasets for the Finora.

Run from the project root:
    python datasets/generate_datasets.py

The data is deterministic (fixed random seed) so that model results are
reproducible. No real banking or personal information is used.
"""
from __future__ import annotations

import calendar
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

BASE_DIR = Path(__file__).resolve().parent
CATEGORIES = [
    "Food",
    "Transport",
    "Shopping",
    "Bills",
    "Entertainment",
    "Health",
    "Education",
    "Other",
]

MERCHANTS = {
    "Food": [
        ("Swiggy", "Swiggy dinner order", 280, 950),
        ("Zomato", "Zomato lunch order", 220, 800),
        ("Dominos", "Dominos pizza night", 350, 1200),
        ("BigBasket", "BigBasket grocery shopping", 700, 3200),
        ("Local Cafe", "Coffee and breakfast at cafe", 120, 600),
        ("Blinkit", "Blinkit groceries and snacks", 300, 1500),
        ("Haldirams", "Haldirams family dinner", 450, 1800),
    ],
    "Transport": [
        ("Uber", "Uber ride to office", 120, 650),
        ("Ola", "Ola cab ride", 100, 600),
        ("Delhi Metro", "Metro recharge", 100, 500),
        ("IndianOil", "Petrol refill at IndianOil", 500, 2800),
        ("IRCTC", "IRCTC train ticket booking", 400, 2500),
        ("Rapido", "Rapido bike taxi", 60, 320),
        ("Fastag", "Fastag toll recharge", 200, 1200),
    ],
    "Shopping": [
        ("Amazon", "Amazon electronics purchase", 600, 6500),
        ("Flipkart", "Flipkart home essentials", 450, 5000),
        ("Myntra", "Myntra clothing purchase", 500, 4200),
        ("DMart", "DMart monthly household shopping", 800, 5500),
        ("Croma", "Croma gadget accessory", 400, 4000),
        ("Nykaa", "Nykaa personal care order", 300, 2500),
        ("Decathlon", "Decathlon sports gear", 500, 4500),
    ],
    "Bills": [
        ("Airtel", "Airtel postpaid bill", 399, 1200),
        ("Jio", "Jio fiber broadband bill", 599, 1800),
        ("Electricity Board", "Electricity bill payment", 500, 3500),
        ("Water Works", "Water utility bill", 150, 800),
        ("Gas Agency", "LPG cylinder booking", 700, 1300),
        ("Rent", "House rent payment", 6000, 18000),
        ("BSNL", "BSNL landline bill", 300, 900),
    ],
    "Entertainment": [
        ("Netflix", "Netflix monthly subscription", 199, 799),
        ("Spotify", "Spotify premium subscription", 119, 399),
        ("PVR", "PVR movie tickets", 300, 1400),
        ("BookMyShow", "BookMyShow concert tickets", 400, 2500),
        ("Steam", "Steam game purchase", 300, 2200),
        ("Hotstar", "Hotstar annual subscription", 299, 1499),
        ("Smaaash", "Smaaash gaming evening", 500, 1800),
    ],
    "Health": [
        ("Apollo Pharmacy", "Apollo Pharmacy medicines", 150, 2000),
        ("1mg", "1mg health supplements", 200, 1800),
        ("City Hospital", "City Hospital consultation", 500, 3500),
        ("Cult Fit", "Cult Fit gym membership", 800, 3000),
        ("Dr Mehta", "Doctor consultation fee", 400, 1500),
        ("Practo", "Practo lab test booking", 300, 2500),
        ("Wellness Forever", "Wellness Forever pharmacy", 120, 1400),
    ],
    "Education": [
        ("Udemy", "Udemy online course purchase", 400, 3500),
        ("Coursera", "Coursera specialization fee", 800, 4500),
        ("Amazon Books", "Amazon technical books", 250, 1800),
        ("School Fees", "School tuition fee payment", 2500, 12000),
        ("Coaching Center", "Competitive exam coaching fee", 1500, 8000),
        ("Stationery Shop", "Stationery and notebooks", 100, 700),
        ("NPTEL", "NPTEL exam registration", 500, 1500),
    ],
    "Other": [
        ("ATM", "ATM cash withdrawal", 500, 5000),
        ("LIC", "LIC insurance premium", 1000, 6000),
        ("Donation", "Charity donation", 200, 2000),
        ("Post Office", "Post office charges", 50, 500),
        ("Misc Store", "Miscellaneous household item", 100, 900),
        ("Bank", "Bank service charges", 50, 400),
        ("Gift Shop", "Birthday gift purchase", 300, 2500),
    ],
}

INCOME_MERCHANTS = [
    ("Salary", "Monthly salary credit"),
    ("Freelance Client", "Freelance project payment"),
    ("Interest", "Savings account interest"),
    ("Refund", "Online order refund"),
]

DESCRIPTION_PREFIXES = [
    "",
    "UPI payment for ",
    "Card payment for ",
    "Paid via wallet for ",
    "Auto-debit for ",
    "Online payment for ",
]


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def previous_month(today: date | None = None) -> date:
    today = today or date.today()
    return add_months(month_start(today), -1)


def generate_transactions() -> pd.DataFrame:
    """Create 1,600 labelled expense records spread over 24 months."""
    today = date.today()
    end = previous_month(today)
    start = add_months(end, -23)
    total_days = (end - start).days + 1

    rows = []
    txn_id = 10001
    for _ in range(1600):
        category = random.choices(CATEGORIES, weights=[24, 15, 17, 15, 10, 8, 6, 5])[0]
        merchant, base_description, low, high = random.choice(MERCHANTS[category])
        amount = round(random.uniform(low, high), 0)
        # Add moderate right-skew to amounts.
        amount = round(amount * random.uniform(0.85, 1.25), 0)

        offset = random.randint(0, total_days - 1)
        txn_date = start + timedelta(days=offset)
        prefix = random.choice(DESCRIPTION_PREFIXES)
        description = f"{prefix}{base_description}".strip()
        if category == "Food" and random.random() < 0.25:
            description += random.choice([" with friends", " after work", " weekend treat"])

        rows.append(
            {
                "transaction_id": txn_id,
                "date": txn_date.isoformat(),
                "description": description,
                "amount": int(amount),
                "transaction_type": "Expense",
                "category": category,
                "merchant": merchant,
            }
        )
        txn_id += 1

    df = pd.DataFrame(rows)
    # Deliberately introduce a few blank descriptions / duplicates to prove the
    # cleaning pipeline handles them, then let the training script deduplicate.
    df.loc[df.sample(frac=0.01, random_state=SEED).index, "description"] = ""
    df = pd.concat([df, df.sample(12, random_state=SEED)], ignore_index=True)
    return df.sample(frac=1, random_state=SEED).reset_index(drop=True)


def generate_monthly_expenses() -> pd.DataFrame:
    """Generate 60 months of category-wise expenses with trend + seasonality."""
    today = date.today()
    end = previous_month(today)
    start = add_months(end, -59)
    rows = []

    base = {
        "food_expenses": 6200,
        "transport_expenses": 3200,
        "shopping_expenses": 4800,
        "bills_expenses": 9800,
        "health_expenses": 1800,
        "entertainment_expenses": 1600,
        "education_expenses": 2200,
        "other_expenses": 1400,
    }
    growth = {
        "food_expenses": 0.007,
        "transport_expenses": 0.004,
        "shopping_expenses": 0.009,
        "bills_expenses": 0.005,
        "health_expenses": 0.010,
        "entertainment_expenses": 0.006,
        "education_expenses": 0.003,
        "other_expenses": 0.002,
    }
    season = {
        "food_expenses": 0.10,
        "transport_expenses": 0.06,
        "shopping_expenses": 0.24,
        "bills_expenses": 0.12,
        "health_expenses": 0.09,
        "entertainment_expenses": 0.18,
        "education_expenses": 0.05,
        "other_expenses": 0.05,
    }

    for i in range(60):
        current = add_months(start, i)
        is_festival_month = current.month in (10, 11)
        row = {"month": current.month, "year": current.year}
        for key, base_value in base.items():
            trend = (1 + growth[key]) ** i
            seasonal = 1 + season[key] * np.sin((current.month / 12) * 2 * np.pi)
            festival = 1.18 if is_festival_month and key in ("shopping_expenses", "food_expenses") else 1.0
            noise = np.random.normal(1.0, 0.055)
            value = base_value * trend * seasonal * festival * noise
            if key == "bills_expenses" and current.month in (5, 6, 7):
                value *= 1.20  # summer cooling bills
            row[key] = int(round(min(max(value, 500), 45000), 0))
        row["total_expenses"] = sum(row[key] for key in base)
        rows.append(row)

    return pd.DataFrame(rows)


def generate_budgets(monthly: pd.DataFrame) -> pd.DataFrame:
    """Create budget history for five synthetic users."""
    rows = []
    recent = monthly.tail(12).copy()
    for user_id in range(1, 6):
        factor = [0.85, 0.95, 1.05, 1.15, 0.90][user_id - 1]
        for _, month_row in recent.iterrows():
            month_label = f"{int(month_row['year'])}-{int(month_row['month']):02d}"
            for category in CATEGORIES:
                key = f"{category.lower()}_expenses"
                actual = int(round(month_row[key] * factor * random.uniform(0.82, 1.18)))
                budget = int(round(actual * random.uniform(0.95, 1.35), -2))
                rows.append(
                    {
                        "user_id": user_id,
                        "month": month_label,
                        "category": category,
                        "budget_limit": max(budget, 500),
                        "actual_expense": actual,
                    }
                )
    return pd.DataFrame(rows)


def generate_insights() -> pd.DataFrame:
    """Rule templates consumed by the rule-based insight engine."""
    rows = [
        ("food_up", "Your food expenses increased by {change}% compared with last month."),
        ("food_down", "Your food expenses decreased by {change}% compared with last month."),
        ("shopping_up", "Your shopping expenses increased by {change}% compared with last month."),
        ("shopping_down", "Your shopping expenses decreased by {change}% compared with last month."),
        ("transport_up", "Your transport expenses increased by {change}% compared with last month."),
        ("transport_down", "Your transport expenses decreased by {change}% compared with last month."),
        ("category_exceeded", "You have exceeded your {category} budget by INR {amount}."),
        ("category_near_limit", "Your {category} budget is {percent}% utilized. You are close to the limit."),
        ("savings_improved", "Your monthly savings improved by INR {amount} compared with last month."),
        ("savings_declined", "Your monthly savings declined by INR {amount} compared with last month."),
        ("expenses_over_income", "Your expenses are higher than your income this month."),
        ("highest_category", "Your highest spending category is {category} at INR {amount}."),
        ("no_budget", "You have not set budgets for {month}. Add budgets to track spending limits."),
        ("budget_on_track", "You are within budget in {count} categories this month. Keep it up."),
        ("forecast_rise", "Your estimated expenses for next month are INR {amount}, a {change}% rise."),
        ("forecast_fall", "Your estimated expenses for next month are INR {amount}, a {change}% fall."),
        ("low_data", "Add transactions across at least two months to unlock month-over-month insights."),
        ("income_added", "Your income this month is INR {amount}. Maintaining a savings rate above 20% is a healthy habit."),
        ("top_merchant", "Your top merchant this month is {merchant}, with spending of INR {amount}."),
        ("budget_exceeded_count", "You have exceeded {count} category budget(s) this month."),
        ("savings_rate", "Your savings rate this month is {rate}% of your income."),
        ("no_transactions", "No transactions found for this period. Add your first transaction to get insights."),
    ]
    return pd.DataFrame(rows, columns=["condition", "insight"])


def main() -> None:
    transactions = generate_transactions()
    monthly = generate_monthly_expenses()
    budgets = generate_budgets(monthly)
    insights = generate_insights()

    transactions.to_csv(BASE_DIR / "expense_transactions.csv", index=False)
    monthly.to_csv(BASE_DIR / "monthly_expenses.csv", index=False)
    budgets.to_csv(BASE_DIR / "budget_data.csv", index=False)
    insights.to_csv(BASE_DIR / "financial_insights.csv", index=False)

    print(f"Wrote {len(transactions):,} transactions")
    print(f"Wrote {len(monthly):,} monthly expense rows")
    print(f"Wrote {len(budgets):,} budget rows")
    print(f"Wrote {len(insights):,} insight templates")


if __name__ == "__main__":
    main()
