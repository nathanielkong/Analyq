from app.api.schema.horizon_signals import HorizonSignal
from app.api.schema.stock_analysis import StockAnalysisResponse
from app.api.schema.stock_direction import StockOutlookResponse
from app.api.schema.stock_fundamentals import StockFundamentalsResponse


def build_horizon_signals(
    analysis: StockAnalysisResponse | None,
    fundamentals: StockFundamentalsResponse | None,
    outlook: StockOutlookResponse | None,
) -> list[HorizonSignal]:
    direction = outlook.direction if outlook else None
    short = HorizonSignal(
        horizon="next_close",
        signal=direction.lean if direction else "unavailable",
        method="Logistic regression: next completed daily close, not opening price.",
        confidence=direction.validation_status if direction else "insufficient_data",
        evidence=[
            f"Up probability: {direction.up_probability_pct}%; validation accuracy edge: {direction.accuracy_edge_pct_points} percentage points."
        ]
        if direction
        else [],
        invalidation_basis="Re-evaluate with the next completed session; no guaranteed direction.",
    )
    rsi = analysis.entry_context.rsi_14 if analysis else None
    medium = HorizonSignal(
        horizon="weeks_to_months",
        signal=analysis.trend if analysis else "unavailable",
        method="Price relative to 20/50-day averages, with RSI momentum context. Descriptive technical rules, not a trained multi-week forecast.",
        confidence="unvalidated_heuristic" if analysis else "insufficient_data",
        evidence=(
            [
                f"20-day average: {analysis.moving_average_20}; 50-day average: {analysis.moving_average_50}.",
                f"RSI14: {rsi}; historical maximum drawdown: {analysis.max_drawdown_pct}%.",
            ]
            if analysis
            else []
        ),
        invalidation_basis="ATR/price-based invalidation belongs to the technical setup only.",
    )
    scores = fundamentals.financial_quality if fundamentals else None
    quality = scores.quality.score if scores else None
    growth = scores.growth.score if scores else None
    valuation = fundamentals.valuation.profile if fundamentals else "insufficient_data"
    signal = "insufficient_data"
    if quality is not None and growth is not None and valuation != "insufficient_data":
        if (
            quality >= 65
            and growth >= 60
            and valuation in {"lower_multiple", "balanced"}
        ):
            signal = "favorable_fundamentals"
        elif quality < 40 or growth < 35 or valuation == "unprofitable":
            signal = "caution"
        else:
            signal = "mixed"
    long_term = HorizonSignal(
        horizon="years",
        signal=signal,
        method="Favorable requires quality >=65, growth >=60 and non-premium valuation; caution if quality <40, growth <35 or unprofitable; otherwise mixed.",
        confidence="unvalidated_heuristic"
        if signal != "insufficient_data"
        else "insufficient_data",
        evidence=[f"Quality: {quality}; growth: {growth}; valuation: {valuation}."]
        if fundamentals
        else [],
        invalidation_basis="Review sustained deterioration in cash generation, growth, leverage and valuation at new filings. A 50-day low is not a long-term thesis stop. No intrinsic-value entry price has been calculated.",
    )
    additional = (
        [
            HorizonSignal(
                horizon=f"{model.horizon_sessions}_sessions",
                signal=model.lean,
                method=f"Separate logistic regression target: {model.horizon}. Walk-forward validation purges {model.horizon_sessions} rows between training and validation.",
                confidence=model.validation_status,
                evidence=[
                    f"Up probability: {model.up_probability_pct}%; accuracy edge: {model.accuracy_edge_pct_points} percentage points."
                ],
                invalidation_basis="Experimental forecast of the close relative to the snapshot close, not intraday path or a guaranteed trade.",
            )
            for model in outlook.additional_horizons
        ]
        if outlook
        else []
    )
    return [short, *additional, medium, long_term]
