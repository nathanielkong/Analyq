from uuid import uuid4

import pytest
from sqlalchemy import DefaultClause, MetaData, create_engine, event, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_assistant import make_interpretation, make_quote, make_stock

from app.api.schema.assistant import AssistantExplanation, AssistantResearchResponse
from app.api.schema.research_report import (
    DeepDiveExplanation,
    ReportNarrative,
    ResearchChatGeneration,
    ResearchChatRequest,
)
from app.api.services import research_report_services as services
from app.api.services.chat_services import ChatSessionNotFoundError
from app.clients.gemini import GeminiClientError
from app.db.base import Base
from app.models.chat import ChatMessage, ChatSession
from app.models.research_report import ResearchReport
from app.core.report_policy import REPORT_SECTIONS


@compiles(JSONB, "sqlite")
def jsonb_as_json(type_, compiler, **kwargs):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(metadata)
    metadata.tables["chat_messages"].c.message_metadata.server_default = DefaultClause(
        text("'{}'")
    )
    metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


class FakeClient:
    def __init__(self):
        self.interpretation = make_interpretation(["quote"])
        self.calls = []
        self.fail = False

    def interpret_stock_prompt(self, message, conversation_context=None):
        return self.interpretation

    def generate_chat_response(
        self, message, interpretation, evidence, report_symbols, context
    ):
        self.calls.append((evidence, report_symbols, context))
        if self.fail:
            raise GeminiClientError("test outage")
        return ResearchChatGeneration(
            answer=AssistantExplanation(answer="Answer grounded in saved evidence."),
            reports=[
                ReportNarrative(
                    symbol=symbol,
                    explanation=DeepDiveExplanation(
                        answer="Standalone company report.",
                        sections=[
                            {"label": label, "content": "Saved evidence."}
                            for label in REPORT_SECTIONS
                        ],
                    ),
                )
                for symbol in report_symbols
            ],
        )


@pytest.fixture
def scenario(db, monkeypatch):
    session = ChatSession(title="Test research")
    db.add(session)
    db.commit()
    collection_calls = []

    def collect(stock, interpretation, **kwargs):
        collection_calls.append(stock.symbol)
        return AssistantResearchResponse(
            stock=stock,
            quote=make_quote().model_copy(update={"symbol": stock.symbol}),
            interpretation=interpretation,
        )

    def resolve(query):
        if query == "INTC":
            return make_stock().model_copy(
                update={"symbol": "INTC", "name": "Intel Corporation"}
            )
        return (
            make_stock().model_copy(
                update={"symbol": "AMD", "name": "Advanced Micro Devices"}
            )
            if query == "AMD"
            else make_stock()
        )

    monkeypatch.setattr(services, "collect_stock_research", collect)
    monkeypatch.setattr(services, "_resolve_stock", resolve)
    return session, FakeClient(), collection_calls


def ask(db, session, client, message="Analyze NVIDIA", **kwargs):
    return services.answer_research_chat(
        db,
        ResearchChatRequest(
            session_id=session.id, request_id=uuid4(), message=message, **kwargs
        ),
        None,
        client,
    )


def test_first_question_saves_one_report_followup_uses_evidence_without_collection(
    db, scenario
):
    session, client, calls = scenario
    first = ask(db, session, client)
    second = ask(db, session, client, "What is its price?")
    assert calls == ["NVDA"]
    assert len(second.reports) == 1
    assert first.reports[0].id == second.reports[0].id
    assert client.calls[0][1] == ["NVDA"]
    assert client.calls[1][1] == []
    assert "fundamentals" not in client.calls[1][0]["NVDA"]["data"]
    assert len(list(db.scalars(select(ChatMessage)))) == 4
    assert second.message.message_metadata["report_ids"] == [str(first.reports[0].id)]
    assert "quote" not in second.message.message_metadata


def test_comparison_does_not_create_reports_and_reuses_existing(db, scenario):
    session, client, calls = scenario
    ask(db, session, client)
    client.interpretation = make_interpretation(["quote"]).model_copy(
        update={"intent": "stock_comparison", "stock_queries": ["NVDA", "AMD"]}
    )
    comparison = ask(db, session, client, "Compare NVIDIA and AMD")
    assert calls == ["NVDA", "AMD"]
    assert len(comparison.reports) == 1
    assert client.calls[-1][1] == []
    assert comparison.message.message_metadata["report_ids"] == []
    assert comparison.message.message_metadata["stock_symbols"] == ["NVDA", "AMD"]


@pytest.mark.parametrize("requested_reports", [[], ["NVDA"], ["NVDA", "AMD", "INTC"]])
def test_three_stock_comparison_only_creates_explicitly_requested_reports(
    db, scenario, requested_reports
):
    session, client, calls = scenario
    client.interpretation = make_interpretation(["quote"]).model_copy(
        update={
            "intent": "stock_comparison",
            "stock_queries": ["NVDA", "AMD", "INTC"],
            "report_queries": requested_reports,
        }
    )
    result = ask(db, session, client, "Compare NVDA, AMD and INTC")
    assert calls == ["NVDA", "AMD", "INTC"]
    assert {report.symbol for report in result.reports} == set(requested_reports)
    assert client.calls[-1][1] == requested_reports
    assert result.message.message_metadata["comparison"] is not None
    assert len(result.message.message_metadata["report_ids"]) == len(requested_reports)
    assert len(list(db.scalars(select(ResearchReport)))) == len(requested_reports)
    for report in result.reports:
        assert report.research.explanation is not None
        assert len(report.research.explanation.sections) == 8

    # A later comparison reuses data but does not regenerate reports or link them.
    client.interpretation = client.interpretation.model_copy(
        update={"report_queries": []}
    )
    followup = ask(db, session, client, "Which is best for growth?")
    assert client.calls[-1][1] == []
    assert followup.message.message_metadata["report_ids"] == []
    assert len(followup.reports) == len(requested_reports)


def test_report_selection_cannot_introduce_an_unrequested_stock():
    from app.api.schema.assistant import StockPromptInterpretation

    data = make_interpretation(["quote"]).model_dump()
    data["report_queries"] = ["UNREQUESTED"]
    with pytest.raises(ValueError, match="Report identities"):
        StockPromptInterpretation.model_validate(data)


def test_explicit_report_alias_is_not_lost_when_ticker_appears_first(db, scenario):
    session, client, calls = scenario
    client.interpretation = make_interpretation(["quote"]).model_copy(
        update={
            "intent": "stock_comparison",
            "stock_queries": ["NVDA", "NVIDIA", "AMD"],
            "report_queries": ["NVIDIA"],
        }
    )
    result = ask(db, session, client, "Compare NVIDIA and AMD; report on NVIDIA")
    assert calls == ["NVDA", "AMD"]
    assert [report.symbol for report in result.reports] == ["NVDA"]
    assert client.calls[-1][1] == ["NVDA"]


def test_new_stock_adds_tab_and_refresh_updates_same_report(db, scenario):
    session, client, calls = scenario
    first = ask(db, session, client)
    client.interpretation = make_interpretation(["quote"], stock_query="AMD")
    second = ask(db, session, client, "Analyze AMD")
    assert len(second.reports) == 2
    third = ask(
        db, session, client, "Refresh NVDA", refresh_report_id=first.reports[0].id
    )
    assert len(third.reports) == 2
    assert calls == ["NVDA", "AMD", "NVDA"]
    assert client.calls[-1][1] == ["NVDA"]


def test_duplicate_request_is_idempotent_even_after_reopening_db_session(db, scenario):
    session, client, calls = scenario
    request = ResearchChatRequest(
        session_id=session.id, request_id=uuid4(), message="Analyze NVIDIA"
    )
    first = services.answer_research_chat(db, request, None, client)
    db.expire_all()
    second = services.answer_research_chat(db, request, None, client)
    assert first.message.id == second.message.id
    assert len(client.calls) == 1
    assert calls == ["NVDA"]
    assert len(list(db.scalars(select(ChatMessage)))) == 2


def test_reports_are_session_scoped_and_wrong_owner_cannot_read(db, scenario):
    session, client, calls = scenario
    first = ask(db, session, client)
    another = ChatSession(title="Other chat")
    db.add(another)
    db.commit()
    with pytest.raises(ChatSessionNotFoundError):
        services.list_research_reports(db, session.id, uuid4())
    assert services.list_research_reports(db, another.id, None) == []
    with pytest.raises(services.AssistantRequestError, match="does not belong"):
        ask(db, another, client, "Refresh NVDA", refresh_report_id=first.reports[0].id)
    assert calls == ["NVDA"]


def test_delete_session_cascades_reports(db, scenario):
    session, client, calls = scenario
    ask(db, session, client)
    db.delete(session)
    db.commit()
    assert list(db.scalars(select(ResearchReport))) == []


def test_explanation_failure_saves_data_and_retry_does_not_recollect(db, scenario):
    session, client, calls = scenario
    client.fail = True
    first = ask(db, session, client)
    assert first.reports[0].research.explanation is None
    client.fail = False
    second = ask(db, session, client, "Explain the saved report")
    assert second.reports[0].research.explanation is not None
    assert calls == ["NVDA"]


def test_general_question_does_not_collect_or_create_report(db, scenario):
    session, client, calls = scenario
    client.interpretation = make_interpretation([]).model_copy(
        update={"intent": "general_finance", "stock_queries": []}
    )
    response = ask(db, session, client, "What does P/E mean?")
    assert response.reports == []
    assert calls == []


def test_request_rejects_blank_and_context_retains_multiple_stocks():
    with pytest.raises(ValueError):
        ResearchChatRequest(session_id=uuid4(), request_id=uuid4(), message="   ")
    context = services.conversation_context(
        [
            ChatMessage(
                role="assistant",
                content="Comparison",
                message_metadata={"stock_symbols": ["NVDA", "AMD"]},
            )
        ]
    )
    assert context[0]["stock_symbols"] == ["NVDA", "AMD"]


def test_reports_routes_persist_and_enforce_ownership(db, scenario):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.db.session import get_db_session
    from app.api.services.auth_services import get_optional_current_user
    from unittest.mock import patch

    session, client, calls = scenario
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_optional_current_user] = lambda: None
    http = TestClient(app)
    with patch.object(services, "GeminiClient", lambda: client):
        response = http.post(
            "/assistant/chat",
            json={
                "session_id": str(session.id),
                "request_id": str(uuid4()),
                "message": "Analyze NVIDIA",
            },
        )
    assert response.status_code == 200
    assert len(response.json()["reports"]) == 1
    assert http.get(f"/assistant/sessions/{session.id}/reports").status_code == 200
    assert http.get(f"/assistant/sessions/{uuid4()}/reports").status_code == 404
    assert (
        http.post(
            "/assistant/chat",
            json={
                "session_id": str(session.id),
                "request_id": str(uuid4()),
                "message": "   ",
            },
        ).status_code
        == 422
    )


def test_selected_report_supplies_verified_followup_context(db, scenario):
    session, client, calls = scenario
    first = ask(db, session, client)
    ask(
        db,
        session,
        client,
        "What about its risk?",
        context_report_id=first.reports[0].id,
    )
    assert client.calls[-1][2][-1]["stock_symbol"] == "NVDA"
    with pytest.raises(services.AssistantRequestError, match="does not belong"):
        ask(db, session, client, "What about risk?", context_report_id=uuid4())
