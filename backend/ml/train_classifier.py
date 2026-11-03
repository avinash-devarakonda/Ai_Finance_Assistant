"""
Train and evaluate the expense category classifier.

Usage:
    python backend/ml/train_classifier.py

Models compared: Logistic Regression, Multinomial Naive Bayes, Random Forest.
The best model (by weighted F1) is persisted with Joblib together with its
TF-IDF pipeline, labels, metrics and training metadata.
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
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

ML_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ML_DIR.parent.parent
DATASET = PROJECT_ROOT / "datasets" / "expense_transactions.csv"
MODEL_PATH = ML_DIR / "expense_classifier.pkl"
METRICS_PATH = ML_DIR / "classifier_metrics.json"
PLOT_PATH = ML_DIR / "confusion_matrix.png"

sys.path.insert(0, str(ML_DIR))
from feature_utils import build_classifier_text  # noqa: E402


def load_and_clean() -> pd.DataFrame:
    if not DATASET.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET}. Run datasets/generate_datasets.py first.")
    df = pd.read_csv(DATASET)
    required = {
        "transaction_id",
        "date",
        "description",
        "amount",
        "transaction_type",
        "category",
        "merchant",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")

    df = df.drop_duplicates(subset=["transaction_id"]).copy()
    df["description"] = df["description"].fillna("").astype(str).str.strip()
    df.loc[df["description"].eq(""), "description"] = df["merchant"].fillna("misc expense").astype(str)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["amount"] = df["amount"].fillna(df["amount"].median())
    df["transaction_type"] = df["transaction_type"].fillna("Expense")
    df["category"] = df["category"].fillna("Other").str.strip().str.title()
    df = df[df["amount"] > 0]
    df["text"] = [
        build_classifier_text(d, a, t)
        for d, a, t in zip(df["description"], df["amount"], df["transaction_type"])
    ]
    return df.reset_index(drop=True)


def main() -> None:
    df = load_and_clean()
    if df["category"].nunique() < 2:
        raise ValueError("At least two categories are required to train a classifier.")

    X_train, X_test, y_train, y_test = train_test_split(
        df["text"],
        df["category"],
        test_size=0.2,
        random_state=42,
        stratify=df["category"],
    )

    candidates = {
        "Logistic Regression": LogisticRegression(max_iter=1500, C=6.0, class_weight="balanced", n_jobs=None),
        "Multinomial Naive Bayes": MultinomialNB(alpha=0.25),
        "Random Forest": RandomForestClassifier(
            n_estimators=350,
            random_state=42,
            class_weight="balanced_subsample",
            n_jobs=-1,
        ),
    }

    results: dict[str, dict] = {}
    fitted: dict[str, Pipeline] = {}
    for name, classifier in candidates.items():
        pipeline = Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True, max_features=12000)),
                ("classifier", classifier),
            ]
        )
        pipeline.fit(X_train, y_train)
        predictions = pipeline.predict(X_test)
        results[name] = {
            "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
            "precision_weighted": round(float(precision_score(y_test, predictions, average="weighted", zero_division=0)), 4),
            "recall_weighted": round(float(recall_score(y_test, predictions, average="weighted", zero_division=0)), 4),
            "f1_weighted": round(float(f1_score(y_test, predictions, average="weighted", zero_division=0)), 4),
        }
        fitted[name] = pipeline

    best_name = max(results, key=lambda key: (results[key]["f1_weighted"], results[key]["accuracy"]))
    best_pipeline = fitted[best_name]
    predictions = best_pipeline.predict(X_test)
    labels = sorted(df["category"].unique().tolist())
    matrix = confusion_matrix(y_test, predictions, labels=labels)
    report = classification_report(y_test, predictions, output_dict=True, zero_division=0)

    # Visualise the confusion matrix for the notebook / project report.
    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(matrix, interpolation="nearest", cmap="Blues")
    ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set(
        xticks=np.arange(len(labels)),
        yticks=np.arange(len(labels)),
        xticklabels=labels,
        yticklabels=labels,
        ylabel="Actual category",
        xlabel="Predicted category",
        title=f"Expense Classifier - {best_name}",
    )
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center", color="black", fontsize=9)
    fig.tight_layout()
    fig.savefig(PLOT_PATH, dpi=160)
    plt.close(fig)

    bundle = {
        "pipeline": best_pipeline,
        "model_name": best_name,
        "labels": labels,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "metrics": results[best_name],
    }
    joblib.dump(bundle, MODEL_PATH)

    metrics = {
        "best_model": best_name,
        "comparison": results,
        "classification_report": report,
        "confusion_matrix": matrix.tolist(),
        "labels": labels,
        "dataset_rows": int(len(df)),
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "trained_at": bundle["trained_at"],
        "top_features": {},
    }

    # Most informative features for interpretability (linear models only).
    classifier = best_pipeline.named_steps["classifier"]
    vectorizer = best_pipeline.named_steps["tfidf"]
    if hasattr(classifier, "coef_"):
        feature_names = np.asarray(vectorizer.get_feature_names_out())
        if classifier.coef_.shape[0] == 1:
            coefs = classifier.coef_[0]
            top = np.argsort(coefs)[-10:][::-1]
            metrics["top_features"] = {str(feature_names[i]): round(float(coefs[i]), 4) for i in top}
        else:
            for idx, label in enumerate(classifier.classes_):
                coefs = classifier.coef_[idx]
                top = np.argsort(coefs)[-8:][::-1]
                metrics["top_features"][str(label)] = {
                    str(feature_names[i]): round(float(coefs[i]), 4) for i in top
                }

    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Best model: {best_name}")
    for name, scores in results.items():
        print(f"  {name:24s} accuracy={scores['accuracy']:.4f}  weighted-F1={scores['f1_weighted']:.4f}")
    print(f"Saved model to {MODEL_PATH}")
    print(f"Saved metrics to {METRICS_PATH}")


if __name__ == "__main__":
    main()
