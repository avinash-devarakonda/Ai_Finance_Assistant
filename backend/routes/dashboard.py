"""Dashboard aggregation route."""
from __future__ import annotations

from flask import Blueprint, g, request

from services.dashboard_service import get_dashboard
from utils.responses import error, success

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("")
@dashboard_bp.get("/")
def dashboard():
    try:
        data = get_dashboard(g.current_user["user_id"], request.args)
        return success(data)
    except ValueError as exc:
        return error(str(exc), 422)
    except Exception as exc:  # pragma: no cover - defensive API boundary
        return error(f"Unable to build dashboard: {exc}", 500)
