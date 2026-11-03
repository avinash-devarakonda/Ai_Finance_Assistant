"""Finance assistant chatbot route."""
from __future__ import annotations

from flask import Blueprint, g, request

from services.chatbot_service import DISCLAIMER, answer
from utils.responses import error, success

chatbot_bp = Blueprint("chatbot", __name__)


@chatbot_bp.post("")
@chatbot_bp.post("/")
def chat():
    payload = request.get_json(silent=True) or {}
    message = " ".join(str(payload.get("message") or "").strip().split())
    if not message:
        return error("Message is required", 422)
    if len(message) > 500:
        return error("Message must be 500 characters or fewer", 422)

    result = answer(g.current_user["user_id"], message)
    result["disclaimer"] = DISCLAIMER
    result["suggestions"] = result.get(
        "suggestions",
        [
            "How much did I spend this month?",
            "What is my highest spending category?",
            "Predict my next month's expenses",
        ],
    )
    return success(result)
