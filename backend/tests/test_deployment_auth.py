from types import SimpleNamespace

import pytest
from app.api.routes import chat
from app.api.services.auth_services import get_optional_current_user
from app.core.config import settings
from app.db.session import get_db_session
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def protected_app(monkeypatch):
    monkeypatch.setattr(settings, "require_auth", True)
    monkeypatch.setattr(settings, "auth_session_secret", "test-only-" + "a" * 40)
    app = create_app()
    app.dependency_overrides[get_optional_current_user] = lambda: None
    return app


@pytest.mark.parametrize(
    "path",
    [
        "/stocks/NVDA",
        "/stocks/NVDA/patterns/backtest",
        "/chat/sessions",
        "/market/watch",
        "/assistant/sessions/00000000-0000-0000-0000-000000000001/reports",
    ],
)
def test_deployment_rejects_guest_before_research(protected_app, path):
    assert TestClient(protected_app).get(path).status_code == 401


def test_deployment_keeps_health_and_login_config_public(protected_app):
    client = TestClient(protected_app)
    assert client.get("/health").status_code == 200
    assert client.get("/auth/config").status_code == 200


def test_deployment_allows_authenticated_route(protected_app, monkeypatch):
    user = SimpleNamespace(id="signed-in")
    protected_app.dependency_overrides[get_optional_current_user] = lambda: user

    protected_app.dependency_overrides[get_db_session] = lambda: None
    monkeypatch.setattr(chat, "list_chat_sessions", lambda db, user_id: [])
    response = TestClient(protected_app).get("/chat/sessions")
    assert response.status_code == 200
    assert response.json() == []


def test_deployment_requires_strong_session_secret(monkeypatch):
    monkeypatch.setattr(settings, "require_auth", True)
    monkeypatch.setattr(settings, "auth_session_secret", "short")
    with pytest.raises(ValueError, match="AUTH_SESSION_SECRET"):
        create_app()
