from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes import auth as auth_routes
from app.api.services import auth_services
from app.api.services.auth_services import (
    GoogleAuthenticationError,
    create_session_token,
    decode_session_token,
    verify_google_credential,
)
from app.core.config import settings
from app.main import create_app


def test_session_token_round_trip(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "auth_session_secret",
        "test-session-secret-at-least-32-bytes",
    )
    user_id = uuid4()

    token = create_session_token(user_id)

    assert decode_session_token(token) == user_id


def test_invalid_session_token_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "auth_session_secret",
        "test-session-secret-at-least-32-bytes",
    )

    with pytest.raises(GoogleAuthenticationError, match="session is invalid"):
        decode_session_token("not-a-jwt")


def test_google_credential_requires_verified_email(monkeypatch) -> None:
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(
        auth_services.id_token,
        "verify_oauth2_token",
        lambda credential, request, audience: {
            "sub": "google-user-1",
            "email": "person@example.com",
            "email_verified": False,
        },
    )

    with pytest.raises(GoogleAuthenticationError, match="email is not verified"):
        verify_google_credential("credential")


def test_auth_config_reports_google_availability(monkeypatch) -> None:
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(
        settings,
        "auth_session_secret",
        "test-session-secret-at-least-32-bytes",
    )
    client = TestClient(create_app())

    response = client.get("/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "password_enabled": True,
        "google_enabled": True,
        "google_client_id": "test-client-id",
    }


def test_google_login_sets_http_only_application_cookie(monkeypatch) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="person@example.com",
        display_name="Example Person",
        avatar_url="https://example.com/avatar.png",
        created_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        auth_routes,
        "authenticate_with_google",
        lambda db, credential: user,
    )
    monkeypatch.setattr(
        auth_routes,
        "create_session_token",
        lambda authenticated_user_id: "signed-session",
    )
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(
        settings,
        "auth_session_secret",
        "test-session-secret-at-least-32-bytes",
    )
    client = TestClient(create_app())

    response = client.post("/auth/google", json={"credential": "google-id-token"})

    assert response.status_code == 200
    assert response.json()["id"] == str(user_id)
    cookie = response.headers["set-cookie"]
    assert f"{settings.auth_cookie_name}=signed-session" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


def test_auth_me_requires_a_valid_session() -> None:
    client = TestClient(create_app())

    response = client.get("/auth/me")

    assert response.status_code == 401


def test_logout_clears_application_cookie() -> None:
    client = TestClient(create_app())

    response = client.delete("/auth/session")

    assert response.status_code == 204
    assert f"{settings.auth_cookie_name}=\"\"" in response.headers["set-cookie"]
