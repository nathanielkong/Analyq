from collections import deque
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.requests import Request
from test_assistant import make_interpretation, make_quote, make_stock
from test_research_reports import db, scenario  # noqa: F401 - shared fixtures

from app.api.schema.research_report import ResearchChatRequest
from app.api.routes import assistant as assistant_routes
from app.clients.gemini import GeminiClientError
from app.api.services import assistant_services, password_auth, research_report_services
from app.api.services.chat_services import ChatSessionNotFoundError
from app.api.services.generation_control import (
    GenerationCancelled,
    cancel_generation,
    check_generation,
    finish_generation,
    register_generation,
)
from app.core.config import settings
from app.db.session import get_db_session
from app.main import create_app
from app.models.chat import ChatMessage, ChatSession
from app.models.research_report import ResearchReport
from app.models.user import User


@pytest.fixture
def auth_client(db, monkeypatch):
    monkeypatch.setattr(
        settings, "auth_session_secret", "test-only-secret-with-more-than-32-characters"
    )
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    monkeypatch.setattr(password_auth, "_attempts", {})
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    with TestClient(app) as client:
        yield client


def test_password_registration_login_and_private_response(auth_client, db):
    credentials = {"username": "Researcher", "password": "A long test passphrase!"}
    response = auth_client.post("/auth/register", json=credentials)
    assert response.status_code == 201
    assert response.json()["username"] == "researcher"
    assert "password" not in str(response.json())
    assert "HttpOnly" in response.headers["set-cookie"]
    user = db.scalar(select(User))
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != credentials["password"]
    assert auth_client.get("/auth/me").json()["id"] == str(user.id)
    auth_client.delete("/auth/session")
    assert auth_client.get("/auth/me").status_code == 401
    assert auth_client.post("/auth/login", json=credentials).status_code == 200
    assert auth_client.post("/auth/register", json=credentials).status_code == 409


@pytest.mark.parametrize("status", [429, 503, 504])
def test_chat_preserves_provider_status_and_does_not_save_failed_turn(
    auth_client, db, monkeypatch, status
):
    session = ChatSession(title="Provider failure")
    db.add(session)
    db.commit()

    def fail(*args, **kwargs):
        raise GeminiClientError("Actionable provider error", status)

    monkeypatch.setattr(assistant_routes, "answer_research_chat", fail)
    response = auth_client.post(
        "/assistant/chat",
        json={
            "session_id": str(session.id),
            "request_id": str(uuid4()),
            "message": "SOXL premarket?",
        },
    )
    assert response.status_code == status
    assert response.json()["detail"] == "Actionable provider error"
    assert db.scalar(select(ChatMessage)) is None


def test_password_failure_is_generic_and_weak_password_rejected(auth_client):
    credentials = {"username": "researcher", "password": "A long test passphrase!"}
    assert auth_client.post("/auth/register", json=credentials).status_code == 201
    wrong = auth_client.post("/auth/login", json={**credentials, "password": "wrong"})
    missing = auth_client.post(
        "/auth/login", json={**credentials, "username": "missing"}
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()
    invalid = auth_client.post(
        "/auth/register", json={**credentials, "password": "pw-42"}
    )
    assert invalid.status_code == 422
    assert "pw-42" not in invalid.text
    assert all("input" not in item for item in invalid.json()["detail"])
    assert (
        auth_client.post(
            "/auth/login",
            json=credentials,
            headers={"Origin": "https://untrusted.test"},
        ).status_code
        == 403
    )


def test_password_rate_limit_and_expired_attempts(monkeypatch):
    monkeypatch.setattr(settings, "auth_session_secret", "test")
    monkeypatch.setattr(password_auth, "monotonic", lambda: 1000)
    monkeypatch.setattr(
        password_auth, "_attempts", {"ip:test": deque([0] * 30 + [950])}
    )
    request = Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("test", 80),
            "path": "/",
            "headers": [],
            "client": ("test", 1234),
        }
    )
    for _ in range(8):
        password_auth.guard_password_request(request, "researcher")
    with pytest.raises(HTTPException) as error:
        password_auth.guard_password_request(request, "researcher")
    assert error.value.status_code == 429
    assert len(password_auth._attempts["ip:test"]) == 9


def test_cancel_before_start_and_completed_race(db, scenario):
    session, _, _ = scenario
    request_id = uuid4()
    assert cancel_generation(db, session.id, request_id, None) == "stopped"
    register_generation(db, session.id, request_id, None)
    with pytest.raises(GenerationCancelled):
        check_generation(db, request_id)
    with pytest.raises(GenerationCancelled):
        finish_generation(db, request_id)
    db.rollback()
    completed_id = uuid4()
    register_generation(db, session.id, completed_id, None)
    finish_generation(db, completed_id)
    db.commit()
    assert cancel_generation(db, session.id, completed_id, None) == "completed"


def test_cancel_cannot_access_another_account_or_chat(db, scenario):
    session, _, _ = scenario
    with pytest.raises(ChatSessionNotFoundError):
        cancel_generation(db, session.id, uuid4(), uuid4())
    request_id = uuid4()
    register_generation(db, session.id, request_id, None)
    other = ChatSession(title="Other")
    db.add(other)
    db.commit()
    with pytest.raises(ValueError):
        cancel_generation(db, other.id, request_id, None)


def test_cancel_after_model_returns_rolls_back_turn_and_report(
    db, scenario, monkeypatch
):
    session, client, _ = scenario
    request = ResearchChatRequest(
        session_id=session.id, request_id=uuid4(), message="Analyze NVIDIA"
    )
    cancelled = False
    original = client.generate_chat_response

    def generate(*args):
        nonlocal cancelled
        response = original(*args)
        cancelled = True
        return response

    def check():
        if cancelled:
            raise GenerationCancelled()

    monkeypatch.setattr(client, "generate_chat_response", generate)
    with pytest.raises(GenerationCancelled):
        research_report_services.answer_research_chat(
            db, request, None, client, check_cancelled=check
        )
    db.rollback()
    assert db.scalar(select(ChatMessage)) is None
    assert db.scalar(select(ResearchReport)) is None


def test_fund_skips_company_fundamentals(monkeypatch):
    calls = []
    monkeypatch.setattr(
        assistant_services, "get_stock_quote", lambda symbol: make_quote()
    )
    monkeypatch.setattr(
        assistant_services,
        "get_stock_fundamentals",
        lambda symbol: calls.append(symbol),
    )
    stock = make_stock().model_copy(
        update={
            "symbol": "SOXL",
            "type": "ETF",
            "name": "Daily Semiconductor Bull 3X ETF",
        }
    )
    research = assistant_services.collect_stock_research(
        stock, make_interpretation(["quote", "fundamentals"])
    )
    assert calls == []
    assert research.fundamentals_error is None
    assert research.instrument["kind"] == "fund"
    assert research.instrument["leverage_in_name"] == 3
    assistant_services.collect_stock_research(
        make_stock(), make_interpretation(["quote", "fundamentals"])
    )
    assert calls == ["NVDA"]
