"""Authentication helpers with a reusable request authenticator."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Callable

import jwt
from flask import g, request

from config import Config
from database import db
from utils.responses import error

_revoked_tokens: set[str] = set()
_revoked_lock = threading.Lock()


def create_access_token(user: dict) -> tuple[str, int]:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=Config.JWT_EXPIRES_SECONDS)
    jti = f"{user['user_id']}-{int(issued_at.timestamp() * 1000)}"
    payload = {
        "sub": str(user["user_id"]),
        "email": user["email"],
        "name": user["name"],
        "iat": issued_at,
        "exp": expires_at,
        "jti": jti,
    }
    token = jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)
    return token, int(expires_at.timestamp())


def decode_token(token: str) -> dict:
    return jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])


def revoke_token(jti: str) -> None:
    with _revoked_lock:
        _revoked_tokens.add(jti)


def is_revoked(jti: str) -> bool:
    with _revoked_lock:
        return jti in _revoked_tokens


def _extract_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[7:].strip()
    return token or None


def authenticate_request():
    """Authenticate the current request and populate Flask's g object.

    Returns an error response tuple when authentication fails, otherwise None.
    This function is used by the global API guard and the route decorator.
    """
    token = _extract_token()
    if not token:
        return error("Authentication required", 401)

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        return error("Your session has expired. Please log in again.", 401)
    except jwt.InvalidTokenError:
        return error("Invalid authentication token", 401)

    if is_revoked(payload.get("jti", "")):
        return error("This session has been logged out", 401)

    user_id = payload.get("sub")
    if not user_id:
        return error("Invalid authentication token", 401)

    user = db.fetch_one(
        "SELECT user_id, name, email, created_at FROM users WHERE user_id = %s",
        (user_id,),
    )
    if not user:
        return error("User account no longer exists", 401)

    g.current_user = user
    g.jwt_payload = payload
    return None


def auth_required(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        failure = authenticate_request()
        if failure:
            return failure
        return view(*args, **kwargs)

    return wrapped
