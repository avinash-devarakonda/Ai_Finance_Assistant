"""Consistent JSON response helpers."""
from __future__ import annotations

from flask import jsonify


def success(data=None, message: str | None = None, status: int = 200):
    payload = {"success": True}
    if message:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def error(message: str, status: int = 400, errors: dict | list | None = None):
    payload = {"success": False, "message": message}
    if errors:
        payload["errors"] = errors
    return jsonify(payload), status
