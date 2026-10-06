import re
from collections.abc import Callable
from app.api.services.instrument_services import instrument_context

from app.api.schema.assistant import (
    AssistantResearchResponse,
    StockPromptInterpretation,
)
from app.api.schema.stock import StockQuoteResponse, StockSearchResultResponse
from app.api.schema.stock_analysis import StockAnalysisResponse
from app.api.schema.stock_direction import StockOutlookResponse
from app.api.schema.stock_history import StockHistoryResponse
from app.api.schema.stock_fundamentals import StockFundamentalsResponse
from app.api.services.stock_analysis_services import (
    StockAnalysisError,
    build_stock_analysis,
)
from app.api.services.stock_direction_services import (
    DirectionModelError,
    get_stock_outlook,
)
from app.api.services.stock_services import get_stock_quote, search_stocks
from app.api.services.stock_history_services import get_stock_history
from app.api.services.stock_fundamentals_services import get_stock_fundamentals
from app.clients.errors import MarketDataError, StockSymbolNotFoundError
from app.clients.gemini import GeminiClient, GeminiClientError
from app.api.services.horizon_signal_services import build_horizon_signals
from app.api.services.stock_news_services import get_stock_news


class AssistantRequestError(Exception):
    pass


FULL_RESEARCH_DATA = [
    "quote",
    "historical_analysis",
    "fundamentals",
    "news_sentiment",
    "direction_outlook",
]


def research_stock_prompt(
    message: str,
    gemini_client: GeminiClient | None = None,
    conversation_context: list[dict[str, object]] | None = None,
) -> AssistantResearchResponse:
    interpreter = gemini_client or GeminiClient()
    interpretation = interpreter.interpret_stock_prompt(
        message.strip(),
        conversation_context=conversation_context,
    )
    _validate_supported_interpretation(interpretation)
    interpretation = interpretation.model_copy(
        update={"requested_data": FULL_RESEARCH_DATA}
    )
    stock = _resolve_stock(interpretation.stock_queries[0])
    research = collect_stock_research(stock, interpretation)
    try:
        research.explanation = interpreter.generate_research_explanation(
            message=message.strip(),
            interpretation=interpretation,
            evidence=research_evidence(research),
        )
    except GeminiClientError as error:
        research.explanation_error = str(error)
    return research


def collect_stock_research(
    stock: StockSearchResultResponse,
    interpretation: StockPromptInterpretation,
    check_cancelled: Callable[[], None] = lambda: None,
) -> AssistantResearchResponse:
    """Collect evidence without spending tokens on interpretation or narration."""
    quote = get_stock_quote(stock.symbol)
    check_cancelled()
    instrument = instrument_context(stock)

    if quote is None:
        raise StockSymbolNotFoundError(f"Stock symbol {stock.symbol} was not found.")

    requested_data = set(interpretation.requested_data)
    history = None
    analysis = None
    analysis_error = None
    fundamentals = None
    fundamentals_error = None
    outlook = None
    outlook_error = None
    news = None
    explanation = None
    explanation_error = None

    if "historical_analysis" in requested_data:
        try:
            history = get_stock_history(
                symbol=stock.symbol,
                provider="alpaca",
                timeframe="1Day",
                limit=_analysis_history_limit(interpretation),
            )
            analysis = build_stock_analysis(history, "historical")
        except (MarketDataError, StockAnalysisError) as error:
            analysis_error = str(error)

    check_cancelled()
    if "fundamentals" in requested_data and instrument["kind"] != "fund":
        try:
            fundamentals = get_stock_fundamentals(stock.symbol)
        except MarketDataError as error:
            fundamentals_error = str(error)

    check_cancelled()
    if "direction_outlook" in requested_data:
        try:
            outlook = get_stock_outlook(
                symbol=stock.symbol,
                benchmark_symbol="SPY",
                history_limit=250,
                news_days=_news_period_days(interpretation),
                news_limit=1000,
            )
            news = outlook.news
        except (MarketDataError, DirectionModelError) as error:
            outlook_error = str(error)

    check_cancelled()
    if "news_sentiment" in requested_data and news is None:
        try:
            news = get_stock_news(stock.symbol, _news_period_days(interpretation), 1000)
            news = news.model_copy(update={"articles": news.articles[:10]})
        except MarketDataError as error:
            outlook_error = outlook_error or str(error)

    return AssistantResearchResponse(
        instrument=instrument,
        news=news,
        horizon_signals=build_horizon_signals(analysis, fundamentals, outlook),
        interpretation=interpretation,
        stock=stock,
        quote=quote,
        history=history,
        analysis=analysis,
        analysis_error=analysis_error,
        fundamentals=fundamentals,
        fundamentals_error=fundamentals_error,
        outlook=outlook,
        outlook_error=outlook_error,
        explanation=explanation,
        explanation_error=explanation_error,
    )


def research_evidence(research: AssistantResearchResponse) -> dict[str, object]:
    evidence = _build_explanation_evidence(
        stock=research.stock,
        quote=research.quote,
        history=research.history,
        analysis=research.analysis,
        analysis_error=research.analysis_error,
        fundamentals=research.fundamentals,
        fundamentals_error=research.fundamentals_error,
        outlook=research.outlook,
        outlook_error=research.outlook_error,
    )
    evidence["instrument"] = research.instrument or instrument_context(research.stock)
    evidence["horizon_signals"] = [
        signal.model_dump(mode="json") for signal in research.horizon_signals
    ]
    if research.news and "news_sentiment" not in evidence:
        news = research.news
        evidence["news_sentiment"] = {
            "provider": news.provider,
            "period_start": news.period_start,
            "period_end": news.period_end,
            "summary": news.summary.model_dump(mode="json"),
            "warnings": news.warnings,
            "recent_articles": [
                {
                    "title": article.title,
                    "summary": article.summary[:1_000],
                    "url": article.url,
                    "source": article.source,
                    "published_at": article.published_at,
                    "sentiment_label": article.vader_label,
                }
                for article in news.articles[:10]
            ],
        }
    return evidence


def _validate_supported_interpretation(
    interpretation: StockPromptInterpretation,
) -> None:
    if interpretation.requires_clarification:
        raise AssistantRequestError(
            interpretation.clarification_question
            or "Please name one company or stock ticker to research."
        )

    if interpretation.intent == "stock_comparison":
        raise AssistantRequestError(
            "Stock comparisons are not enabled yet. Ask about one company at a time."
        )

    if interpretation.intent != "stock_research":
        raise AssistantRequestError(
            "This assistant currently handles research questions about one stock."
        )

    if len(interpretation.stock_queries) != 1:
        raise AssistantRequestError(
            "Please name exactly one company or stock ticker to research."
        )


def _resolve_stock(query: str) -> StockSearchResultResponse:
    matches = search_stocks(query)

    if not matches:
        raise StockSymbolNotFoundError(f"No stock could be resolved from {query!r}.")

    normalized_query = _normalize_stock_identity(query)
    exact_symbol_matches = [
        match
        for match in matches
        if _normalize_stock_identity(match.symbol) == normalized_query
    ]

    if len(exact_symbol_matches) == 1:
        return exact_symbol_matches[0]

    exact_name_matches = [
        match
        for match in matches
        if _normalize_stock_identity(match.name) == normalized_query
    ]

    if len(exact_name_matches) == 1:
        return exact_name_matches[0]

    company_query = _normalize_company_name(query)
    company_matches = [
        match
        for match in matches
        if company_query and _normalize_company_name(match.name) == company_query
    ]

    if len(company_matches) == 1:
        return company_matches[0]

    # A unique issuer may be referred to by the last part of its name, e.g.
    # "Disney" for "The Walt Disney Company". Require whole words, not fragments.
    if len(matches) == 1 and company_query and len("".join(company_query)) >= 4:
        company_name = _normalize_company_name(matches[0].name)
        product_terms = {"etf", "etn", "fund", "trust", "leveraged", "bull", "bear"}
        if company_name[
            -len(company_query) :
        ] == company_query and not product_terms.intersection(company_name):
            return matches[0]

    # Equivalent company names can still represent different listings or shares.
    # Do not let a provider score choose between those securities.
    if len(company_matches) > 1:
        matches = company_matches

    high_confidence_matches = [
        match
        for match in matches
        if match.match_score is not None and match.match_score >= 0.9
    ]

    if len(company_matches) < 2 and len(high_confidence_matches) == 1:
        return high_confidence_matches[0]

    candidate_symbols = ", ".join(match.symbol for match in matches[:3])
    raise AssistantRequestError(
        f"I could not safely identify one stock for {query!r}. "
        "Use the full company name or include its exact ticker. "
        f"Possible matches: {candidate_symbols}."
    )


def _normalize_stock_identity(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _normalize_company_name(value: str) -> tuple[str, ...]:
    words = re.findall(r"[^\W_]+", value.casefold())
    if words and words[0] == "the":
        words.pop(0)

    # Strip only trailing legal/listing descriptors, preserving words that
    # distinguish issuers, funds, and share classes.
    suffixes = (
        ("common", "stock"),
        ("ordinary", "shares"),
        ("incorporated",),
        ("corporation",),
        ("company",),
        ("limited",),
        ("corp",),
        ("inc",),
        ("ltd",),
        ("plc",),
        ("co",),
        ("the",),
    )
    while words:
        for suffix in suffixes:
            if tuple(words[-len(suffix) :]) == suffix:
                del words[-len(suffix) :]
                break
        else:
            break
    return tuple(words)


def _analysis_history_limit(interpretation: StockPromptInterpretation) -> int:
    return 250 if interpretation.time_horizon == "long_term" else 100


def _news_period_days(interpretation: StockPromptInterpretation) -> int:
    if interpretation.time_horizon == "current":
        return 30

    if interpretation.time_horizon == "long_term":
        return 365

    return 180


def _build_explanation_evidence(
    *,
    stock: StockSearchResultResponse,
    quote: StockQuoteResponse,
    history: StockHistoryResponse | None,
    analysis: StockAnalysisResponse | None,
    analysis_error: str | None,
    fundamentals: StockFundamentalsResponse | None,
    fundamentals_error: str | None,
    outlook: StockOutlookResponse | None,
    outlook_error: str | None,
) -> dict[str, object]:
    evidence: dict[str, object] = {
        "stock": stock.model_dump(mode="json"),
        "quote": quote.model_dump(mode="json"),
        "history": (
            {
                "provider": history.provider,
                "timeframe": history.timeframe,
                "adjusted": history.adjusted,
                "bar_count": len(history.bars),
                "start": history.bars[0].timestamp if history.bars else None,
                "end": history.bars[-1].timestamp if history.bars else None,
            }
            if history is not None
            else None
        ),
        "analysis_error": analysis_error,
        "fundamentals_error": fundamentals_error,
        "outlook_error": outlook_error,
    }

    if analysis is not None:
        evidence["historical_analysis"] = {
            "as_of": analysis.as_of,
            "data_through": analysis.data_through,
            "adjusted": analysis.adjusted,
            "bar_count": analysis.bar_count,
            "sample_sufficient": analysis.sample_sufficient,
            "start_timestamp": analysis.start_timestamp,
            "end_timestamp": analysis.end_timestamp,
            "first_close": analysis.first_close,
            "latest_close": analysis.latest_close,
            "period_return_pct": analysis.period_return_pct,
            "compound_average_daily_return_pct": (
                analysis.compound_average_daily_return_pct
            ),
            "annualized_volatility_pct": analysis.annualized_volatility_pct,
            "moving_average_20": analysis.moving_average_20,
            "moving_average_50": analysis.moving_average_50,
            "max_drawdown_pct": analysis.max_drawdown_pct,
            "trend": analysis.trend,
            "risk_level": analysis.risk_level,
            "entry_context": analysis.entry_context.model_dump(mode="json"),
            "reasons": analysis.reasons,
            "warnings": analysis.warnings,
        }

    if fundamentals is not None:
        evidence["fundamentals"] = {
            "annual_financials": [
                row.model_dump(mode="json") for row in fundamentals.annual_financials
            ],
            "financial_quality": fundamentals.financial_quality.model_dump(mode="json")
            if fundamentals.financial_quality
            else None,
            "provider": fundamentals.provider,
            "fetched_at": fundamentals.fetched_at,
            "latest_quarter": fundamentals.latest_quarter,
            "company": fundamentals.company.model_dump(mode="json"),
            "valuation": fundamentals.valuation.model_dump(mode="json"),
            "profitability_growth": (
                fundamentals.profitability_growth.model_dump(mode="json")
            ),
            "financial_health": fundamentals.financial_health.model_dump(mode="json"),
            "market_context": fundamentals.market_context.model_dump(mode="json"),
            "highlights": fundamentals.highlights,
            "warnings": fundamentals.warnings,
        }

    if outlook is not None:
        evidence["news_sentiment"] = {
            "provider": outlook.news.provider,
            "period_start": outlook.news.period_start,
            "period_end": outlook.news.period_end,
            "summary": outlook.news.summary.model_dump(mode="json"),
            "warnings": outlook.news.warnings,
            "recent_articles": [
                {
                    "title": article.title,
                    "summary": article.summary[:1_000],
                    "url": article.url,
                    "source": article.source,
                    "published_at": article.published_at,
                    "relevance_score": article.relevance_score,
                    "sentiment_score": article.vader_compound,
                    "sentiment_label": article.vader_label,
                }
                for article in outlook.news.articles[:10]
            ],
        }
        evidence["direction_model"] = {
            "additional_horizons": [
                {
                    "horizon": model.horizon,
                    "horizon_sessions": model.horizon_sessions,
                    "up_probability_pct": model.up_probability_pct,
                    "lean": model.lean,
                    "validation_status": model.validation_status,
                    "accuracy_edge_pct_points": model.accuracy_edge_pct_points,
                    "validation_brier_score": model.validation_brier_score,
                    "baseline_brier_score": model.baseline_brier_score,
                }
                for model in outlook.additional_horizons
            ],
            "horizon_errors": outlook.horizon_errors,
            "model_version": outlook.direction.model_version,
            "model_type": outlook.direction.model_type,
            "target": outlook.direction.target,
            "horizon": outlook.direction.horizon,
            "generated_at": outlook.direction.generated_at,
            "data_through": outlook.direction.data_through,
            "lean": outlook.direction.lean,
            "confidence": outlook.direction.confidence,
            "up_probability_pct": outlook.direction.up_probability_pct,
            "down_probability_pct": outlook.direction.down_probability_pct,
            "validation_status": outlook.direction.validation_status,
            "validation_accuracy_pct": outlook.direction.validation_accuracy_pct,
            "validation_balanced_accuracy_pct": (
                outlook.direction.validation_balanced_accuracy_pct
            ),
            "validation_roc_auc": outlook.direction.validation_roc_auc,
            "strongest_baseline_accuracy_pct": (
                outlook.direction.strongest_baseline_accuracy_pct
            ),
            "accuracy_edge_pct_points": outlook.direction.accuracy_edge_pct_points,
            "validation_brier_score": outlook.direction.validation_brier_score,
            "baseline_brier_score": outlook.direction.baseline_brier_score,
            "observed_up_rate_pct": outlook.direction.observed_up_rate_pct,
            "decisive_coverage_pct": outlook.direction.decisive_coverage_pct,
            "decisive_accuracy_pct": outlook.direction.decisive_accuracy_pct,
            "latest_feature_values": outlook.direction.latest_feature_values,
            "feature_stability": [
                feature.model_dump(mode="json")
                for feature in outlook.direction.feature_stability[:5]
            ],
            "warnings": outlook.direction.warnings,
        }

    return evidence
