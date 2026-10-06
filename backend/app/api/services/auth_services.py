from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db_session
from app.models.user import User


class GoogleAuthenticationError(Exception):
    pass


def verify_google_credential(credential: str) -> dict[str, Any]:
    if not settings.google_client_id:
        raise GoogleAuthenticationError("Google sign-in is not configured.")

    try:
        payload = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as error:
        raise GoogleAuthenticationError("Google could not verify this sign-in.") from error

    if payload.get("email_verified") is not True:
        raise GoogleAuthenticationError("The Google account email is not verified.")

    return payload


def authenticate_with_google(db: Session, credential: str) -> User:
    payload = verify_google_credential(credential)
    subject = _required_claim(payload, "sub")
    email = _required_claim(payload, "email").lower()
    display_name = str(payload.get("name") or email.split("@", maxsplit=1)[0])
    avatar_url = payload.get("picture")

    user = db.scalar(select(User).where(User.google_subject == subject))

    if user is None:
        user = db.scalar(select(User).where(User.email == email))

    if user is None:
        user = User(
            google_subject=subject,
            email=email,
            display_name=display_name,
            avatar_url=str(avatar_url) if avatar_url else None,
            email_verified=True,
        )
        db.add(user)
    else:
        user.google_subject = subject
        user.email = email
        user.display_name = display_name
        user.avatar_url = str(avatar_url) if avatar_url else None
        user.email_verified = True
        user.last_login_at = datetime.now(UTC)

    db.commit()
    db.refresh(user)
    return user


def create_session_token(user_id: UUID) -> str:
    session_secret = settings.auth_session_secret

    if not session_secret:
        raise GoogleAuthenticationError("Application sessions are not configured.")

    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.auth_session_days)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": expires_at,
        },
        session_secret,
        algorithm="HS256",
    )


def decode_session_token(token: str) -> UUID:
    session_secret = settings.auth_session_secret

    if not session_secret:
        raise GoogleAuthenticationError("Application sessions are not configured.")

    try:
        payload = jwt.decode(
            token,
            session_secret,
            algorithms=["HS256"],
        )
        return UUID(str(payload["sub"]))
    except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise GoogleAuthenticationError("The application session is invalid.") from error


def get_optional_current_user(
    request: Request,
    db: Session = Depends(get_db_session),
) -> User | None:
    token = request.cookies.get(settings.auth_cookie_name)

    if not token:
        return None

    try:
        user_id = decode_session_token(token)
    except GoogleAuthenticationError:
        return None

    return db.get(User, user_id)


def get_current_user(
    user: User | None = Depends(get_optional_current_user),
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to access this account.",
        )

    return user


def _required_claim(payload: dict[str, Any], claim: str) -> str:
    value = payload.get(claim)

    if not isinstance(value, str) or not value.strip():
        raise GoogleAuthenticationError("Google returned an incomplete identity.")

    return value.strip()
