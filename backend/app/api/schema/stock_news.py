from typing import Literal

from pydantic import BaseModel


SentimentLabel = Literal["positive", "neutral", "negative", "insufficient_data"]


class StockNewsTopicResponse(BaseModel):
    name: str
    relevance_score: float | None


class StockNewsArticleResponse(BaseModel):
    title: str
    summary: str
    url: str
    source: str
    source_domain: str | None
    published_at: str
    authors: list[str]
    topics: list[StockNewsTopicResponse]
    relevance_score: float | None
    provider_sentiment_score: float | None
    provider_sentiment_label: str | None
    vader_positive: float
    vader_neutral: float
    vader_negative: float
    vader_compound: float
    vader_label: SentimentLabel


class StockSentimentSummaryResponse(BaseModel):
    article_count: int
    positive_count: int
    neutral_count: int
    negative_count: int
    source_count: int
    average_vader_compound: float | None
    relevance_weighted_vader_compound: float | None
    average_provider_sentiment: float | None
    label: SentimentLabel


class StockNewsResponse(BaseModel):
    sentiment_version: str
    symbol: str
    provider: str
    model: str
    fetched_at: str
    period_start: str
    period_end: str
    article_coverage_start: str | None
    article_coverage_end: str | None
    requested_limit: int
    result_limit_reached: bool
    summary: StockSentimentSummaryResponse
    articles: list[StockNewsArticleResponse]
    warnings: list[str]
