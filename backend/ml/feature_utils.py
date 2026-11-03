"""Shared feature engineering for the expense classifier."""
from __future__ import annotations

import re

AMOUNT_BUCKETS = (
    (500, "amt_very_low"),
    (1500, "amt_low"),
    (5000, "amt_medium"),
    (15000, "amt_high"),
)

STOP_WORDS = {
    "payment",
    "paid",
    "for",
    "via",
    "card",
    "upi",
    "online",
    "the",
    "and",
    "with",
    "at",
    "of",
    "to",
}


def clean_text(value: object) -> str:
    text = "" if value is None else str(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def amount_bucket(amount: object) -> str:
    try:
        numeric = float(amount)
    except (TypeError, ValueError):
        numeric = 0.0
    for threshold, label in AMOUNT_BUCKETS:
        if numeric < threshold:
            return label
    return "amt_very_high"


def build_classifier_text(description: object, amount: object, transaction_type: object = "Expense") -> str:
    """Combine description, amount band and type into tokens for TF-IDF.

    Amount bands let the classifier learn realistic spending ranges without
    leaking the target category. The API and training script use this exact
    function, which keeps inference consistent with training.
    """
    text = clean_text(description)
    txn_type = clean_text(transaction_type) or "expense"
    return f"{text} {amount_bucket(amount)} type_{txn_type}".strip()
