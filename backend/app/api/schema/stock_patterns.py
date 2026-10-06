from typing import Literal

from pydantic import BaseModel, ConfigDict


DailyPatternName = Literal[
    "rising_streak_high_rsi",
    "falling_streak_low_rsi",
    "unusually_large_up_day",
    "unusually_large_down_day",
]


class DailyPatternCheck(BaseModel):
    name: DailyPatternName
    detected: bool | None
    rule: str


class DailyPatternsResponse(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    version: str = "1.0.0"
    symbol: str
    provider: str
    timeframe: str
    adjusted: bool
    as_of: str
    data_through: str | None
    completed_bar_count: int
    status: Literal["available", "insufficient_data", "stale", "unadjusted"]
    daily_return_pct: float | None = None
    signed_close_streak: int | None = None
    streak_reaches_history_start: bool = False
    rsi_14: float | None = None
    prior_20_return_mean_pct: float | None = None
    prior_20_return_std_pct: float | None = None
    daily_return_zscore: float | None = None
    checks: list[DailyPatternCheck]
    warnings: list[str]
