from typing import Literal

from pydantic import BaseModel


AnalysisMode = Literal["historical"]
AnalysisTrend = Literal["uptrend", "downtrend", "sideways", "insufficient_data"]
AnalysisRiskLevel = Literal["low", "medium", "high", "insufficient_data"]
EntryPosition = Literal[
    "above_near_term_zone",
    "inside_near_term_zone",
    "between_reference_zones",
    "inside_deeper_zone",
    "below_reference_zones",
    "insufficient_data",
]
TechnicalEntrySignal = Literal[
    "wait_for_pullback",
    "starter_entry",
    "preferred_entry",
    "avoid_until_stabilizes",
    "insufficient_data",
]


class TechnicalEntryZoneResponse(BaseModel):
    label: str
    lower_price: float
    upper_price: float
    reference_price: float
    basis: str


class TechnicalEntryPlanResponse(BaseModel):
    signal: TechnicalEntrySignal
    preferred_entry_lower: float | None
    preferred_entry_upper: float | None
    patient_entry_lower: float | None
    patient_entry_upper: float | None
    upside_reference_price: float | None
    invalidation_price: float | None
    estimated_reward_risk_ratio: float | None
    method: str


class StockEntryContextResponse(BaseModel):
    reference_price: float
    position: EntryPosition
    atr_14: float | None
    atr_14_pct: float | None
    rsi_14: float | None
    distance_from_sma_20_pct: float | None
    distance_from_sma_50_pct: float | None
    recent_low_20: float | None
    recent_high_20: float | None
    recent_low_50: float | None
    recent_high_50: float | None
    zones: list[TechnicalEntryZoneResponse]
    plan: TechnicalEntryPlanResponse
    notes: list[str]


class StockAnalysisResponse(BaseModel):
    analysis_version: str
    symbol: str
    provider: str
    timeframe: str
    mode: AnalysisMode
    as_of: str
    data_through: str
    adjusted: bool
    bar_count: int
    sample_sufficient: bool
    trend_sample_sufficient: bool
    start_timestamp: str
    end_timestamp: str
    first_close: float
    latest_close: float
    period_return_pct: float
    compound_average_daily_return_pct: float
    annualized_volatility_pct: float | None
    moving_average_20: float | None
    moving_average_50: float | None
    max_drawdown_pct: float
    trend: AnalysisTrend
    risk_level: AnalysisRiskLevel
    entry_context: StockEntryContextResponse
    reasons: list[str]
    warnings: list[str]
