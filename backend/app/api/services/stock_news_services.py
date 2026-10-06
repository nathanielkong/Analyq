from datetime import datetime, timedelta, timezone
from statistics import fmean
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.api.schema.stock_news import (
    SentimentLabel,
    StockNewsArticleResponse,
    StockNewsResponse,
    StockNewsTopicResponse,
    StockSentimentSummaryResponse,
)
from app.api.services.stock_history_services import normalize_stock_symbol
from app.api.services.ttl_cache import TTLCache
from app.core.report_policy import report_day
from app.clients.alpha_vantage import AlphaVantageClient, AlphaVantageNewsArticle


NEWS_CACHE_TTL_SECONDS = 900
SENTIMENT_VERSION = "1.0.0"
VADER_MODEL_NAME = "VADER 3.3.2"
MIN_TICKER_RELEVANCE_SCORE = 0.7
_news_cache: TTLCache[tuple[str, ...], StockNewsResponse] = TTLCache(
    ttl_seconds=NEWS_CACHE_TTL_SECONDS
)
_sentiment_analyzer = SentimentIntensityAnalyzer()


def get_stock_news(
    symbol: str,
    days: int,
    limit: int,
    now: datetime | None = None,
) -> StockNewsResponse:
    normalized_symbol = normalize_stock_symbol(symbol)
    period_end = _as_utc(now or datetime.now(timezone.utc)).replace(microsecond=0)
    period_start = period_end - timedelta(days=days)
    cache_key = (
        report_day(period_end),
        normalized_symbol,
        str(days),
        str(limit),
        period_end.date().isoformat(),
    )
    cached_news = _news_cache.get(cache_key)

    if cached_news is not None:
        return cached_news

    provider_articles = AlphaVantageClient().get_news_sentiment(
        symbol=normalized_symbol,
        time_from=_alpha_vantage_time(period_start),
        time_to=_alpha_vantage_time(period_end),
        limit=limit,
    )
    response = build_stock_news_response(
        symbol=normalized_symbol,
        articles=provider_articles,
        period_start=period_start,
        period_end=period_end,
        requested_limit=limit,
        fetched_at=period_end,
    )
    _news_cache.set(cache_key, response)

    return response


def build_stock_news_response(
    symbol: str,
    articles: list[AlphaVantageNewsArticle],
    period_start: datetime,
    period_end: datetime,
    requested_limit: int,
    fetched_at: datetime,
) -> StockNewsResponse:
    normalized_start = _as_utc(period_start)
    normalized_end = _as_utc(period_end)
    deduplicated_articles: dict[str, AlphaVantageNewsArticle] = {}
    low_relevance_count = 0

    for article in articles:
        if (
            article.ticker_relevance_score is None
            or article.ticker_relevance_score < MIN_TICKER_RELEVANCE_SCORE
        ):
            low_relevance_count += 1
            continue

        published_at = _parse_iso_timestamp(article.published_at)

        if (
            published_at is None
            or not normalized_start <= published_at <= normalized_end
        ):
            continue

        canonical_url = _canonicalize_url(article.url)

        if canonical_url not in deduplicated_articles:
            deduplicated_articles[canonical_url] = article

    scored_articles = [
        _score_article(article) for article in deduplicated_articles.values()
    ]
    scored_articles.sort(key=lambda article: article.published_at, reverse=True)
    result_limit_reached = len(articles) >= requested_limit
    warnings: list[str] = []

    if not scored_articles:
        warnings.append("No valid company news was returned for the selected period.")

    if result_limit_reached:
        warnings.append(
            "The provider result limit was reached, so older articles in this period "
            "may be missing."
        )

    if low_relevance_count:
        warnings.append(
            f"Excluded {low_relevance_count} articles with ticker relevance below "
            f"{MIN_TICKER_RELEVANCE_SCORE:.2f}."
        )

    warnings.append(
        "VADER is a general-language baseline and can misunderstand financial wording."
    )

    return StockNewsResponse(
        sentiment_version=SENTIMENT_VERSION,
        symbol=symbol,
        provider="Alpha Vantage",
        model=VADER_MODEL_NAME,
        fetched_at=_iso_timestamp(_as_utc(fetched_at)),
        period_start=_iso_timestamp(normalized_start),
        period_end=_iso_timestamp(normalized_end),
        article_coverage_start=(
            scored_articles[-1].published_at if scored_articles else None
        ),
        article_coverage_end=(
            scored_articles[0].published_at if scored_articles else None
        ),
        requested_limit=requested_limit,
        result_limit_reached=result_limit_reached,
        summary=_summarize_sentiment(scored_articles),
        articles=scored_articles,
        warnings=warnings,
    )


def _score_article(article: AlphaVantageNewsArticle) -> StockNewsArticleResponse:
    analysis_text = ". ".join(
        part for part in (article.title, article.summary) if part.strip()
    )
    scores = _sentiment_analyzer.polarity_scores(analysis_text)
    compound = float(scores["compound"])

    return StockNewsArticleResponse(
        title=article.title,
        summary=article.summary,
        url=article.url,
        source=article.source,
        source_domain=article.source_domain,
        published_at=article.published_at,
        authors=article.authors,
        topics=[
            StockNewsTopicResponse(
                name=topic.name,
                relevance_score=topic.relevance_score,
            )
            for topic in article.topics
        ],
        relevance_score=article.ticker_relevance_score,
        provider_sentiment_score=article.ticker_sentiment_score,
        provider_sentiment_label=article.ticker_sentiment_label,
        vader_positive=float(scores["pos"]),
        vader_neutral=float(scores["neu"]),
        vader_negative=float(scores["neg"]),
        vader_compound=compound,
        vader_label=_sentiment_label(compound),
    )


def _summarize_sentiment(
    articles: list[StockNewsArticleResponse],
) -> StockSentimentSummaryResponse:
    if not articles:
        return StockSentimentSummaryResponse(
            article_count=0,
            positive_count=0,
            neutral_count=0,
            negative_count=0,
            source_count=0,
            average_vader_compound=None,
            relevance_weighted_vader_compound=None,
            average_provider_sentiment=None,
            label="insufficient_data",
        )

    compounds = [article.vader_compound for article in articles]
    weighted_pairs = [
        (
            article.vader_compound,
            article.relevance_score
            if article.relevance_score is not None and article.relevance_score > 0
            else 1.0,
        )
        for article in articles
    ]
    weight_total = sum(weight for _, weight in weighted_pairs)
    weighted_compound = (
        sum(score * weight for score, weight in weighted_pairs) / weight_total
    )
    provider_scores = [
        article.provider_sentiment_score
        for article in articles
        if article.provider_sentiment_score is not None
    ]

    return StockSentimentSummaryResponse(
        article_count=len(articles),
        positive_count=sum(article.vader_label == "positive" for article in articles),
        neutral_count=sum(article.vader_label == "neutral" for article in articles),
        negative_count=sum(article.vader_label == "negative" for article in articles),
        source_count=len({article.source.lower() for article in articles}),
        average_vader_compound=round(fmean(compounds), 4),
        relevance_weighted_vader_compound=round(weighted_compound, 4),
        average_provider_sentiment=(
            round(fmean(provider_scores), 4) if provider_scores else None
        ),
        label=_sentiment_label(weighted_compound),
    )


def _sentiment_label(compound: float) -> SentimentLabel:
    if compound >= 0.05:
        return "positive"

    if compound <= -0.05:
        return "negative"

    return "neutral"


def _canonicalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    filtered_query = [
        (key, query_value)
        for key, query_value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    path = parts.path.rstrip("/") or "/"

    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            urlencode(filtered_query),
            "",
        )
    )


def _parse_iso_timestamp(value: str) -> datetime | None:
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _alpha_vantage_time(value: datetime) -> str:
    return _as_utc(value).strftime("%Y%m%dT%H%M")


def _iso_timestamp(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")
