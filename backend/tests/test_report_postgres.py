"""Opt-in PostgreSQL locking test, isolated in a throwaway schema.

ANALYQ_POSTGRES_TEST=1 .venv/bin/python -m pytest tests/test_report_postgres.py
"""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from test_assistant import make_quote, make_stock
from test_research_reports import FakeClient

from app.api.schema.assistant import AssistantResearchResponse
from app.api.schema.research_report import ResearchChatRequest
from app.api.services import research_report_services as services
from app.core.config import settings
from app.db.base import Base
from app.models.chat import ChatMessage, ChatSession
from app.models.research_report import ResearchReport
from app.models.user import User
from app.api.services.generation_control import (
    GenerationCancelled,
    register_generation,
    cancel_generation,
    check_generation,
    finish_generation,
)


@pytest.mark.skipif(
    os.getenv("ANALYQ_POSTGRES_TEST") != "1",
    reason="Opt-in real PostgreSQL integration test",
)
@pytest.mark.parametrize("different_chats", [False, True])
def test_concurrent_retry_creates_one_report_and_one_turn(monkeypatch, different_chats):
    schema = "report_test_" + uuid4().hex
    admin = create_engine(settings.database_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        settings.database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            user = User(
                google_subject="concurrency",
                email="concurrency@example.test",
                display_name="Test",
            )
            db.add(user)
            db.flush()
            user_id = user.id
            session = ChatSession(title="Isolated concurrency test", user_id=user_id)
            db.add(session)
            other = ChatSession(title="Second concurrent chat", user_id=user_id)
            db.add(other)
            db.commit()
            session_id = session.id
            other_id = other.id
        client = FakeClient()
        collections = []

        def collect(stock, interpretation, **kwargs):
            collections.append(stock.symbol)
            return AssistantResearchResponse(
                stock=stock, quote=make_quote(), interpretation=interpretation
            )

        monkeypatch.setattr(services, "collect_stock_research", collect)
        monkeypatch.setattr(services, "_resolve_stock", lambda query: make_stock())
        request = ResearchChatRequest(
            session_id=session_id, request_id=uuid4(), message="Analyze NVIDIA"
        )

        requests = [
            request,
            ResearchChatRequest(
                session_id=other_id, request_id=uuid4(), message="Analyze NVIDIA"
            )
            if different_chats
            else request,
        ]

        def send(request):
            with Session(engine) as db:
                return services.answer_research_chat(db, request, user_id, client)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(send, requests))
        assert (first.message.id != second.message.id) == different_chats
        assert collections == ["NVDA"]
        assert len(client.calls) == (2 if different_chats else 1)
        assert sum(bool(call[1]) for call in client.calls) == 1
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(ResearchReport)) == (
                2 if different_chats else 1
            )
            assert db.scalar(select(func.count()).select_from(ChatMessage)) == (
                4 if different_chats else 2
            )
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.skipif(
    os.getenv("ANALYQ_POSTGRES_TEST") != "1", reason="Opt-in PostgreSQL test"
)
def test_stop_does_not_wait_for_locked_chat_or_save_late_answer(monkeypatch):
    schema = "cancel_test_" + uuid4().hex
    admin = create_engine(settings.database_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        settings.database_url,
        connect_args={"options": f"-csearch_path={schema} -cstatement_timeout=5000"},
    )
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            session = ChatSession(title="Cancellation test")
            db.add(session)
            db.commit()
            session_id = session.id
        request = ResearchChatRequest(
            session_id=session_id, request_id=uuid4(), message="Analyze NVIDIA"
        )
        with Session(engine) as db:
            register_generation(db, session_id, request.request_id, None)
        entered, release = Event(), Event()
        client = FakeClient()
        original = client.generate_chat_response

        def slow_generate(*args):
            entered.set()
            assert release.wait(10)
            return original(*args)

        monkeypatch.setattr(client, "generate_chat_response", slow_generate)
        monkeypatch.setattr(services, "_resolve_stock", lambda query: make_stock())
        monkeypatch.setattr(
            services,
            "collect_stock_research",
            lambda stock, interpretation, **kwargs: AssistantResearchResponse(
                stock=stock, quote=make_quote(), interpretation=interpretation
            ),
        )

        def generate():
            with Session(engine) as db:
                with pytest.raises(GenerationCancelled):
                    services.answer_research_chat(
                        db,
                        request,
                        None,
                        client,
                        check_cancelled=lambda: check_generation(
                            db, request.request_id
                        ),
                        finish=lambda: finish_generation(db, request.request_id),
                    )
                db.rollback()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(generate)
            try:
                assert entered.wait(10)
                with Session(engine) as db:
                    assert (
                        cancel_generation(db, session_id, request.request_id, None)
                        == "stopped"
                    )
            finally:
                release.set()
            future.result(timeout=10)
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(ChatMessage)) == 0
            assert db.scalar(select(func.count()).select_from(ResearchReport)) == 0
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
