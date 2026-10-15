from uuid import uuid4

import jwt
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import get_db_session
from app.main import create_app
from test_research_reports import db  # noqa: F401


def test_guests_can_start_private_chats_but_cannot_list_or_cross_access(db, monkeypatch):
    monkeypatch.setattr(settings, "require_auth", True)
    monkeypatch.setattr(settings, "allow_guest_research", True)
    monkeypatch.setattr(settings, "auth_session_secret", "guest-test-" + "a" * 40)
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    client = TestClient(app)
    first = client.post("/chat/sessions", json={"title": "First guest"})
    second = client.post("/chat/sessions", json={"title": "Second guest"})
    assert first.status_code == second.status_code == 201
    chat = first.json()
    headers = {"X-Guest-Chat": chat["guest_token"]}
    path = f'/chat/sessions/{chat["id"]}/messages'
    assert client.get("/chat/sessions").json() == []
    assert client.get(path).status_code == 403
    assert client.get(path, headers=headers).status_code == 200
    assert client.get(path, headers={"X-Guest-Chat": second.json()["guest_token"]}).status_code == 403
    assert client.get(path, headers={"X-Guest-Chat": "invalid"}).status_code == 403
    expired = jwt.encode({"sub": chat["id"], "purpose": "guest-chat", "exp": 1}, settings.auth_session_secret, algorithm="HS256")
    assert client.get(path, headers={"X-Guest-Chat": expired}).status_code == 403
    assert client.post("/assistant/chat", json={"session_id": second.json()["id"], "request_id": str(uuid4()), "message": "Price?"}, headers=headers).status_code == 403
    assert client.delete(f'/chat/sessions/{second.json()["id"]}', headers=headers).status_code == 403
