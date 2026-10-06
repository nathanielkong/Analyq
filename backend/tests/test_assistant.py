import json
import httpx
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.testclient import TestClient
from google import genai
from google.genai import errors as genai_errors

from app.api.routes import assistant as assistant_routes
from app.api.schema.assistant import (
    AssistantExplanation,
    AssistantResearchResponse,
    StockPromptInterpretation,
)
from app.api.schema.stock import StockQuoteResponse, StockSearchResultResponse
from app.api.services import assistant_services
from app.api.services.assistant_services import (
    AssistantRequestError,
    research_stock_prompt,
)
from app.api.services.stock_analysis_services import StockAnalysisError
from app.api.services.stock_direction_services import DirectionModelError
from app.clients.errors import MarketDataError
from app.clients.gemini import GeminiClient, GeminiClientError
from app.clients import gemini as gemini_module
from app.main import create_app


@pytest.fixture(autouse=True)
def no_live_news_calls(monkeypatch):
    def unavailable(*args, **kwargs):
        raise MarketDataError("Optional news unavailable in unit tests")

    monkeypatch.setattr(assistant_services, "get_stock_news", unavailable)


class FakeModels:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.request: dict[str, object] | None = None

    def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.request = kwargs
        return SimpleNamespace(text=self.response_text)


class FakeSdkClient:
    def __init__(self, response_text: str) -> None:
        self.models = FakeModels(response_text)


@pytest.mark.parametrize(
    "code, status, message",
    [
        (429, 429, "quota"),
        (401, 503, "credentials"),
        (403, 503, "permissions"),
        (402, 503, "billing"),
        (400, 503, "configured model"),
        (404, 503, "configured model"),
        (504, 504, "too long"),
    ],
)
def test_gemini_api_errors_are_actionable_and_not_retried(
    code, status, message, monkeypatch, caplog
):
    sdk = FakeSdkClient("")
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise genai_errors.APIError(
            code, {"error": {"message": "SECRET_PROVIDER_PAYLOAD"}}
        )

    monkeypatch.setattr(sdk.models, "generate_content", fail)
    client = GeminiClient(client=cast(genai.Client, sdk))
    with pytest.raises(GeminiClientError) as error:
        client.interpret_stock_prompt(
            "do you think soxl will rise in pre and dip when it opens today?"
        )
    assert error.value.status_code == status
    assert message in str(error.value)
    assert len(calls) == 1
    assert f"status={code}" in caplog.text
    assert "SECRET_PROVIDER_PAYLOAD" not in caplog.text
    assert "SECRET_PROVIDER_PAYLOAD" not in str(error.value)


@pytest.mark.parametrize("recover", [True, False])
def test_transient_gemini_failure_retries_only_once(monkeypatch, recover):
    sdk = FakeSdkClient("")
    calls, delays = [], []

    def generate(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1 or not recover:
            raise genai_errors.APIError(503, {"error": {"status": "UNAVAILABLE"}})
        return SimpleNamespace(text=make_interpretation(["quote"]).model_dump_json())

    monkeypatch.setattr(sdk.models, "generate_content", generate)
    monkeypatch.setattr(gemini_module.time, "sleep", delays.append)
    client = GeminiClient(client=cast(genai.Client, sdk))
    if recover:
        assert client.interpret_stock_prompt("NVDA price").stock_queries == ["NVIDIA"]
    else:
        with pytest.raises(GeminiClientError, match="temporarily unavailable"):
            client.interpret_stock_prompt("NVDA price")
    assert len(calls) == 2
    assert len(delays) == 1
    assert 1 <= delays[0] <= 1.5


@pytest.mark.parametrize(
    "failure, status",
    [(httpx.ReadTimeout("private"), 504), (httpx.ConnectError("private"), 503)],
)
def test_network_failures_are_not_unhandled_or_automatically_retried(
    monkeypatch, failure, status
):
    sdk = FakeSdkClient("")
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise failure

    monkeypatch.setattr(sdk.models, "generate_content", fail)
    with pytest.raises(GeminiClientError) as error:
        GeminiClient(client=cast(genai.Client, sdk)).interpret_stock_prompt(
            "NVDA price"
        )
    assert error.value.status_code == status
    assert len(calls) == 1


class FakeInterpreter:
    def __init__(self, interpretation: StockPromptInterpretation) -> None:
        self.interpretation = interpretation
        self.messages: list[str] = []
        self.contexts: list[list[dict[str, object]]] = []
        self.explanation_calls: list[dict[str, object]] = []

    def interpret_stock_prompt(
        self,
        message: str,
        conversation_context: list[dict[str, object]] | None = None,
    ) -> StockPromptInterpretation:
        self.messages.append(message)
        self.contexts.append(conversation_context or [])
        return self.interpretation

    def generate_research_explanation(
        self,
        message: str,
        interpretation: StockPromptInterpretation,
        evidence: dict[str, object],
    ) -> AssistantExplanation:
        self.explanation_calls.append(
            {
                "message": message,
                "interpretation": interpretation,
                "evidence": evidence,
            }
        )
        return AssistantExplanation(
            title="NVIDIA price",
            answer=(
                "NVIDIA's latest test price is **USD 200.00**. "
                "That figure comes from the backend quote."
            ),
            sections=[],
        )


class FailingExplainer(FakeInterpreter):
    def generate_research_explanation(
        self,
        message: str,
        interpretation: StockPromptInterpretation,
        evidence: dict[str, object],
    ) -> AssistantExplanation:
        raise GeminiClientError("explanation unavailable")


def make_interpretation(
    requested_data: list[str],
    *,
    time_horizon: str = "unspecified",
    stock_query: str = "NVIDIA",
) -> StockPromptInterpretation:
    return StockPromptInterpretation.model_validate(
        {
            "intent": "stock_research",
            "stock_queries": [stock_query],
            "requested_data": requested_data,
            "time_horizon": time_horizon,
            "keywords": ["current price"],
            "requires_clarification": False,
            "clarification_question": "",
        }
    )


def make_stock() -> StockSearchResultResponse:
    return StockSearchResultResponse(
        symbol="NVDA",
        name="NVIDIA Corporation",
        type="Equity",
        region="United States",
        currency="USD",
        match_score=0.9,
    )


def make_quote() -> StockQuoteResponse:
    return StockQuoteResponse(
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        price=200.0,
        currency="USD",
        source="test",
    )


def test_gemini_client_requests_and_parses_structured_output() -> None:
    response_payload = make_interpretation(
        ["quote", "historical_analysis"]
    ).model_dump()
    fake_sdk = FakeSdkClient(json.dumps(response_payload))
    client = GeminiClient(client=cast(genai.Client, fake_sdk))

    context = [
        {
            "role": "assistant",
            "content": "NVIDIA was previously researched.",
            "stock_symbol": "NVDA",
        }
    ]
    result = client.interpret_stock_prompt(
        "How risky is it?",
        conversation_context=context,
    )

    assert result.stock_queries == ["NVIDIA"]
    assert result.requested_data == ["quote", "historical_analysis"]
    assert fake_sdk.models.request is not None
    prompt = json.loads(str(fake_sdk.models.request["contents"]))
    assert prompt["current_message"] == "How risky is it?"
    assert prompt["recent_conversation"][0]["stock_symbol"] == "NVDA"
    config = fake_sdk.models.request["config"]
    assert isinstance(config, dict)
    assert config["response_mime_type"] == "application/json"
    assert "response_json_schema" in config


def test_gemini_client_generates_grounded_structured_explanation() -> None:
    explanation = AssistantExplanation(
        title="NVIDIA price",
        answer=(
            "NVIDIA's latest backend price is **USD 200.00**. "
            "No historical analysis was requested."
        ),
        sections=[
            {
                "label": "Price context",
                "content": "The backend quote reports **USD 200.00**.",
            }
        ],
    )
    fake_sdk = FakeSdkClient(explanation.model_dump_json())
    client = GeminiClient(client=cast(genai.Client, fake_sdk))
    interpretation = make_interpretation(["quote"])

    result = client.generate_research_explanation(
        message="What is Nvidia's price?",
        interpretation=interpretation,
        evidence={"quote": {"price": 200.0, "currency": "USD"}},
    )

    assert "USD 200.00" in result.answer
    assert result.sections[0].label == "Price context"
    assert fake_sdk.models.request is not None
    prompt = json.loads(str(fake_sdk.models.request["contents"]))
    assert prompt["user_question"] == "What is Nvidia's price?"
    assert prompt["backend_evidence"]["quote"]["price"] == 200.0
    config = fake_sdk.models.request["config"]
    assert isinstance(config, dict)
    assert config["temperature"] == 0.2
    assert "response_json_schema" in config


def test_chat_generation_does_not_request_report_sections_for_followups():
    from app.api.schema.research_report import ResearchChatGeneration

    generated = ResearchChatGeneration(
        answer=AssistantExplanation(
            title="Unwanted report title",
            answer="Saved price is USD 200.",
            visuals=["price", "price"],
            sections=[{"label": "Unwanted", "content": "Do not repeat the report."}],
        )
    )
    fake_sdk = FakeSdkClient(generated.model_dump_json())
    client = GeminiClient(client=cast(genai.Client, fake_sdk))
    answer = client.generate_chat_response(
        "What is the price?",
        make_interpretation(["quote"]),
        {"NVDA": {"quote": {"price": 200}}},
        [],
        [],
    )
    assert answer.answer.sections == []
    assert answer.answer.title == ""
    assert answer.answer.visuals == ["price"]
    assert answer.reports == []
    assert fake_sdk.models.request["config"]["max_output_tokens"] == 3000
    assert json.loads(fake_sdk.models.request["contents"])["reports_to_write"] == []
    schema = fake_sdk.models.request["config"]["response_json_schema"]
    assert "reports" not in schema["properties"]
    assert "ReportNarrative" not in schema.get("$defs", {})


@pytest.mark.parametrize("symbols", [[], ["NVDA"], ["NVDA", "AMD", "INTC"]])
def test_chat_wire_schema_is_simple_but_reports_are_still_validated(symbols):
    from app.core.report_policy import REPORT_SECTIONS
    from app.api.schema.research_report import ResearchChatGeneration

    payload = {
        "answer": {"answer": "Synthetic answer."},
        "reports": [
            {
                "symbol": symbol,
                "explanation": {
                    "answer": "Synthetic report.",
                    "sections": [
                        {"label": label, "content": "Synthetic evidence."}
                        for label in REPORT_SECTIONS
                    ],
                },
            }
            for symbol in symbols
        ],
    }
    sdk = FakeSdkClient(json.dumps(payload))
    client = GeminiClient(client=cast(genai.Client, sdk))
    result = client.generate_chat_response(
        "Synthetic request", make_interpretation(["quote"]), {}, symbols, []
    )
    assert [report.symbol for report in result.reports] == symbols
    schema = sdk.models.request["config"]["response_json_schema"]
    encoded = json.dumps(schema)
    for keyword in ("minItems", "maxItems", "minLength", "maxLength"):
        assert keyword not in encoded
    assert ("reports" in schema["properties"]) == bool(symbols)
    # The provider schema does not weaken the saved/API contracts.
    local_schema = ResearchChatGeneration.model_json_schema()
    assert local_schema["properties"]["reports"]["maxItems"] == 5
    payload["answer"]["answer"] = "x" * 6001
    sdk.models.response_text = json.dumps(payload)
    with pytest.raises(GeminiClientError, match="invalid chat answer"):
        client.generate_chat_response(
            "Synthetic request", make_interpretation(["quote"]), {}, symbols, []
        )


def test_chat_rejects_missing_report_sections_with_simplified_wire_schema():
    payload = {
        "answer": {"answer": "Synthetic answer."},
        "reports": [
            {
                "symbol": "NVDA",
                "explanation": {"answer": "Incomplete report", "sections": []},
            }
        ],
    }
    sdk = FakeSdkClient(json.dumps(payload))
    client = GeminiClient(client=cast(genai.Client, sdk))
    with pytest.raises(GeminiClientError, match="invalid chat answer"):
        client.generate_chat_response(
            "Synthetic request", make_interpretation(["quote"]), {}, ["NVDA"], []
        )


def test_news_only_collection_never_calls_direction_model(monkeypatch):
    from test_stock_direction import make_news

    monkeypatch.setattr(
        assistant_services, "get_stock_quote", lambda symbol: make_quote()
    )
    monkeypatch.setattr(assistant_services, "get_stock_news", lambda *args: make_news())

    def forbidden(*args, **kwargs):
        raise AssertionError("Unrequested tool called")

    monkeypatch.setattr(assistant_services, "get_stock_outlook", forbidden)
    monkeypatch.setattr(assistant_services, "get_stock_fundamentals", forbidden)
    monkeypatch.setattr(assistant_services, "get_stock_history", forbidden)
    result = assistant_services.collect_stock_research(
        make_stock(), make_interpretation(["news_sentiment"])
    )
    assert result.news is not None
    assert result.outlook is None
    assert assistant_services.research_evidence(result)["news_sentiment"][
        "recent_articles"
    ][0]["url"]


def test_news_survives_direction_model_failure(monkeypatch):
    from test_stock_direction import make_news

    monkeypatch.setattr(
        assistant_services, "get_stock_quote", lambda symbol: make_quote()
    )
    monkeypatch.setattr(assistant_services, "get_stock_news", lambda *args: make_news())

    def unavailable(**kwargs):
        raise DirectionModelError("Insufficient history")

    monkeypatch.setattr(assistant_services, "get_stock_outlook", unavailable)
    result = assistant_services.collect_stock_research(
        make_stock(), make_interpretation(["news_sentiment", "direction_outlook"])
    )
    assert result.news is not None
    assert result.outlook is None
    assert result.outlook_error == "Insufficient history"


@pytest.mark.parametrize(
    ("query", "symbol", "provider_name", "score"),
    [
        ("NVIDIA", "NVDA", "NVIDIA Corporation", 0.9),
        ("Walt Disney", "DIS", "The Walt Disney Company", 0.5),
        ("Disney", "DIS", "The Walt Disney Company", 0.5),
    ],
)
def test_research_prompt_resolves_stock_and_runs_full_research_bundle(
    monkeypatch,
    query,
    symbol,
    provider_name,
    score,
) -> None:
    interpreter = FakeInterpreter(make_interpretation(["quote"], stock_query=query))
    stock = make_stock().model_copy(
        update={"symbol": symbol, "name": provider_name, "match_score": score}
    )
    monkeypatch.setattr(assistant_services, "search_stocks", lambda query: [stock])

    def get_quote(resolved_symbol):
        assert resolved_symbol == symbol
        return make_quote().model_copy(
            update={"symbol": symbol, "company_name": provider_name}
        )

    monkeypatch.setattr(assistant_services, "get_stock_quote", get_quote)

    def fail_optional_data(*args: object, **kwargs: object) -> None:
        raise MarketDataError("optional test data unavailable")

    monkeypatch.setattr(assistant_services, "get_stock_history", fail_optional_data)
    monkeypatch.setattr(
        assistant_services,
        "get_stock_fundamentals",
        fail_optional_data,
    )
    monkeypatch.setattr(assistant_services, "get_stock_outlook", fail_optional_data)

    message = f"Analyse {query} for me"
    result = research_stock_prompt(
        message,
        gemini_client=cast(GeminiClient, interpreter),
        conversation_context=[{"role": "user", "content": "NVIDIA"}],
    )

    assert interpreter.messages == [message]
    assert interpreter.contexts == [[{"role": "user", "content": "NVIDIA"}]]
    assert result.stock.symbol == symbol
    assert result.quote.price == 200.0
    assert result.interpretation.requested_data == [
        "quote",
        "historical_analysis",
        "fundamentals",
        "news_sentiment",
        "direction_outlook",
    ]
    assert result.analysis is None
    assert result.outlook is None
    assert result.explanation is not None
    assert "USD 200.00" in result.explanation.answer
    assert interpreter.explanation_calls[0]["message"] == message


def test_research_prompt_preserves_data_when_explanation_fails(monkeypatch) -> None:
    interpreter = FailingExplainer(make_interpretation(["quote"]))
    monkeypatch.setattr(
        assistant_services, "search_stocks", lambda query: [make_stock()]
    )
    monkeypatch.setattr(
        assistant_services, "get_stock_quote", lambda symbol: make_quote()
    )

    def fail_optional_data(*args: object, **kwargs: object) -> None:
        raise MarketDataError("optional test data unavailable")

    monkeypatch.setattr(assistant_services, "get_stock_history", fail_optional_data)
    monkeypatch.setattr(
        assistant_services,
        "get_stock_fundamentals",
        fail_optional_data,
    )
    monkeypatch.setattr(assistant_services, "get_stock_outlook", fail_optional_data)

    result = research_stock_prompt(
        "What is Nvidia's price?",
        gemini_client=cast(GeminiClient, interpreter),
    )

    assert result.quote.price == 200.0
    assert result.explanation is None
    assert result.explanation_error == "explanation unavailable"


@pytest.mark.parametrize(
    ("query", "provider_name"),
    [
        ("Walt Disney", "The Walt Disney Company"),
        ("  wAlT DISNEY  ", "Walt Disney Co (The)"),
        ("Walt Disney", "The Walt Disney Company Common Stock"),
        ("NVIDIA", "NVIDIA Corporation Common Stock"),
        ("Apple", "Apple Inc."),
        ("Acme", "Acme plc Ordinary Shares"),
    ],
)
def test_resolver_accepts_company_name_without_legal_descriptors(
    monkeypatch,
    query,
    provider_name,
) -> None:
    stock = make_stock().model_copy(update={"name": provider_name, "match_score": 0.5})
    monkeypatch.setattr(assistant_services, "search_stocks", lambda query: [stock])

    assert assistant_services._resolve_stock(query) == stock


@pytest.mark.parametrize(
    "provider_name",
    ["Walt Disney Holdings", "Walt Disney 2x Bull ETF", "Walt Disney Class A"],
)
def test_resolver_does_not_accept_an_unrelated_single_search_result(
    monkeypatch,
    provider_name,
) -> None:
    stock = make_stock().model_copy(update={"name": provider_name, "match_score": 0.5})
    monkeypatch.setattr(assistant_services, "search_stocks", lambda query: [stock])

    with pytest.raises(AssistantRequestError):
        assistant_services._resolve_stock("Walt Disney")


def test_resolver_preserves_ambiguity_between_equivalent_company_names(monkeypatch):
    matches = [
        make_stock().model_copy(update={"symbol": "ACM", "name": "Acme Inc."}),
        make_stock().model_copy(
            update={"symbol": "ACMX", "name": "The Acme Company", "match_score": 0.5}
        ),
    ]
    monkeypatch.setattr(assistant_services, "search_stocks", lambda query: matches)

    with pytest.raises(AssistantRequestError):
        assistant_services._resolve_stock("Acme")
    assert assistant_services._resolve_stock("acm").symbol == "ACM"


@pytest.mark.parametrize(
    ("query", "names", "accepted"),
    [
        ("Disney", ["The Walt Disney Company"], True),
        ("disney", ["Walt Disney Co (The)"], True),
        ("  DISNEY ", ["The Walt Disney Company Common Stock"], True),
        ("Hathaway", ["Berkshire Hathaway Inc."], True),
        ("Disney", ["The Walt Disney Company", "Disney Holdings"], False),
        ("Disney", ["Walt Disney Class A", "Walt Disney Class B"], False),
        ("Disney", ["PineDisney Inc."], False),
        ("Dis", ["The Walt Disney Company"], False),
        ("Disney", ["Leveraged ETF Trust Disney"], False),
    ],
)
def test_resolver_handles_short_company_names(monkeypatch, query, names, accepted):
    matches = [
        make_stock().model_copy(
            update={"symbol": f"TEST{index}", "name": name, "match_score": 0.5}
        )
        for index, name in enumerate(names)
    ]
    monkeypatch.setattr(assistant_services, "search_stocks", lambda query: matches)

    if accepted:
        assert assistant_services._resolve_stock(query) == matches[0]
    else:
        with pytest.raises(AssistantRequestError):
            assistant_services._resolve_stock(query)


def test_research_prompt_rejects_ambiguous_low_confidence_stock(monkeypatch) -> None:
    interpreter = FakeInterpreter(make_interpretation(["quote"], stock_query="Acme"))
    matches = [
        make_stock().model_copy(
            update={
                "symbol": "ACM",
                "name": "Acme Holdings",
                "match_score": 0.5,
            }
        ),
        make_stock().model_copy(
            update={
                "symbol": "ACMI",
                "name": "Acme Industries",
                "match_score": 0.5,
            }
        ),
    ]
    monkeypatch.setattr(assistant_services, "search_stocks", lambda query: matches)

    with pytest.raises(AssistantRequestError, match="could not safely identify"):
        research_stock_prompt(
            "What is Acme's price?",
            gemini_client=cast(GeminiClient, interpreter),
        )


def test_research_prompt_uses_horizon_and_preserves_optional_tool_errors(
    monkeypatch,
) -> None:
    interpreter = FakeInterpreter(
        make_interpretation(
            ["quote", "historical_analysis", "fundamentals", "news_sentiment"],
            time_horizon="long_term",
        )
    )
    history_calls: list[dict[str, object]] = []
    outlook_calls: list[dict[str, object]] = []
    fundamentals_calls: list[str] = []

    def fail_history(**kwargs: object) -> None:
        history_calls.append(kwargs)
        raise StockAnalysisError("analysis unavailable")

    def fail_outlook(**kwargs: object) -> None:
        outlook_calls.append(kwargs)
        raise DirectionModelError("outlook unavailable")

    def fail_fundamentals(symbol: str) -> None:
        fundamentals_calls.append(symbol)
        raise MarketDataError("fundamentals unavailable")

    monkeypatch.setattr(
        assistant_services, "search_stocks", lambda query: [make_stock()]
    )
    monkeypatch.setattr(
        assistant_services, "get_stock_quote", lambda symbol: make_quote()
    )
    monkeypatch.setattr(assistant_services, "get_stock_history", fail_history)
    monkeypatch.setattr(
        assistant_services,
        "get_stock_fundamentals",
        fail_fundamentals,
    )
    monkeypatch.setattr(assistant_services, "get_stock_outlook", fail_outlook)

    result = research_stock_prompt(
        "Give me a long-term Nvidia analysis",
        gemini_client=cast(GeminiClient, interpreter),
    )

    assert history_calls[0]["limit"] == 250
    assert fundamentals_calls == ["NVDA"]
    assert outlook_calls[0]["news_days"] == 365
    assert result.analysis_error == "analysis unavailable"
    assert result.fundamentals_error == "fundamentals unavailable"
    assert result.outlook_error == "outlook unavailable"


def test_assistant_route_returns_structured_research(monkeypatch) -> None:
    expected = AssistantResearchResponse(
        interpretation=make_interpretation(["quote"]),
        stock=make_stock(),
        quote=make_quote(),
    )
    monkeypatch.setattr(
        assistant_routes,
        "research_stock_prompt",
        lambda message, conversation_context: expected,
    )
    client = TestClient(create_app())

    response = client.post(
        "/assistant/research",
        json={"message": "What is Nvidia's price?"},
    )

    assert response.status_code == 200
    assert response.json()["interpretation"]["stock_queries"] == ["NVIDIA"]
    assert response.json()["quote"]["price"] == 200.0


def test_assistant_route_maps_unsupported_prompt_to_bad_request(monkeypatch) -> None:
    def fail(
        message: str,
        conversation_context: list[dict[str, object]],
    ) -> AssistantResearchResponse:
        raise AssistantRequestError("Ask about one stock.")

    monkeypatch.setattr(assistant_routes, "research_stock_prompt", fail)
    client = TestClient(create_app())

    response = client.post(
        "/assistant/research",
        json={"message": "Tell me a joke"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Ask about one stock."}


def test_conversation_context_keeps_recent_messages_and_verified_stock() -> None:
    messages = [
        SimpleNamespace(
            role="user",
            content=f"message {index}",
            message_metadata={},
        )
        for index in range(9)
    ]
    messages.append(
        SimpleNamespace(
            role="assistant",
            content="NVIDIA research result",
            message_metadata={
                "stock": {"symbol": "NVDA", "name": "NVIDIA Corporation"}
            },
        )
    )

    context = assistant_routes._build_conversation_context(cast(list, messages))

    assert len(context) == 8
    assert context[0]["content"] == "message 2"
    assert context[-1]["stock_symbol"] == "NVDA"
    assert context[-1]["stock_name"] == "NVIDIA Corporation"
