"""ML expense category classification service."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import joblib

from config import Config

_model_bundle = None
_model_lock = threading.Lock()


class ModelUnavailableError(RuntimeError):
    pass


def _load():
    global _model_bundle
    if _model_bundle is not None:
        return _model_bundle
    with _model_lock:
        if _model_bundle is not None:
            return _model_bundle
        path = Path(Config.CLASSIFIER_MODEL)
        if not path.exists():
            raise ModelUnavailableError(
                "Expense classification model is not trained. Run: python backend/ml/train_classifier.py"
            )
        _model_bundle = joblib.load(path)
        return _model_bundle


def reload_model() -> None:
    global _model_bundle
    with _model_lock:
        _model_bundle = None


def predict_category(description: str, amount: float, transaction_type: str = "Expense") -> dict:
    from ml.feature_utils import build_classifier_text

    bundle = _load()
    pipeline = bundle["pipeline"]
    text = build_classifier_text(description, amount, transaction_type)
    prediction = str(pipeline.predict([text])[0])

    confidence = 0.0
    probabilities: list[dict] = []
    if hasattr(pipeline, "predict_proba"):
        proba = pipeline.predict_proba([text])[0]
        classes = [str(value) for value in pipeline.classes_]
        probabilities = sorted(
            [
                {"category": label, "confidence": round(float(score), 4)}
                for label, score in zip(classes, proba)
            ],
            key=lambda item: item["confidence"],
            reverse=True,
        )
        confidence = probabilities[0]["confidence"] if probabilities else 0.0

    return {
        "predicted_category": prediction,
        "confidence": round(float(confidence), 4),
        "alternatives": probabilities[1:4],
        "model": bundle.get("model_name", "Trained classifier"),
    }


def model_info() -> dict:
    try:
        bundle = _load()
    except ModelUnavailableError as exc:
        return {"available": False, "message": str(exc)}
    info = {
        "available": True,
        "model_name": bundle.get("model_name"),
        "labels": bundle.get("labels"),
        "trained_at": bundle.get("trained_at"),
        "training_rows": bundle.get("training_rows"),
        "test_rows": bundle.get("test_rows"),
        "metrics": bundle.get("metrics"),
    }
    metrics_path = Path(Config.ML_DIR) / "classifier_metrics.json"
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            info["comparison"] = metrics.get("comparison", {})
            info["confusion_matrix"] = metrics.get("confusion_matrix", [])
        except (OSError, json.JSONDecodeError):
            pass
    return info
