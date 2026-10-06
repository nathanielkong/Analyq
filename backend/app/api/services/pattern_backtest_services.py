from datetime import datetime, time, timedelta, timezone
from math import isfinite, sqrt
from statistics import fmean, median
from typing import Literal

from app.api.schema.pattern_backtest import (
    BacktestReturnSummary,
    DailyPatternBacktestResponse,
    PatternBacktestResult,
    PatternHorizonBacktest,
    PatternOutcome,
)
from app.api.schema.stock_history import StockHistoryBarResponse, StockHistoryResponse
from app.api.schema.stock_patterns import DailyPatternName
from app.api.services.stock_history_services import get_stock_history
from app.api.services.stock_pattern_services import (
    MARKET_ZONE,
    RULES,
    build_daily_patterns,
    market_bar_date,
)
from app.clients.errors import MarketDataError


HORIZONS = (1, 3, 5)
SMALL_SAMPLE_THRESHOLD = 30
REVERSAL_DIRECTIONS: dict[DailyPatternName, Literal["up", "down"]] = {
    "rising_streak_high_rsi": "down",
    "falling_streak_low_rsi": "up",
    "unusually_large_up_day": "down",
    "unusually_large_down_day": "up",
}


def get_daily_pattern_backtest(
    symbol: str, limit: int = 250
) -> DailyPatternBacktestResponse:
    history = get_stock_history(
        symbol=symbol, provider="alpaca", timeframe="1Day", limit=limit
    )
    return build_daily_pattern_backtest(history)


def _summary(returns: list[float], direction: str) -> BacktestReturnSummary:
    reversals = sum(value > 0 if direction == "up" else value < 0 for value in returns)
    return BacktestReturnSummary(
        count=len(returns),
        reversals=reversals,
        flat_outcomes=sum(value == 0 for value in returns),
        reversal_rate_pct=100 * reversals / len(returns) if returns else None,
        mean_return_pct=fmean(returns) if returns else None,
        median_return_pct=median(returns) if returns else None,
    )


def _wilson_interval(successes: int, count: int) -> tuple[float | None, float | None]:
    if count == 0:
        return None, None
    z = 1.959963984540054
    p = successes / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    margin = z * sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / denominator
    return max(0.0, center - margin) * 100, min(1.0, center + margin) * 100


def _forward_return(
    bars: list[StockHistoryBarResponse], index: int, horizon: int
) -> float:
    value = (bars[index + horizon].close / bars[index].close - 1) * 100
    if not isfinite(value):
        raise MarketDataError(
            "Pattern backtest returns exceed the supported numeric range."
        )
    return value


def _evaluate_horizon(
    bars: list[StockHistoryBarResponse],
    states: list[bool | None],
    signals: list[int],
    direction: Literal["up", "down"],
    horizon: int,
) -> PatternHorizonBacktest:
    outcomes = []
    pending = overlap = 0
    next_allowed = 0
    for index in signals:
        if index + horizon >= len(bars):
            pending += 1
            continue
        if index < next_allowed:
            overlap += 1
            continue
        value = _forward_return(bars, index, horizon)
        outcomes.append(
            PatternOutcome(
                signal_timestamp=bars[index].timestamp,
                outcome_timestamp=bars[index + horizon].timestamp,
                forward_return_pct=value,
                reversed=value > 0 if direction == "up" else value < 0,
            )
        )
        next_allowed = index + horizon
    # Unconditional baseline uses every evaluable decision date (including
    # signal dates) with the same horizon and data cutoff. It is not regime matched.
    baseline = _summary(
        [
            _forward_return(bars, index, horizon)
            for index, state in enumerate(states)
            if state is not None and index + horizon < len(bars)
        ],
        direction,
    )
    pattern = _summary([item.forward_return_pct for item in outcomes], direction)
    low, high = _wilson_interval(pattern.reversals, pattern.count)
    return PatternHorizonBacktest(
        horizon_bars=horizon,
        status="no_observations"
        if not outcomes
        else "small_sample"
        if len(outcomes) < SMALL_SAMPLE_THRESHOLD
        else "descriptive_only",
        signal_count=len(signals),
        pending_outcomes=pending,
        overlap_excluded=overlap,
        pattern=pattern,
        baseline=baseline,
        reversal_rate_difference_pp=(
            pattern.reversal_rate_pct - baseline.reversal_rate_pct
        )
        if pattern.reversal_rate_pct is not None
        and baseline.reversal_rate_pct is not None
        else None,
        approximate_wilson_95_low_pct=low,
        approximate_wilson_95_high_pct=high,
        outcomes=outcomes,
    )


def build_daily_pattern_backtest(
    history: StockHistoryResponse, *, as_of: datetime | None = None
) -> DailyPatternBacktestResponse:
    now = as_of or datetime.now(timezone.utc)
    latest = build_daily_patterns(history, as_of=now)
    if not history.adjusted:
        raise MarketDataError("Pattern backtests require adjusted daily prices.")
    # Validation and the New York date cutoff are shared with the live detector.
    bars = history.bars[: latest.completed_bar_count]
    states: dict[DailyPatternName, list[bool | None]] = {
        name: [] for name in REVERSAL_DIRECTIONS
    }
    for index, bar in enumerate(bars):
        next_date = market_bar_date(bar.timestamp) + timedelta(days=1)
        cutoff = datetime.combine(next_date, time.min, tzinfo=MARKET_ZONE)
        prefix = history.model_copy(update={"bars": bars[: index + 1], "warnings": []})
        detected = build_daily_patterns(prefix, as_of=cutoff)
        for check in detected.checks:
            states[check.name].append(check.detected)
    results = []
    for name, direction in REVERSAL_DIRECTIONS.items():
        values = states[name]
        signals = []
        initial_active = 0
        previous = None
        for index, state in enumerate(values):
            if state is True:
                if previous is False:
                    signals.append(index)
                elif previous is None:
                    # An already-active pattern when data becomes evaluable has
                    # no known start. Do not invent a first activation date.
                    initial_active += 1
            previous = state
        results.append(
            PatternBacktestResult(
                name=name,
                rule=RULES[name],
                reversal_direction=direction,
                initial_active_excluded=initial_active,
                horizons=[
                    _evaluate_horizon(bars, values, signals, direction, horizon)
                    for horizon in HORIZONS
                ],
            )
        )
    return DailyPatternBacktestResponse(
        detector_version=latest.version,
        symbol=history.symbol,
        provider=history.provider,
        timeframe=history.timeframe,
        adjusted=history.adjusted,
        as_of=now.isoformat(),
        start_timestamp=bars[0].timestamp if bars else None,
        data_through=latest.data_through,
        completed_bar_count=len(bars),
        latest_patterns=latest,
        results=results,
        warnings=[
            *latest.warnings,
            "Exploratory same-history study, not held-out model validation, predicted accuracy or trading profitability.",
            "A reversal is a strictly opposite final close-to-close return; flat outcomes remain in the denominator and are not reversals.",
            "Only false-to-true activations count. Initially active or previously unknown patterns are excluded until a known reset.",
            "Overlapping outcomes are excluded within each pattern/horizon; results across patterns or horizons are not independent.",
            "The baseline uses all evaluable dates, including signal dates and overlapping returns; it is unconditional, not matched by market regime.",
            "Wilson intervals are approximate binomial intervals. Serial dependence can make them too narrow, even after overlap exclusion.",
            "Fewer than 30 measured events is flagged as a small sample; 30 or more is not proof of a predictive edge.",
            "Returns are raw adjusted close-to-close outcomes, not executable entries or net P&L. Fees, spreads, slippage and dividends are not separately simulated.",
            "Horizon counts supplied bars. Missing-session continuity and historical point-in-time adjustment vintages are not verified.",
        ],
    )
