from datetime import date, datetime, timezone
from math import isfinite
from statistics import fmean, stdev
from zoneinfo import ZoneInfo

from app.api.schema.stock_history import StockHistoryResponse
from app.api.schema.stock_patterns import DailyPatternCheck, DailyPatternsResponse
from app.api.services.stock_analysis_services import calculate_rsi
from app.api.services.stock_history_services import get_stock_history
from app.clients.errors import MarketDataError


MARKET_ZONE = ZoneInfo("America/New_York")
MIN_STREAK = 3
HIGH_RSI = 70
LOW_RSI = 30
LARGE_MOVE_Z = 2
BASELINE_RETURNS = 20
MAX_AGE_DAYS = 7
RULES = {
    "rising_streak_high_rsi": "At least 3 rising observed closes AND simple RSI14 > 70.",
    "falling_streak_low_rsi": "At least 3 falling observed closes AND simple RSI14 < 30.",
    "unusually_large_up_day": "Positive close-to-close return AND prior-20-return z-score >= 2.",
    "unusually_large_down_day": "Negative close-to-close return AND prior-20-return z-score <= -2.",
}


def get_daily_patterns(symbol: str, limit: int = 100) -> DailyPatternsResponse:
    history = get_stock_history(
        symbol=symbol, provider="alpaca", timeframe="1Day", limit=limit
    )
    return build_daily_patterns(history)


def market_bar_date(timestamp: str) -> date:
    try:
        if len(timestamp) == 10:
            return date.fromisoformat(timestamp)
        value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if value.tzinfo is None:
            raise ValueError("Timestamp needs a timezone")
        return value.astimezone(MARKET_ZONE).date()
    except ValueError as error:
        raise MarketDataError(
            "Daily pattern bars contain an invalid timestamp."
        ) from error


def build_daily_patterns(
    history: StockHistoryResponse, *, as_of: datetime | None = None
) -> DailyPatternsResponse:
    """Describe completed daily bars without predicting the next session."""
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    if history.timeframe != "1Day":
        raise MarketDataError("Daily patterns require daily bars.")
    today = now.astimezone(MARKET_ZONE).date()
    dated = [(market_bar_date(bar.timestamp), bar) for bar in history.bars]
    dates = [day for day, _ in dated]
    if dates != sorted(set(dates)):
        raise MarketDataError(
            "Daily pattern bars must have unique, ordered market dates."
        )
    # Conservative policy matches the existing history client: never use today's
    # bar, even after the close. This also makes historical as-of checks reproducible.
    completed = [(day, bar) for day, bar in dated if day < today]
    warnings = [
        *history.warnings,
        "Observed patterns are unvalidated hypotheses, not reversal probabilities or trade signals.",
        "Streaks count supplied daily bars, not calendar days. Missing exchange sessions are not verified.",
        "Today's New York session is excluded, even after close. Daily bars cannot identify premarket/session divergence.",
        "RSI uses simple 14-change averages, matching current analysis, not Wilder smoothing.",
    ]
    if len(completed) != len(dated):
        warnings.append("Excluded same-day or future bars from the calculation.")
    result = DailyPatternsResponse(
        symbol=history.symbol,
        provider=history.provider,
        timeframe=history.timeframe,
        adjusted=history.adjusted,
        as_of=now.isoformat(),
        data_through=completed[-1][1].timestamp if completed else None,
        completed_bar_count=len(completed),
        status="insufficient_data",
        checks=[
            DailyPatternCheck(name=name, detected=None, rule=rule)
            for name, rule in RULES.items()
        ],
        warnings=warnings,
    )
    if not history.adjusted:
        result.status = "unadjusted"
        result.warnings.append(
            "Adjusted prices are required; split-related jumps could mimic patterns."
        )
        return result
    closes = [bar.close for _, bar in completed]
    if any(not isfinite(close) or close <= 0 for close in closes):
        raise MarketDataError("Daily pattern closes must be finite and positive.")
    if not completed:
        return result
    if (today - completed[-1][0]).days > MAX_AGE_DAYS:
        result.status = "stale"
        result.warnings.append(
            "Latest bar is more than 7 calendar days old; detection withheld."
        )
        return result
    if len(closes) < 2:
        return result
    returns = [
        (current / previous - 1) * 100 for previous, current in zip(closes, closes[1:])
    ]
    if not all(isfinite(value) for value in returns):
        raise MarketDataError(
            "Daily pattern returns exceed the supported numeric range."
        )
    latest = returns[-1]
    direction = 1 if latest > 0 else -1 if latest < 0 else 0
    streak = 0
    for value in reversed(returns):
        if direction == 0 or value * direction <= 0:
            break
        streak += direction
    result.daily_return_pct = latest
    result.signed_close_streak = streak
    result.streak_reaches_history_start = abs(streak) == len(returns)
    result.rsi_14 = calculate_rsi(closes, 14)
    if result.rsi_14 is not None:
        result.checks[0].detected = streak >= MIN_STREAK and result.rsi_14 > HIGH_RSI
        result.checks[1].detected = streak <= -MIN_STREAK and result.rsi_14 < LOW_RSI
    # Exclude the move being tested from its baseline: 22 closes provide 20
    # preceding daily returns plus the latest return. Never use future observations.
    if len(returns) >= BASELINE_RETURNS + 1:
        baseline = returns[-(BASELINE_RETURNS + 1) : -1]
        mean, spread = fmean(baseline), stdev(baseline)
        result.prior_20_return_mean_pct = mean
        result.prior_20_return_std_pct = spread
        if spread > 1e-12:
            zscore = (latest - mean) / spread
            result.daily_return_zscore = zscore
            result.checks[2].detected = latest > 0 and zscore >= LARGE_MOVE_Z
            result.checks[3].detected = latest < 0 and zscore <= -LARGE_MOVE_Z
        else:
            result.warnings.append(
                "Prior returns have zero variance; unusual-move checks are unavailable."
            )
    else:
        result.warnings.append(
            "22 completed closes are needed for all checks; unavailable checks return null, not false."
        )
    if all(check.detected is not None for check in result.checks):
        result.status = "available"
    return result
