from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.api.schema.stock_patterns import DailyPatternName, DailyPatternsResponse


class BacktestReturnSummary(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    count: int
    reversals: int
    flat_outcomes: int
    reversal_rate_pct: float | None
    mean_return_pct: float | None
    median_return_pct: float | None


class PatternOutcome(BaseModel):
    signal_timestamp: str
    outcome_timestamp: str
    forward_return_pct: float
    reversed: bool


class PatternHorizonBacktest(BaseModel):
    horizon_bars: Literal[1, 3, 5]
    status: Literal["no_observations", "small_sample", "descriptive_only"]
    signal_count: int
    pending_outcomes: int
    overlap_excluded: int
    pattern: BacktestReturnSummary
    baseline: BacktestReturnSummary
    reversal_rate_difference_pp: float | None
    approximate_wilson_95_low_pct: float | None
    approximate_wilson_95_high_pct: float | None
    outcomes: list[PatternOutcome]


class PatternBacktestResult(BaseModel):
    name: DailyPatternName
    rule: str
    reversal_direction: Literal["up", "down"]
    initial_active_excluded: int
    horizons: list[PatternHorizonBacktest]


class DailyPatternBacktestResponse(BaseModel):
    version: str = "1.0.0"
    detector_version: str
    evaluation: Literal["exploratory_historical_study"] = "exploratory_historical_study"
    symbol: str
    provider: str
    timeframe: str
    adjusted: bool
    as_of: str
    start_timestamp: str | None
    data_through: str | None
    completed_bar_count: int
    latest_patterns: DailyPatternsResponse
    results: list[PatternBacktestResult]
    warnings: list[str]
