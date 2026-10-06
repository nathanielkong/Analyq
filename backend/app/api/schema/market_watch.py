from typing import Literal

from pydantic import BaseModel


MarketWatchSignal = Literal[
    "news_catalyst",
    "session_mover",
    "high_activity",
    "mixed_attention",
]
MarketWatchSentiment = Literal["bullish", "mixed", "bearish", "unavailable"]
MarketSession = Literal[
    "overnight",
    "premarket",
    "regular",
    "after_hours",
    "closed",
]


class MarketWatchCandidateResponse(BaseModel):
    rank: int
    symbol: str
    attention_score: float
    catalyst_score: float
    signal: MarketWatchSignal
    market_session: MarketSession
    price: float | None
    previous_close: float | None
    change_amount: float | None
    change_percent: float | None
    volume: int | None
    snapshot_at: str | None
    news_mentions: int
    average_relevance: float | None
    average_sentiment: float | None
    sentiment: MarketWatchSentiment
    latest_headline: str | None
    latest_source: str | None
    latest_url: str | None
    latest_published_at: str | None
    reasons: list[str]


class MarketWatchResponse(BaseModel):
    generated_at: str
    provider: str
    period_start: str
    period_end: str
    market_snapshot_at: str | None
    market_data_freshness: Literal["provider_snapshot", "combined_snapshot"]
    market_session: MarketSession
    snapshot_feed: str | None
    candidates: list[MarketWatchCandidateResponse]
    movers: list[MarketWatchCandidateResponse]
    news_catalysts: list[MarketWatchCandidateResponse]
    warnings: list[str]
