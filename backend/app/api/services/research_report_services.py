from datetime import UTC, datetime
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schema.assistant import (
    AssistantExplanation,
    AssistantResearchResponse,
    StockPromptInterpretation,
)
from app.api.schema.chat import ChatMessageResponse
from app.api.schema.peer_comparison import PeerComparisonResponse
from app.api.schema.research_report import (
    ResearchChatRequest,
    ResearchChatResponse,
    ResearchReportResponse,
)
from app.api.schema.stock import StockSearchResultResponse
from app.api.services.assistant_services import (
    FULL_RESEARCH_DATA,
    AssistantRequestError,
    _normalize_company_name,
    _normalize_stock_identity,
    _resolve_stock,
    collect_stock_research,
    research_evidence,
)
from app.api.services.chat_services import (
    ChatSessionNotFoundError,
    get_chat_session,
    list_chat_messages,
)
from app.api.services.daily_report_cache import (
    cache_scope,
    load_daily_report,
    lock_report_generation,
    store_daily_report,
)
from app.api.services.peer_comparison_services import compare_fundamentals
from app.clients.gemini import GeminiClient, GeminiClientError
from app.core.report_policy import (
    REPORT_FORMAT_VERSION,
    as_utc,
    report_expiry,
    snapshot_is_current,
    utc_now,
)
from app.models.chat import ChatMessage, ChatSession
from app.models.research_report import ResearchReport


def list_research_reports(
    db: Session, session_id: UUID, user_id: UUID | None
) -> list[ResearchReport]:
    get_chat_session(db, session_id, user_id)
    return list(
        db.scalars(
            select(ResearchReport)
            .where(
                ResearchReport.session_id == session_id,
            )
            .order_by(ResearchReport.created_at, ResearchReport.symbol)
        ).all()
    )


def conversation_context(messages: list[ChatMessage]) -> list[dict[str, object]]:
    context: list[dict[str, object]] = []
    for message in messages[-8:]:
        item: dict[str, object] = {
            "role": message.role,
            "content": message.content[:1_000],
        }
        stock = message.message_metadata.get("stock")
        if isinstance(stock, dict):
            item["stock_symbol"] = stock.get("symbol")
            item["stock_name"] = stock.get("name")
        symbols = message.message_metadata.get("stock_symbols")
        if isinstance(symbols, list):
            item["stock_symbols"] = symbols
        context.append(item)
    return context


def _find_saved_stock(
    query: str, reports: list[ResearchReport]
) -> StockSearchResultResponse | None:
    # Exact identities only: do not let a fuzzy saved alias select a different issuer.
    normalized = _normalize_stock_identity(query)
    company = _normalize_company_name(query)
    matches = []
    for report in reports:
        stock = AssistantResearchResponse.model_validate(report.research).stock
        if normalized in {
            _normalize_stock_identity(stock.symbol),
            _normalize_stock_identity(stock.name),
        } or (company and company == _normalize_company_name(stock.name)):
            matches.append(stock)
    return matches[0] if len(matches) == 1 else None


def focused_evidence(
    research: AssistantResearchResponse, requested: list[str], *, full: bool
) -> dict[str, object]:
    evidence = research_evidence(research)
    if full:
        return evidence
    keys = {"stock", "quote", "instrument"}
    if "historical_analysis" in requested:
        keys.update({"history", "historical_analysis", "analysis_error"})
    if "fundamentals" in requested:
        keys.update({"fundamentals", "fundamentals_error"})
    if "news_sentiment" in requested:
        keys.update({"news_sentiment", "outlook_error"})
    if "direction_outlook" in requested:
        keys.update({"direction_model", "outlook_error"})
    result = {key: value for key, value in evidence.items() if key in keys}
    horizons = set()
    if "historical_analysis" in requested:
        horizons.add("weeks_to_months")
    if "fundamentals" in requested:
        horizons.add("years")
    if "direction_outlook" in requested:
        horizons.update({"next_close", "3_sessions", "5_sessions"})
    if horizons:
        result["horizon_signals"] = [
            signal.model_dump(mode="json")
            for signal in research.horizon_signals
            if signal.horizon in horizons
        ]
    return result


def answer_research_chat(
    db: Session,
    request: ResearchChatRequest,
    user_id: UUID | None,
    gemini_client: GeminiClient | None = None,
    check_cancelled: Callable[[], None] = lambda: None,
    finish: Callable[[], None] = lambda: None,
) -> ResearchChatResponse:
    check_cancelled()
    # A session-level database lock serializes concurrent submissions. A repeated
    # request_id replays the saved turn without provider calls or duplicate messages.
    session = db.scalar(
        select(ChatSession)
        .where(
            ChatSession.id == request.session_id,
            ChatSession.user_id == user_id,
        )
        .with_for_update()
    )
    if session is None:
        raise ChatSessionNotFoundError
    messages = list_chat_messages(db, session.id, user_id)
    reports = list_research_reports(db, session.id, user_id)
    for saved in messages:
        if saved.role == "assistant" and saved.message_metadata.get(
            "request_id"
        ) == str(request.request_id):
            if saved.message_metadata.get("query") != request.message:
                raise AssistantRequestError(
                    "This request ID has already been used for another question."
                )
            return _response(session.id, saved, reports)

    client = gemini_client or GeminiClient()
    context = conversation_context(messages)
    if request.context_report_id:
        selected = next(
            (report for report in reports if report.id == request.context_report_id),
            None,
        )
        if selected is None:
            raise AssistantRequestError(
                "The selected report does not belong to this chat."
            )
        stock = AssistantResearchResponse.model_validate(selected.research).stock
        context.append(
            {
                "role": "assistant",
                "content": "The user is currently viewing this saved report.",
                "stock_symbol": stock.symbol,
                "stock_name": stock.name,
            }
        )
    refresh = next(
        (report for report in reports if report.id == request.refresh_report_id), None
    )
    if request.refresh_report_id and refresh is None:
        raise AssistantRequestError("That report does not belong to this chat.")
    if refresh:
        interpretation = AssistantResearchResponse.model_validate(
            refresh.research
        ).interpretation.model_copy(
            update={
                "intent": "stock_research",
                "stock_queries": [refresh.symbol],
                "report_queries": [],
                "requested_data": FULL_RESEARCH_DATA,
            },
        )
    else:
        interpretation = client.interpret_stock_prompt(
            request.message, conversation_context=context
        )
    check_cancelled()

    if interpretation.requires_clarification or interpretation.intent in {
        "unclear",
        "unrelated",
    }:
        answer = AssistantExplanation(
            answer=interpretation.clarification_question
            or "Which stock or finance topic would you like to research?"
        )
        finish()
        return _save_turn(db, session, request, interpretation, answer, [], reports)
    if (
        interpretation.intent == "stock_research"
        and len(interpretation.stock_queries) != 1
    ):
        raise AssistantRequestError("Please identify one stock for the report.")
    if (
        interpretation.intent == "stock_comparison"
        and not 2 <= len(interpretation.stock_queries) <= 5
    ):
        raise AssistantRequestError(
            "Please name between two and five stocks to compare."
        )
    if interpretation.intent == "stock_comparison":
        interpretation = interpretation.model_copy(
            update={
                "requested_data": list(
                    dict.fromkeys(
                        ["quote", "fundamentals", *interpretation.requested_data]
                    )
                )
            }
        )

    research_items: list[AssistantResearchResponse] = []
    reports_to_write: list[ResearchReport] = []
    full_reports: list[ResearchReport] = []
    explicit_report_queries = {
        query.strip().casefold() for query in interpretation.report_queries
    }
    scope = cache_scope(user_id, session.id)
    evidence: dict[str, object] = {}
    queries = (
        []
        if interpretation.intent == "general_finance"
        else interpretation.stock_queries
    )
    resolved_stocks = {}
    report_symbols_requested = set()
    for query in queries:
        check_cancelled()
        stock = _find_saved_stock(query, reports) or _resolve_stock(query)
        resolved_stocks.setdefault(stock.symbol, stock)
        if query.strip().casefold() in explicit_report_queries:
            report_symbols_requested.add(stock.symbol)
    for stock in resolved_stocks.values():
        check_cancelled()
        report = next((item for item in reports if item.symbol == stock.symbol), None)
        full = (
            interpretation.intent == "stock_research"
            or stock.symbol in report_symbols_requested
        )
        if full:
            lock_report_generation(db, scope)
        cached = load_daily_report(db, scope, stock.symbol) if not refresh else None
        current_report = report and snapshot_is_current(
            report.updated_at, report.expires_at, report.format_version, utc_now()
        )
        if cached and (
            not current_report
            or as_utc(cached.generated_at) >= as_utc(report.updated_at)
        ):
            research = AssistantResearchResponse.model_validate(cached.research)
            snapshot_at = cached.generated_at
            if full:
                if report is None:
                    report = ResearchReport(session_id=session.id, symbol=stock.symbol)
                    db.add(report)
                    reports.append(report)
                report.research = research.model_dump(mode="json")
                report.updated_at = cached.generated_at
                report.expires_at = cached.expires_at
                report.format_version = cached.format_version
        elif current_report and not refresh:
            research = AssistantResearchResponse.model_validate(report.research)
            snapshot_at = report.updated_at
        else:
            requested = (
                FULL_RESEARCH_DATA
                if full
                else list(dict.fromkeys(["quote", *interpretation.requested_data]))
            )
            collection_request = interpretation.model_copy(
                update={
                    "stock_queries": [stock.symbol],
                    "report_queries": [],
                    "requested_data": requested,
                    # Consistent daily windows for newly collected comparison/report data.
                    "time_horizon": "long_term",
                }
            )
            collected_at = utc_now()
            snapshot_at = collected_at
            research = collect_stock_research(
                stock, collection_request, check_cancelled=check_cancelled
            )
            check_cancelled()
            if full:
                if report is None:
                    report = ResearchReport(session_id=session.id, symbol=stock.symbol)
                    db.add(report)
                    reports.append(report)
                report.research = research.model_dump(mode="json")
                report.updated_at = collected_at
                report.expires_at = report_expiry(collected_at)
                report.format_version = REPORT_FORMAT_VERSION
        if full:
            full_reports.append(report)
        needs_narrative = bool(full and report and research.explanation is None)
        if needs_narrative:
            reports_to_write.append(report)
        research_items.append(research)
        evidence[stock.symbol] = {
            "snapshot_generated_at": as_utc(snapshot_at).isoformat(),
            "saved_snapshot": bool(cached or current_report or full),
            "data": focused_evidence(
                research,
                interpretation.requested_data,
                full=needs_narrative,
            ),
        }
    if interpretation.intent == "stock_comparison" and len(research_items) < 2:
        raise AssistantRequestError(
            "Those names identify the same stock. Please choose two different stocks."
        )
    symbols_to_write = [report.symbol for report in reports_to_write]
    comparison = None
    if interpretation.intent == "stock_comparison":
        comparison = compare_fundamentals(
            [item.fundamentals for item in research_items if item.fundamentals],
            interpretation.ranking_preset,
        )
        evidence["peer_comparison"] = comparison.model_dump(mode="json")
    try:
        check_cancelled()
        generated = client.generate_chat_response(
            request.message,
            interpretation,
            evidence,
            symbols_to_write,
            context,
        )
        check_cancelled()
        answer = generated.answer
        if [item.symbol for item in generated.reports] != symbols_to_write:
            raise GeminiClientError(
                "The requested report explanations were not returned."
            )
        for report_to_write, narrative in zip(reports_to_write, generated.reports):
            research = AssistantResearchResponse.model_validate(
                report_to_write.research
            )
            research.explanation = narrative.explanation
            research.explanation_error = None
            report_to_write.research = research.model_dump(mode="json")
    except GeminiClientError as error:
        # Keep expensive collected evidence even if the narration provider fails.
        for report_to_write in reports_to_write:
            research = AssistantResearchResponse.model_validate(
                report_to_write.research
            )
            research.explanation_error = str(error)
            report_to_write.research = research.model_dump(mode="json")
        answer = AssistantExplanation(
            answer=f"The AI explanation is unavailable: {error}. Any collected report data has been saved; you can ask again without recollecting it."
        )
    for full_report in full_reports:
        store_daily_report(db, scope, full_report)
    db.flush()
    finish()
    return _save_turn(
        db,
        session,
        request,
        interpretation,
        answer,
        research_items,
        reports,
        comparison,
        report_symbols=[report.symbol for report in full_reports],
    )


def _save_turn(
    db: Session,
    session: ChatSession,
    request: ResearchChatRequest,
    interpretation: StockPromptInterpretation,
    answer: AssistantExplanation,
    research_items: list[AssistantResearchResponse],
    reports: list[ResearchReport],
    comparison: PeerComparisonResponse | None = None,
    report_symbols: list[str] | None = None,
) -> ResearchChatResponse:
    now = datetime.now(UTC)
    symbols = [item.stock.symbol for item in research_items]
    linked_symbols = (
        report_symbols
        if report_symbols is not None
        else (symbols if interpretation.intent == "stock_research" else [])
    )
    linked = [str(report.id) for report in reports if report.symbol in linked_symbols]
    metadata = {
        "kind": "research_chat",
        "request_id": str(request.request_id),
        "query": request.message,
        "explanation": answer.model_dump(mode="json"),
        "stock_symbols": symbols,
        "report_ids": linked,
        "comparison": comparison.model_dump(mode="json") if comparison else None,
        "price_as_of": {
            item.stock.symbol: item.quote.latest_trading_day for item in research_items
        },
    }
    if len(research_items) == 1 and answer.visuals:
        item = research_items[0]
        # Save only chart inputs chosen for this turn, never a second report narrative.
        fields = {"quote"}
        if "price" in answer.visuals:
            fields.update({"history", "analysis"})
        if "fundamentals" in answer.visuals:
            fields.add("fundamentals")
        if {"news", "model"}.intersection(answer.visuals):
            fields.update({"outlook", "news"})
        metadata["visual_data"] = item.model_dump(mode="json", include=fields)
    if len(research_items) == 1:
        metadata["stock"] = research_items[0].stock.model_dump(mode="json")
    user_message = ChatMessage(
        session_id=session.id,
        role="user",
        content=request.message,
        message_metadata={"request_id": str(request.request_id)},
        created_at=now,
    )
    assistant_message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer.answer,
        message_metadata=metadata,
        created_at=datetime.now(UTC),
    )
    db.add_all([user_message, assistant_message])
    session.updated_at = datetime.now(UTC)
    db.commit()
    return _response(session.id, assistant_message, reports)


def _response(
    session_id: UUID, message: ChatMessage, reports: list[ResearchReport]
) -> ResearchChatResponse:
    return ResearchChatResponse(
        session_id=session_id,
        message=ChatMessageResponse.model_validate(message),
        reports=[ResearchReportResponse.model_validate(report) for report in reports],
    )
