"""Budget management routes."""
from __future__ import annotations

from flask import Blueprint, g, request

from services.budget_service import create_budget, delete_budget, get_budgets, update_budget
from utils.responses import error, success
from utils.validators import ValidationError, validate_budget

budgets_bp = Blueprint("budgets", __name__)


@budgets_bp.get("")
@budgets_bp.get("/")
def list_budgets():
    try:
        data = get_budgets(g.current_user["user_id"], request.args.get("month"))
        return success(data)
    except ValueError as exc:
        return error(str(exc), 422)


@budgets_bp.post("")
@budgets_bp.post("/")
def add_budget():
    payload = request.get_json(silent=True) or {}
    try:
        data = validate_budget(payload)
        budget = create_budget(g.current_user["user_id"], data)
        return success({"budget": budget}, "Budget saved successfully", 201)
    except ValidationError as exc:
        return error(str(exc), 422)
    except ValueError as exc:
        return error(str(exc), 409)


@budgets_bp.put("/<int:budget_id>")
def edit_budget(budget_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        data = validate_budget(payload, partial=True)
        budget = update_budget(g.current_user["user_id"], budget_id, data)
        return success({"budget": budget}, "Budget updated successfully")
    except ValidationError as exc:
        return error(str(exc), 422)
    except LookupError as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc), 409)


@budgets_bp.delete("/<int:budget_id>")
def remove_budget(budget_id: int):
    try:
        delete_budget(g.current_user["user_id"], budget_id)
        return success(message="Budget deleted successfully")
    except LookupError as exc:
        return error(str(exc), 404)
