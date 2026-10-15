from datetime import UTC, datetime, timedelta
from json import JSONDecodeError
import secrets

import jwt
from fastapi import Depends, HTTPException, Request

from app.api.services.auth_services import get_optional_current_user
from app.core.config import settings


_development_secret = secrets.token_urlsafe(32)


def create_guest_token(session_id) -> str:
    return jwt.encode(
        {"sub": str(session_id), "aud": "guest-chat", "purpose": "guest-chat", "exp": datetime.now(UTC) + timedelta(hours=24)},
        settings.auth_session_secret or _development_secret,
        algorithm="HS256",
    )


async def check_guest_access(request: Request, user=Depends(get_optional_current_user)):
    if user is not None:
        return
    session_id = request.path_params.get("session_id")
    if request.url.path in {"/assistant/chat", "/assistant/research"}:
        try:
            body = await request.json()
        except JSONDecodeError:
            return  # Let FastAPI return its normal validation response.
        session_id = body.get("session_id") if isinstance(body, dict) else None
    if not session_id:
        return
    try:
        payload = jwt.decode(
            request.headers.get("X-Guest-Chat", ""),
            settings.auth_session_secret or _development_secret,
            algorithms=["HS256"],
            audience="guest-chat",
            options={"require": ["exp", "sub"]},
        )
        if payload.get("purpose") != "guest-chat" or payload["sub"] != str(session_id):
            raise ValueError("Wrong chat")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(403, "This guest chat has expired or is unavailable. Start a new chat.") from None
