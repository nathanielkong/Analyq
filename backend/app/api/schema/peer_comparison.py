from typing import Literal

from pydantic import BaseModel, Field

RankingPreset = Literal["value", "growth", "quality"]


class PeerComparisonRequest(BaseModel):
    symbols: list[str] = Field(min_length=2, max_length=5)
    preset: RankingPreset = "quality"


class PeerMetrics(BaseModel):
    symbol: str
    sector: str | None
    fiscal_date: str | None
    fetched_at: str
    price_sales_ttm: float | None
    price_sales_forward: float | None = None
    price_fcf_annual: float | None
    ev_ebitda: float | None
    gross_margin_pct: float | None
    quarterly_revenue_growth_yoy_pct: float | None
    sales_growth_multiple: float | None
    quality_score: float | None
    growth_score: float | None
    value_score: float | None
    weighted_score: float | None = None
    rank: int | None = None


class PeerComparisonResponse(BaseModel):
    preset: RankingPreset
    weights: dict[str, float]
    rows: list[PeerMetrics]
    warnings: list[str]
    validation_status: Literal["unvalidated_heuristic"] = "unvalidated_heuristic"
