from datetime import datetime, timezone
from math import log, sqrt
from statistics import fmean, stdev

from app.api.schema.stock_analysis import (
    AnalysisMode,
    AnalysisRiskLevel,
    AnalysisTrend,
    EntryPosition,
    StockEntryContextResponse,
    StockAnalysisResponse,
    TechnicalEntryPlanResponse,
    TechnicalEntryZoneResponse,
)
from app.api.schema.stock_history import StockHistoryBarResponse, StockHistoryResponse
from app.api.services.stock_history_services import (
    HistoryProvider,
    HistoryTimeframe,
    get_stock_history,
)


TRADING_DAYS_PER_YEAR = 252
MIN_VOLATILITY_BARS = 30
MIN_TREND_BARS = 50
TREND_TOLERANCE = 0.005
ANALYSIS_VERSION = "2.2.0"
ENTRY_ZONE_ATR_LOWER_MULTIPLIER = 0.5
ENTRY_ZONE_ATR_UPPER_MULTIPLIER = 0.25


class StockAnalysisError(Exception):
    pass


def get_stock_analysis(
    symbol: str,
    provider: HistoryProvider,
    timeframe: HistoryTimeframe,
    mode: AnalysisMode,
    limit: int,
) -> StockAnalysisResponse:
    normalized_symbol = symbol.strip().upper()
    history = get_stock_history(
        symbol=normalized_symbol,
        provider=provider,
        timeframe=timeframe,
        limit=limit,
    )

    return build_stock_analysis(history, mode)


def build_stock_analysis(
    history: StockHistoryResponse,
    mode: AnalysisMode,
    as_of: str | None = None,
) -> StockAnalysisResponse:
    if len(history.bars) < 2:
        raise StockAnalysisError(
            "At least two historical bars are required for analysis."
        )

    closes = [bar.close for bar in history.bars]

    if any(close <= 0 for close in closes):
        raise StockAnalysisError("Historical bars must have positive close prices.")

    log_returns = _calculate_log_returns(closes)
    first_close = closes[0]
    latest_close = closes[-1]
    return_periods = len(closes) - 1
    period_return_pct = ((latest_close / first_close) - 1) * 100
    compound_average_daily_return_pct = (
        ((latest_close / first_close) ** (1 / return_periods)) - 1
    ) * 100
    sample_sufficient = len(closes) >= MIN_VOLATILITY_BARS
    trend_sample_sufficient = len(closes) >= MIN_TREND_BARS
    annualized_volatility_pct = (
        stdev(log_returns) * sqrt(TRADING_DAYS_PER_YEAR) * 100
        if sample_sufficient
        else None
    )
    moving_average_20 = _moving_average(closes, 20)
    moving_average_50 = _moving_average(closes, 50)
    max_drawdown_pct = _calculate_max_drawdown_pct(closes)
    entry_context = _build_entry_context(
        history=history,
        moving_average_20=moving_average_20,
        moving_average_50=moving_average_50,
    )
    trend = _classify_trend(
        latest_close=latest_close,
        moving_average_20=moving_average_20,
        moving_average_50=moving_average_50,
    )
    risk_level = _classify_risk(
        annualized_volatility_pct=annualized_volatility_pct,
        max_drawdown_pct=max_drawdown_pct,
    )
    warnings = list(history.warnings)

    if not sample_sufficient:
        warnings.append(
            f"At least {MIN_VOLATILITY_BARS} daily bars are required for volatility "
            "and risk classification."
        )
    else:
        warnings.append(
            f"Volatility is estimated from {len(log_returns)} daily returns and may be noisy."
        )

    if not trend_sample_sufficient:
        warnings.append(
            f"At least {MIN_TREND_BARS} daily bars are required for trend classification."
        )

    warnings.append(
        "Risk thresholds are provisional and are not yet calibrated against a benchmark."
    )

    return StockAnalysisResponse(
        analysis_version=ANALYSIS_VERSION,
        symbol=history.symbol,
        provider=history.provider,
        timeframe=history.timeframe,
        mode=mode,
        as_of=as_of or _utc_timestamp(),
        data_through=history.bars[-1].timestamp,
        adjusted=history.adjusted,
        bar_count=len(history.bars),
        sample_sufficient=sample_sufficient,
        trend_sample_sufficient=trend_sample_sufficient,
        start_timestamp=history.bars[0].timestamp,
        end_timestamp=history.bars[-1].timestamp,
        first_close=_round_metric(first_close),
        latest_close=_round_metric(latest_close),
        period_return_pct=_round_metric(period_return_pct),
        compound_average_daily_return_pct=_round_metric(
            compound_average_daily_return_pct
        ),
        annualized_volatility_pct=_round_optional_metric(annualized_volatility_pct),
        moving_average_20=_round_optional_metric(moving_average_20),
        moving_average_50=_round_optional_metric(moving_average_50),
        max_drawdown_pct=_round_metric(max_drawdown_pct),
        trend=trend,
        risk_level=risk_level,
        entry_context=entry_context,
        reasons=_build_reasons(
            latest_close=latest_close,
            moving_average_20=moving_average_20,
            moving_average_50=moving_average_50,
            period_return_pct=period_return_pct,
            annualized_volatility_pct=annualized_volatility_pct,
            max_drawdown_pct=max_drawdown_pct,
            trend=trend,
            risk_level=risk_level,
        ),
        warnings=warnings,
    )


def _calculate_log_returns(closes: list[float]) -> list[float]:
    return [
        log(current_close / previous_close)
        for previous_close, current_close in zip(closes, closes[1:])
    ]


def _moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None

    return fmean(values[-window:])


def _calculate_max_drawdown_pct(closes: list[float]) -> float:
    peak = closes[0]
    max_drawdown = 0.0

    for close in closes:
        peak = max(peak, close)
        drawdown = (close / peak) - 1
        max_drawdown = min(max_drawdown, drawdown)

    return max_drawdown * 100


def _build_entry_context(
    history: StockHistoryResponse,
    moving_average_20: float | None,
    moving_average_50: float | None,
) -> StockEntryContextResponse:
    bars = history.bars
    closes = [bar.close for bar in bars]
    latest_close = closes[-1]
    atr_14 = _average_true_range(bars, 14)
    rsi_14 = calculate_rsi(closes, 14)
    zones: list[TechnicalEntryZoneResponse] = []

    if atr_14 is not None and moving_average_20 is not None:
        zones.append(
            _entry_zone(
                label="Near-term pullback zone",
                reference_price=moving_average_20,
                atr_14=atr_14,
                basis="20-day moving average with an ATR-based tolerance",
            )
        )

    if atr_14 is not None and moving_average_50 is not None:
        zones.append(
            _entry_zone(
                label="Deeper pullback zone",
                reference_price=moving_average_50,
                atr_14=atr_14,
                basis="50-day moving average with an ATR-based tolerance",
            )
        )

    position = _classify_entry_position(latest_close, zones)
    atr_14_pct = (
        (atr_14 / latest_close) * 100
        if atr_14 is not None and latest_close > 0
        else None
    )
    notes = _build_entry_notes(
        reference_price=latest_close,
        position=position,
        atr_14_pct=atr_14_pct,
        rsi_14=rsi_14,
        moving_average_20=moving_average_20,
        moving_average_50=moving_average_50,
    )

    recent_low_20 = _recent_price(bars, 20, "low")
    recent_high_20 = _recent_price(bars, 20, "high")
    recent_low_50 = _recent_price(bars, 50, "low")
    recent_high_50 = _recent_price(bars, 50, "high")
    plan = _build_entry_plan(
        position=position,
        zones=zones,
        atr_14=atr_14,
        recent_low_50=recent_low_50,
        recent_high_20=recent_high_20,
    )

    return StockEntryContextResponse(
        reference_price=_round_metric(latest_close),
        position=position,
        atr_14=_round_optional_metric(atr_14),
        atr_14_pct=_round_optional_metric(atr_14_pct),
        rsi_14=_round_optional_metric(rsi_14),
        distance_from_sma_20_pct=_percentage_distance(
            latest_close,
            moving_average_20,
        ),
        distance_from_sma_50_pct=_percentage_distance(
            latest_close,
            moving_average_50,
        ),
        recent_low_20=recent_low_20,
        recent_high_20=recent_high_20,
        recent_low_50=recent_low_50,
        recent_high_50=recent_high_50,
        zones=zones,
        plan=plan,
        notes=notes,
    )


def _build_entry_plan(
    position: EntryPosition,
    zones: list[TechnicalEntryZoneResponse],
    atr_14: float | None,
    recent_low_50: float | None,
    recent_high_20: float | None,
) -> TechnicalEntryPlanResponse:
    if len(zones) < 2 or atr_14 is None:
        return TechnicalEntryPlanResponse(
            signal="insufficient_data",
            preferred_entry_lower=None,
            preferred_entry_upper=None,
            patient_entry_lower=None,
            patient_entry_upper=None,
            upside_reference_price=recent_high_20,
            invalidation_price=None,
            estimated_reward_risk_ratio=None,
            method="Insufficient history for a complete technical entry plan.",
        )

    near_term_zone, deeper_zone = zones
    signal_by_position = {
        "above_near_term_zone": "wait_for_pullback",
        "inside_near_term_zone": "starter_entry",
        "between_reference_zones": "preferred_entry",
        "inside_deeper_zone": "preferred_entry",
        "below_reference_zones": "avoid_until_stabilizes",
        "insufficient_data": "insufficient_data",
    }
    invalidation_price = (
        recent_low_50 - (atr_14 * 0.5)
        if recent_low_50 is not None
        else deeper_zone.lower_price - (atr_14 * 0.5)
    )
    entry_midpoint = (near_term_zone.lower_price + near_term_zone.upper_price) / 2
    estimated_reward_risk_ratio = _reward_risk_ratio(
        entry_price=entry_midpoint,
        upside_price=recent_high_20,
        invalidation_price=invalidation_price,
    )

    return TechnicalEntryPlanResponse(
        signal=signal_by_position[position],
        preferred_entry_lower=near_term_zone.lower_price,
        preferred_entry_upper=near_term_zone.upper_price,
        patient_entry_lower=deeper_zone.lower_price,
        patient_entry_upper=deeper_zone.upper_price,
        upside_reference_price=recent_high_20,
        invalidation_price=_round_metric(invalidation_price),
        estimated_reward_risk_ratio=_round_optional_metric(estimated_reward_risk_ratio),
        method=(
            "Preferred and patient ranges use the 20-day and 50-day moving averages "
            "with ATR tolerance. The upside reference is the recent 20-day high; "
            "invalidation is the recent 50-day low minus half an ATR."
        ),
    )


def _reward_risk_ratio(
    entry_price: float,
    upside_price: float | None,
    invalidation_price: float,
) -> float | None:
    if upside_price is None:
        return None

    potential_reward = upside_price - entry_price
    potential_risk = entry_price - invalidation_price

    if potential_reward <= 0 or potential_risk <= 0:
        return None

    return potential_reward / potential_risk


def _entry_zone(
    label: str,
    reference_price: float,
    atr_14: float,
    basis: str,
) -> TechnicalEntryZoneResponse:
    return TechnicalEntryZoneResponse(
        label=label,
        lower_price=_round_metric(
            reference_price - (atr_14 * ENTRY_ZONE_ATR_LOWER_MULTIPLIER)
        ),
        upper_price=_round_metric(
            reference_price + (atr_14 * ENTRY_ZONE_ATR_UPPER_MULTIPLIER)
        ),
        reference_price=_round_metric(reference_price),
        basis=basis,
    )


def _classify_entry_position(
    reference_price: float,
    zones: list[TechnicalEntryZoneResponse],
) -> EntryPosition:
    if len(zones) < 2:
        return "insufficient_data"

    near_term_zone, deeper_zone = zones

    if near_term_zone.lower_price <= reference_price <= near_term_zone.upper_price:
        return "inside_near_term_zone"

    if deeper_zone.lower_price <= reference_price <= deeper_zone.upper_price:
        return "inside_deeper_zone"

    highest_upper_bound = max(zone.upper_price for zone in zones)
    lowest_lower_bound = min(zone.lower_price for zone in zones)

    if reference_price > highest_upper_bound:
        return "above_near_term_zone"

    if reference_price < lowest_lower_bound:
        return "below_reference_zones"

    return "between_reference_zones"


def _average_true_range(
    bars: list[StockHistoryBarResponse],
    window: int,
) -> float | None:
    if len(bars) < window + 1:
        return None

    recent_bars = bars[-window:]
    previous_closes = [bar.close for bar in bars[-(window + 1) : -1]]
    true_ranges = [
        max(
            current.high - current.low,
            abs(current.high - previous_close),
            abs(current.low - previous_close),
        )
        for previous_close, current in zip(previous_closes, recent_bars)
    ]
    return fmean(true_ranges)


def calculate_rsi(
    closes: list[float],
    window: int,
) -> float | None:
    """RSI using simple average gains/losses, not Wilder smoothing."""
    if len(closes) < window + 1:
        return None

    changes = [
        current - previous
        for previous, current in zip(
            closes[-(window + 1) :],
            closes[-window:],
        )
    ]
    average_gain = fmean(max(change, 0.0) for change in changes)
    average_loss = fmean(max(-change, 0.0) for change in changes)

    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0

    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def _percentage_distance(value: float, reference: float | None) -> float | None:
    if reference is None or reference <= 0:
        return None

    return _round_metric(((value / reference) - 1) * 100)


def _recent_price(
    bars: list[StockHistoryBarResponse],
    window: int,
    field: str,
) -> float | None:
    if len(bars) < window:
        return None

    values = [getattr(bar, field) for bar in bars[-window:]]
    value = min(values) if field == "low" else max(values)
    return _round_metric(value)


def _build_entry_notes(
    reference_price: float,
    position: EntryPosition,
    atr_14_pct: float | None,
    rsi_14: float | None,
    moving_average_20: float | None,
    moving_average_50: float | None,
) -> list[str]:
    notes: list[str] = []

    if moving_average_20 is not None and moving_average_50 is not None:
        notes.append(
            f"Latest adjusted close is {_round_metric(reference_price)}, "
            f"compared with SMA20 {_round_metric(moving_average_20)} and "
            f"SMA50 {_round_metric(moving_average_50)}."
        )

    if atr_14_pct is not None:
        notes.append(
            f"ATR14 is approximately {_round_metric(atr_14_pct)}% of price, "
            "so narrow entry levels may be crossed during ordinary daily movement."
        )

    if rsi_14 is not None:
        if rsi_14 >= 70:
            rsi_description = "historically stretched on the upside"
        elif rsi_14 <= 30:
            rsi_description = "historically stretched on the downside"
        else:
            rsi_description = "between common overbought and oversold thresholds"

        notes.append(f"RSI14 is {_round_metric(rsi_14)}, which is {rsi_description}.")

    if position == "insufficient_data":
        notes.append("There is not enough daily history to construct reference zones.")
    else:
        notes.append(
            "These zones are volatility-aware technical references, not estimates of "
            "intrinsic value or guaranteed buying opportunities."
        )

    return notes


def _classify_trend(
    latest_close: float,
    moving_average_20: float | None,
    moving_average_50: float | None,
) -> AnalysisTrend:
    if moving_average_20 is None or moving_average_50 is None:
        return "insufficient_data"

    if latest_close > moving_average_20 * (
        1 + TREND_TOLERANCE
    ) and moving_average_20 > moving_average_50 * (1 + TREND_TOLERANCE):
        return "uptrend"

    if latest_close < moving_average_20 * (
        1 - TREND_TOLERANCE
    ) and moving_average_20 < moving_average_50 * (1 - TREND_TOLERANCE):
        return "downtrend"

    return "sideways"


def _classify_risk(
    annualized_volatility_pct: float | None,
    max_drawdown_pct: float,
) -> AnalysisRiskLevel:
    if annualized_volatility_pct is None:
        return "insufficient_data"

    if annualized_volatility_pct >= 40 or max_drawdown_pct <= -20:
        return "high"

    if annualized_volatility_pct >= 20 or max_drawdown_pct <= -10:
        return "medium"

    return "low"


def _build_reasons(
    latest_close: float,
    moving_average_20: float | None,
    moving_average_50: float | None,
    period_return_pct: float,
    annualized_volatility_pct: float | None,
    max_drawdown_pct: float,
    trend: AnalysisTrend,
    risk_level: AnalysisRiskLevel,
) -> list[str]:
    reasons = [
        f"Adjusted-price return over the selected period is {_round_metric(period_return_pct)}%."
    ]

    if trend == "insufficient_data":
        reasons.append(
            f"Trend is unavailable because fewer than {MIN_TREND_BARS} daily bars were received."
        )
    else:
        reasons.append(
            f"Close {_round_metric(latest_close)} versus 20-day "
            f"{_round_optional_metric(moving_average_20)} and 50-day "
            f"{_round_optional_metric(moving_average_50)} averages indicates {trend}."
        )

    if annualized_volatility_pct is None:
        reasons.append(
            f"Risk is unavailable because fewer than {MIN_VOLATILITY_BARS} daily bars were received."
        )
    else:
        reasons.append(
            f"Annualized sample volatility is {_round_metric(annualized_volatility_pct)}% "
            f"and maximum drawdown is {_round_metric(max_drawdown_pct)}%, indicating "
            f"{risk_level} risk under the current provisional thresholds."
        )

    return reasons


def _round_metric(value: float) -> float:
    return round(value, 4)


def _round_optional_metric(value: float | None) -> float | None:
    if value is None:
        return None

    return _round_metric(value)


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
