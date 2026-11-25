"""Password hashing (PBKDF2, standard library) and signed bearer tokens (HMAC-SHA256)."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time

from fastapi import HTTPException, Request

ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def _sign(body: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()


def make_token(user_id: int, secret: str, hours: int) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + hours * 3600}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{body}.{_sign(body, secret)}"


def read_token(token: str, secret: str) -> int | None:
    try:
        body, signature = token.split(".")
        if not hmac.compare_digest(_sign(body, secret), signature):
            return None
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if payload["exp"] < time.time():
            return None
        return int(payload["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, binascii.Error):
        return None


def current_user(request: Request) -> dict:
    """FastAPI dependency: returns the logged-in user or raises 401."""
    from .config import settings

    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please log in to use this feature.")
    user_id = read_token(header[7:].strip(), settings.auth_secret)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Please log in again.")
    user = request.app.state.db.one("SELECT id, name, email, language FROM users WHERE id = ?", (user_id,))
    if user is None:
        raise HTTPException(status_code=401, detail="Account not found. Please register again.")
    return user
