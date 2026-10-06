from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
from statistics import fmean
from zoneinfo import ZoneInfo

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.api.schema.market_watch import (
    MarketWatchCandidateResponse,
    MarketWatchResponse,
    MarketSession,
    MarketWatchSentiment,
    MarketWatchSignal,
)
from app.clients.alpaca import (
    AlpacaClient,
    AlpacaNewsArticle,
    AlpacaScreenerMover,
    AlpacaStockMovers,
    AlpacaStockSnapshot,
)
from app.api.services.ttl_cache import TTLCache
from app.clients.alpha_vantage import (
    AlphaVantageClient,
    AlphaVantageMarketMover,
    AlphaVantageMarketNewsArticle,
    AlphaVantageMarketMovers,
    AlphaVantageTickerSentiment,
)
from app.clients.errors import MarketDataError
from app.core.config import settings


MARKET_WATCH_CACHE_TTL_SECONDS = 900
MARKET_WATCH_NEWS_HOURS = 36
MARKET_WATCH_NEWS_LIMIT = 200
MIN_MARKET_NEWS_RELEVANCE = 0.25
MAX_SNAPSHOT_SYMBOLS = 100
MIN_MOVER_PRICE = 1.0
MIN_MOVER_VOLUME = 100_000
MAX_SNAPSHOT_AGE_DAYS = 5
_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_market_watch_cache: TTLCache[int, MarketWatchResponse] = TTLCache(
    ttl_seconds=MARKET_WATCH_CACHE_TTL_SECONDS
)
_sentiment_analyzer = SentimentIntensityAnalyzer()


@dataclass
class _TickerAttention:
    symbol: str
    relevance_scores: list[float] = field(default_factory=list)
    sentiment_scores: list[float] = field(default_factory=list)
    news_mentions: int = 0
    latest_headline: str | None = None
    latest_source: str | None = None
    latest_url: str | None = None
    latest_published_at: str | None = None
    mover: AlphaVantageMarketMover | None = None
    gainer_rank: int | None = None
    activity_rank: int | None = None
    loser_rank: int | None = None
    snapshot: AlpacaStockSnapshot | None = None


def get_market_watch(
    limit: int,
    now: datetime | None = None,
    client: AlphaVantageClient | None = None,
    snapshot_client: AlpacaClient | None = None,
) -> MarketWatchResponse:
    cached_response = _market_watch_cache.get(limit)

    if cached_response is not None and client is None and now is None:
        return cached_response

    period_end = _as_utc(now or datetime.now(timezone.utc)).replace(microsecond=0)
    period_start = period_end - timedelta(hours=MARKET_WATCH_NEWS_HOURS)
    provider = client or AlphaVantageClient()
    warnings: list[str] = []
    news: list[AlphaVantageMarketNewsArticle] = []
    movers: AlphaVantageMarketMovers | None = None
    snapshots: dict[str, AlpacaStockSnapshot] = {}

    try:
        news = provider.get_market_news(
            time_from=_alpha_vantage_time(period_start),
            time_to=_alpha_vantage_time(period_end),
            limit=MARKET_WATCH_NEWS_LIMIT,
        )
    except MarketDataError as error:
        warnings.append(f"Market-news scan is unavailable: {error}")

    try:
        movers = provider.get_top_movers()
    except MarketDataError as error:
        warnings.append(f"Top-mover snapshot is unavailable: {error}")

    market_session = _market_session(period_end)
    snapshot_feed = (
        "overnight" if market_session == "overnight" else settings.alpaca_data_feed
    )
    alpaca_provider = snapshot_client or (
        AlpacaClient() if client is None else None
    )
    alpha_data_available = bool(news or movers is not None)
    alpaca_data_available = False

    if alpaca_provider is not None:
        alpaca_movers: AlpacaStockMovers | None = None
        alpaca_news: list[AlpacaNewsArticle] = []

        try:
            alpaca_movers = alpaca_provider.get_stock_movers(top=20)
            alpaca_data_available = True
        except MarketDataError as error:
            warnings.append(f"Alpaca mover discovery is unavailable: {error}")

        try:
            alpaca_news = alpaca_provider.get_market_news(
                start=_iso_timestamp(period_start),
                end=_iso_timestamp(period_end),
                limit=50,
            )
            alpaca_data_available = True
        except MarketDataError as error:
            warnings.append(f"Alpaca market news is unavailable: {error}")

        news = _merge_news(news, _convert_alpaca_news(alpaca_news))
        movers = _merge_movers(movers, alpaca_movers)

    if not news and movers is None:
        raise MarketDataError("Market watch data is temporarily unavailable.")

    symbols = _candidate_symbols(news, movers)

    if symbols and alpaca_provider is not None:
        try:
            snapshots = alpaca_provider.get_stock_snapshots(
                symbols=symbols,
                feed=snapshot_feed,
            )
        except MarketDataError as error:
            if snapshot_feed == "overnight":
                try:
                    snapshot_feed = settings.alpaca_data_feed
                    snapshots = alpaca_provider.get_stock_snapshots(
                        symbols=symbols,
                        feed=snapshot_feed,
                    )
                    warnings.append(
                        "The overnight feed was unavailable; latest standard-feed "
                        "snapshots are shown instead."
                    )
                except MarketDataError as fallback_error:
                    warnings.append(
                        f"Live session snapshots are unavailable: {fallback_error}"
                    )
            else:
                warnings.append(f"Live session snapshots are unavailable: {error}")

    snapshots = {
        symbol: snapshot
        for symbol, snapshot in snapshots.items()
        if _snapshot_is_fresh(snapshot, period_end)
    }

    ranked_candidates = build_market_watch_candidates(
        news,
        movers,
        max(MAX_SNAPSHOT_SYMBOLS, limit),
        snapshots=snapshots,
        market_session=market_session,
    )
    candidates = _rerank(ranked_candidates, limit)
    mover_candidates = _rerank(
        sorted(
            (
                candidate
                for candidate in ranked_candidates
                if candidate.change_percent is not None
                and (candidate.price or 0.0) >= MIN_MOVER_PRICE
                and (
                    candidate.volume is None
                    or candidate.volume >= MIN_MOVER_VOLUME
                )
            ),
            key=lambda candidate: abs(candidate.change_percent or 0.0),
            reverse=True,
        ),
        limit,
    )
    news_candidates = _rerank(
        sorted(
            (
                candidate
                for candidate in ranked_candidates
                if candidate.news_mentions > 0
            ),
            key=lambda candidate: (
                candidate.catalyst_score,
                candidate.news_mentions,
                abs(candidate.change_percent or 0.0),
            ),
            reverse=True,
        ),
        limit,
    )
    warnings.extend(
        [
            (
                "Before the regular market opens, the Alpaca mover screen may still "
                "reflect the prior session; snapshot changes are used where available."
            ),
            (
                "The scanner covers symbols surfaced by provider movers, activity, "
                "and recent news; it is not yet a scan of every US-listed stock."
            ),
            (
                "The movers view excludes sub-$1 prices and symbols with reported "
                "session volume below 100,000 to reduce illiquid noise."
            ),
            (
                "Session labels follow the normal US weekday schedule and do not "
                "yet account for exchange holidays or early closes."
            ),
        ]
    )
    response = MarketWatchResponse(
        generated_at=_iso_timestamp(period_end),
        provider=_provider_label(
            alpha_available=alpha_data_available,
            alpaca_available=alpaca_data_available or bool(snapshots),
        ),
        period_start=_iso_timestamp(period_start),
        period_end=_iso_timestamp(period_end),
        market_snapshot_at=movers.last_updated if movers is not None else None,
        market_data_freshness=(
            "combined_snapshot" if snapshots else "provider_snapshot"
        ),
        market_session=market_session,
        snapshot_feed=snapshot_feed if snapshots else None,
        candidates=candidates,
        movers=mover_candidates,
        news_catalysts=news_candidates,
        warnings=warnings,
    )

    if client is None and now is None:
        _market_watch_cache.set(limit, response)

    return response


def build_market_watch_candidates(
    news: list[AlphaVantageMarketNewsArticle],
    movers: AlphaVantageMarketMovers | None,
    limit: int,
    snapshots: dict[str, AlpacaStockSnapshot] | None = None,
    market_session: MarketSession = "closed",
) -> list[MarketWatchCandidateResponse]:
    attention: dict[str, _TickerAttention] = {}

    for article in news:
        for ticker_sentiment in article.ticker_sentiments:
            symbol = ticker_sentiment.ticker.strip().upper()
            relevance = ticker_sentiment.relevance_score

            if not _is_supported_symbol(symbol):
                continue

            if relevance is None or relevance < MIN_MARKET_NEWS_RELEVANCE:
                continue

            ticker = attention.setdefault(symbol, _TickerAttention(symbol=symbol))
            ticker.news_mentions += 1
            ticker.relevance_scores.append(relevance)

            if ticker_sentiment.sentiment_score is not None:
                ticker.sentiment_scores.append(ticker_sentiment.sentiment_score)

            if (
                ticker.latest_published_at is None
                or article.published_at > ticker.latest_published_at
            ):
                ticker.latest_headline = article.title
                ticker.latest_source = article.source
                ticker.latest_url = article.url
                ticker.latest_published_at = article.published_at

    if movers is not None:
        for rank, mover in enumerate(movers.top_gainers, start=1):
            if not _is_supported_symbol(mover.ticker):
                continue

            ticker = attention.setdefault(
                mover.ticker,
                _TickerAttention(symbol=mover.ticker),
            )
            ticker.mover = mover
            ticker.gainer_rank = rank

        for rank, mover in enumerate(movers.top_losers, start=1):
            if not _is_supported_symbol(mover.ticker):
                continue

            ticker = attention.setdefault(
                mover.ticker,
                _TickerAttention(symbol=mover.ticker),
            )
            ticker.mover = mover
            ticker.loser_rank = rank

        for rank, mover in enumerate(movers.most_actively_traded, start=1):
            if not _is_supported_symbol(mover.ticker):
                continue

            ticker = attention.setdefault(
                mover.ticker,
                _TickerAttention(symbol=mover.ticker),
            )
            ticker.activity_rank = rank

            if ticker.mover is None:
                ticker.mover = mover

    for symbol, snapshot in (snapshots or {}).items():
        ticker = attention.get(symbol)

        if ticker is not None:
            ticker.snapshot = snapshot

    eligible_attention = [
        item
        for item in attention.values()
        if not snapshots or item.mover is not None or item.snapshot is not None
    ]
    ranked = sorted(
        eligible_attention,
        key=lambda item: (
            _attention_score(item),
            item.news_mentions,
            abs(_change_percent(item) or 0.0),
        ),
        reverse=True,
    )[:limit]

    return [
        _to_response(item, rank, market_session)
        for rank, item in enumerate(ranked, start=1)
    ]


def _to_response(
    item: _TickerAttention,
    rank: int,
    market_session: MarketSession,
) -> MarketWatchCandidateResponse:
    average_relevance = (
        fmean(item.relevance_scores) if item.relevance_scores else None
    )
    average_sentiment = (
        fmean(item.sentiment_scores) if item.sentiment_scores else None
    )
    mover = item.mover
    snapshot = item.snapshot
    price = (
        snapshot.latest_price
        if snapshot is not None and snapshot.latest_price is not None
        else mover.price if mover is not None else None
    )
    previous_close = snapshot.previous_close if snapshot is not None else None
    change_percent = _change_percent(item)
    change_amount = (
        price - previous_close
        if price is not None and previous_close is not None
        else mover.change_amount if mover is not None else None
    )

    return MarketWatchCandidateResponse(
        rank=rank,
        symbol=item.symbol,
        attention_score=round(_attention_score(item), 2),
        catalyst_score=round(_catalyst_score(item), 2),
        signal=_signal(item),
        market_session=market_session,
        price=_round_optional(price),
        previous_close=_round_optional(previous_close),
        change_amount=_round_optional(change_amount),
        change_percent=_round_optional(change_percent),
        volume=(
            snapshot.daily_volume
            if snapshot is not None and snapshot.daily_volume is not None
            else mover.volume if mover is not None else None
        ),
        snapshot_at=snapshot.latest_timestamp if snapshot is not None else None,
        news_mentions=item.news_mentions,
        average_relevance=(
            round(average_relevance, 4) if average_relevance is not None else None
        ),
        average_sentiment=(
            round(average_sentiment, 4) if average_sentiment is not None else None
        ),
        sentiment=_sentiment(average_sentiment),
        latest_headline=item.latest_headline,
        latest_source=item.latest_source,
        latest_url=item.latest_url,
        latest_published_at=item.latest_published_at,
        reasons=_reasons(item, average_sentiment),
    )


def _attention_score(item: _TickerAttention) -> float:
    average_relevance = (
        fmean(item.relevance_scores) if item.relevance_scores else 0.0
    )
    average_sentiment = (
        fmean(item.sentiment_scores) if item.sentiment_scores else 0.0
    )
    news_score = min(28.0, item.news_mentions * 8.0)
    relevance_score = min(18.0, average_relevance * 18.0)
    sentiment_attention_score = min(10.0, abs(average_sentiment) * 20.0)
    change_percent = _change_percent(item) or 0.0
    momentum_score = min(28.0, abs(change_percent) / 15.0 * 28.0)
    activity_score = (
        max(2.0, 12.0 - ((item.activity_rank - 1) * 0.5))
        if item.activity_rank is not None
        else 0.0
    )
    confluence_bonus = (
        4.0 if item.news_mentions > 0 and item.gainer_rank is not None else 0.0
    )

    return min(
        100.0,
        news_score
        + relevance_score
        + sentiment_attention_score
        + momentum_score
        + activity_score
        + confluence_bonus,
    )


def _signal(item: _TickerAttention) -> MarketWatchSignal:
    if item.news_mentions > 0 and abs(_change_percent(item) or 0.0) >= 2:
        return "mixed_attention"

    if item.news_mentions > 0:
        return "news_catalyst"

    if _change_percent(item) is not None:
        return "session_mover"

    return "high_activity"


def _sentiment(value: float | None) -> MarketWatchSentiment:
    if value is None:
        return "unavailable"

    if value >= 0.15:
        return "bullish"

    if value <= -0.15:
        return "bearish"

    return "mixed"


def _reasons(item: _TickerAttention, average_sentiment: float | None) -> list[str]:
    reasons: list[str] = []

    if item.news_mentions:
        noun = "article" if item.news_mentions == 1 else "articles"
        reasons.append(
            f"Mentioned in {item.news_mentions} recent market-news {noun}."
        )

    if item.gainer_rank is not None and item.mover is not None:
        change = item.mover.change_percentage
        change_text = f" ({change:+.2f}%)" if change is not None else ""
        reasons.append(
            f"Ranked #{item.gainer_rank} in the provider's top gainers{change_text}."
        )

    if item.loser_rank is not None and item.mover is not None:
        change = item.mover.change_percentage
        change_text = f" ({change:+.2f}%)" if change is not None else ""
        reasons.append(
            f"Ranked #{item.loser_rank} in the provider's top losers{change_text}."
        )

    if item.activity_rank is not None:
        reasons.append(
            f"Ranked #{item.activity_rank} among the most actively traded symbols."
        )

    if average_sentiment is not None and len(reasons) < 3:
        reasons.append(
            f"Average ticker-specific news tone is {_sentiment(average_sentiment)}."
        )

    return reasons[:3]


def _candidate_symbols(
    news: list[AlphaVantageMarketNewsArticle],
    movers: AlphaVantageMarketMovers | None,
) -> list[str]:
    symbols: list[str] = []

    if movers is not None:
        for mover in (
            movers.top_gainers
            + movers.top_losers
            + movers.most_actively_traded
        ):
            if _is_supported_symbol(mover.ticker):
                symbols.append(mover.ticker)

    news_attention: dict[str, float] = {}

    for article in news:
        for ticker in article.ticker_sentiments:
            if (
                _is_supported_symbol(ticker.ticker)
                and ticker.relevance_score is not None
                and ticker.relevance_score >= MIN_MARKET_NEWS_RELEVANCE
            ):
                news_attention[ticker.ticker] = (
                    news_attention.get(ticker.ticker, 0.0)
                    + ticker.relevance_score
                )

    symbols.extend(
        symbol
        for symbol, _ in sorted(
            news_attention.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    )
    return list(dict.fromkeys(symbols))[:MAX_SNAPSHOT_SYMBOLS]


def _convert_alpaca_news(
    articles: list[AlpacaNewsArticle],
) -> list[AlphaVantageMarketNewsArticle]:
    converted: list[AlphaVantageMarketNewsArticle] = []

    for article in articles:
        compound = float(
            _sentiment_analyzer.polarity_scores(
                f"{article.headline}. {article.summary}"
            )["compound"]
        )
        relevance = max(0.3, 1.0 / len(article.symbols))
        sentiment_label = _sentiment(compound)
        converted.append(
            AlphaVantageMarketNewsArticle(
                title=article.headline,
                url=article.url,
                source=article.source,
                published_at=article.created_at,
                ticker_sentiments=[
                    AlphaVantageTickerSentiment(
                        ticker=symbol,
                        relevance_score=relevance,
                        sentiment_score=compound,
                        sentiment_label=sentiment_label,
                    )
                    for symbol in article.symbols
                    if _is_supported_symbol(symbol)
                ],
            )
        )

    return converted


def _merge_news(
    first: list[AlphaVantageMarketNewsArticle],
    second: list[AlphaVantageMarketNewsArticle],
) -> list[AlphaVantageMarketNewsArticle]:
    articles: dict[str, AlphaVantageMarketNewsArticle] = {}

    for article in first + second:
        articles.setdefault(article.url, article)

    return sorted(
        articles.values(),
        key=lambda article: article.published_at,
        reverse=True,
    )


def _merge_movers(
    alpha_movers: AlphaVantageMarketMovers | None,
    alpaca_movers: AlpacaStockMovers | None,
) -> AlphaVantageMarketMovers | None:
    if alpha_movers is None and alpaca_movers is None:
        return None

    alpaca_gainers = (
        [_convert_alpaca_mover(mover) for mover in alpaca_movers.gainers]
        if alpaca_movers is not None
        else []
    )
    alpaca_losers = (
        [_convert_alpaca_mover(mover) for mover in alpaca_movers.losers]
        if alpaca_movers is not None
        else []
    )

    return AlphaVantageMarketMovers(
        last_updated=(
            alpaca_movers.last_updated
            if alpaca_movers is not None and alpaca_movers.last_updated is not None
            else alpha_movers.last_updated if alpha_movers is not None else None
        ),
        top_gainers=_unique_movers(
            alpaca_gainers
            + (alpha_movers.top_gainers if alpha_movers is not None else [])
        ),
        top_losers=_unique_movers(
            alpaca_losers
            + (alpha_movers.top_losers if alpha_movers is not None else [])
        ),
        most_actively_traded=(
            alpha_movers.most_actively_traded
            if alpha_movers is not None
            else []
        ),
    )


def _convert_alpaca_mover(
    mover: AlpacaScreenerMover,
) -> AlphaVantageMarketMover:
    return AlphaVantageMarketMover(
        ticker=mover.symbol,
        price=mover.price,
        change_amount=mover.change,
        change_percentage=mover.percent_change,
        volume=None,
    )


def _unique_movers(
    movers: list[AlphaVantageMarketMover],
) -> list[AlphaVantageMarketMover]:
    unique: dict[str, AlphaVantageMarketMover] = {}

    for mover in movers:
        unique.setdefault(mover.ticker, mover)

    return list(unique.values())


def _provider_label(alpha_available: bool, alpaca_available: bool) -> str:
    if alpha_available and alpaca_available:
        return "Alpaca + Alpha Vantage"

    if alpaca_available:
        return "Alpaca"

    return "Alpha Vantage"


def _change_percent(item: _TickerAttention) -> float | None:
    snapshot = item.snapshot

    if (
        snapshot is not None
        and snapshot.latest_price is not None
        and snapshot.previous_close is not None
        and snapshot.previous_close > 0
    ):
        return ((snapshot.latest_price / snapshot.previous_close) - 1) * 100

    if item.mover is not None:
        return item.mover.change_percentage

    return None


def _catalyst_score(item: _TickerAttention) -> float:
    average_relevance = (
        fmean(item.relevance_scores) if item.relevance_scores else 0.0
    )
    average_sentiment = (
        fmean(item.sentiment_scores) if item.sentiment_scores else 0.0
    )
    return min(
        100.0,
        min(50.0, item.news_mentions * 15.0)
        + min(35.0, average_relevance * 35.0)
        + min(15.0, abs(average_sentiment) * 30.0),
    )


def _rerank(
    candidates: list[MarketWatchCandidateResponse],
    limit: int,
) -> list[MarketWatchCandidateResponse]:
    return [
        candidate.model_copy(update={"rank": rank})
        for rank, candidate in enumerate(candidates[:limit], start=1)
    ]


def _market_session(value: datetime) -> MarketSession:
    eastern = _as_utc(value).astimezone(ZoneInfo("America/New_York"))
    weekday = eastern.weekday()
    minutes = eastern.hour * 60 + eastern.minute

    if weekday == 5 or (weekday == 6 and minutes < 20 * 60):
        return "closed"

    if weekday == 6:
        return "overnight"

    if weekday == 4 and minutes >= 20 * 60:
        return "closed"

    if minutes < 4 * 60 or minutes >= 20 * 60:
        return "overnight"

    if minutes < 9 * 60 + 30:
        return "premarket"

    if minutes < 16 * 60:
        return "regular"

    return "after_hours"


def _round_optional(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _snapshot_is_fresh(
    snapshot: AlpacaStockSnapshot,
    as_of: datetime,
) -> bool:
    if snapshot.latest_timestamp is None:
        return False

    try:
        timestamp = datetime.fromisoformat(
            snapshot.latest_timestamp.replace("Z", "+00:00")
        )
    except ValueError:
        return False

    return _as_utc(as_of) - _as_utc(timestamp) <= timedelta(
        days=MAX_SNAPSHOT_AGE_DAYS
    )


def _is_supported_symbol(value: str) -> bool:
    return bool(_SYMBOL_PATTERN.fullmatch(value)) and ":" not in value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _alpha_vantage_time(value: datetime) -> str:
    return _as_utc(value).strftime("%Y%m%dT%H%M")


def _iso_timestamp(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")
