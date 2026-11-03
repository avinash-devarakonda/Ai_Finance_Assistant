"""AI insights route."""
from __future__ import annotations

from flask import Blueprint, g, request

from services.insights_service import generate_insights
from utils.responses import error, success

insights_bp = Blueprint("insights", __name__)


@insights_bp.get("")
@insights_bp.get("/")
def insights():
    try:
        items = generate_insights(g.current_user["user_id"], request.args.get("month"))
        return success({"insights": items, "count": len(items), "source": "rule-based analysis"})
    except ValueError as exc:
        return error(str(exc), 422)
    except Exception as exc:  # pragma: no cover - defensive API boundary
        return error(f"Unable to generate insights: {exc}", 500)
