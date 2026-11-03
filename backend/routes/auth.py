"""Authentication routes."""
from __future__ import annotations

from flask import Blueprint, g, request
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from models.serializers import serialize_user
from utils.auth import auth_required, create_access_token, revoke_token
from utils.responses import error, success
from utils.validators import ValidationError, validate_login, validate_registration

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    try:
        data = validate_registration(payload)
    except ValidationError as exc:
        return error(str(exc), 422)

    existing = db.fetch_one("SELECT user_id FROM users WHERE email = %s", (data["email"],))
    if existing:
        return error("An account with this email already exists", 409)

    user_id = db.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
        (data["name"], data["email"], generate_password_hash(data["password"])),
        return_id=True,
    )
    user = db.fetch_one(
        "SELECT user_id, name, email, created_at FROM users WHERE user_id = %s",
        (user_id,),
    )
    token, expires_at = create_access_token(user)
    return success(
        {"token": token, "expires_at": expires_at, "user": serialize_user(user)},
        "Account created successfully",
        201,
    )


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    try:
        data = validate_login(payload)
    except ValidationError as exc:
        return error(str(exc), 422)

    user = db.fetch_one("SELECT * FROM users WHERE email = %s", (data["email"],))
    if not user or not check_password_hash(user["password_hash"], data["password"]):
        return error("Incorrect email or password", 401)

    token, expires_at = create_access_token(user)
    return success(
        {"token": token, "expires_at": expires_at, "user": serialize_user(user)},
        "Logged in successfully",
    )


@auth_bp.post("/logout")
@auth_required
def logout():
    payload = g.get("jwt_payload") or {}
    if payload.get("jti"):
        revoke_token(payload["jti"])
    return success(message="Logged out successfully")


@auth_bp.get("/me")
@auth_required
def me():
    return success({"user": serialize_user(g.current_user)})
