from collections import deque
from datetime import UTC, datetime
from hashlib import sha256
from threading import Lock
from time import monotonic

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User

_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_dummy_hash = _hasher.hash("dummy authentication timing comparison")
_attempts: dict[str, deque[float]] = {}
_attempt_lock = Lock()


def guard_password_request(request: Request, username: str) -> None:
    if not settings.auth_session_secret:
        raise HTTPException(503, "Password sign-in is not configured.")
    origin = request.headers.get("origin")
    if origin and origin not in {
        *settings.cors_origins,
        str(request.base_url).rstrip("/"),
    }:
        raise HTTPException(403, "Sign-in origin is not allowed.")
    # Local single-process protection; a public multi-worker deployment needs
    # a shared limiter at the gateway or Redis, and must trust proxy IPs explicitly.
    ip = request.client.host if request.client else "unknown"
    keys = [(f"ip:{ip}", 30), (f"name:{sha256(username.encode()).hexdigest()}", 8)]
    now = monotonic()
    with _attempt_lock:
        for key in list(_attempts):
            while _attempts[key] and _attempts[key][0] <= now - 900:
                _attempts[key].popleft()
            if not _attempts[key]:
                del _attempts[key]
        if any(len(_attempts.get(key, ())) >= limit for key, limit in keys):
            raise HTTPException(
                429,
                "Too many sign-in attempts. Try again in 15 minutes.",
                headers={"Retry-After": "900"},
            )
        for key, _ in keys:
            _attempts.setdefault(key, deque()).append(now)


def register_password_account(db: Session, username: str, password: str) -> User:
    user = User(
        username=username,
        password_hash=_hasher.hash(password),
        display_name=username,
        email_verified=False,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "That username is unavailable.") from error
    db.refresh(user)
    return user


def authenticate_password(db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    encoded = user.password_hash if user and user.password_hash else _dummy_hash
    try:
        _hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError) as error:
        raise HTTPException(401, "Incorrect username or password.") from error
    if user is None or user.password_hash is None:
        raise HTTPException(401, "Incorrect username or password.")
    if _hasher.check_needs_rehash(encoded):
        user.password_hash = _hasher.hash(password)
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return user
