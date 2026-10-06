from app.api.schema.peer_comparison import (
    PeerComparisonResponse,
    PeerMetrics,
    RankingPreset,
)
from app.api.schema.stock_fundamentals import StockFundamentalsResponse

RANKING_WEIGHTS = {
    "value": {"value": 0.6, "quality": 0.25, "growth": 0.15},
    "growth": {"value": 0.15, "quality": 0.25, "growth": 0.6},
    "quality": {"value": 0.2, "quality": 0.6, "growth": 0.2},
}


def compare_fundamentals(
    items: list[StockFundamentalsResponse], preset: RankingPreset = "quality"
) -> PeerComparisonResponse:
    weights = RANKING_WEIGHTS[preset]
    rows = []
    warnings = [
        "Scores are transparent heuristics, not a validated best-stock or return forecast. Missing score dimensions are excluded from ranking, not treated as zero.",
        "Sales/growth = P/S (TTM) divided by quarterly revenue growth in percentage points (e.g. 20, not 0.20). Nonpositive growth is not ranked by this metric.",
        "Forward P/S is unavailable: forward revenue estimates have not been collected. P/FCF uses the latest annual FCF, not TTM FCF.",
    ]
    for item in items:
        valuation, profit = item.valuation, item.profitability_growth
        scores = item.financial_quality
        quality = scores.quality.score if scores else None
        growth = scores.growth.score if scores else None
        value = (
            round(50 + 50 * valuation.score / valuation.metric_count, 1)
            if valuation.metric_count >= 2
            else None
        )
        rev_growth = profit.quarterly_revenue_growth_yoy_pct
        ps = valuation.price_to_sales_ttm
        # Company overview amounts and market capitalisation must share currency.
        fcf_yield = valuation.free_cash_flow_yield_pct
        gross_margin = (
            profit.gross_profit_ttm / profit.revenue_ttm * 100
            if profit.gross_profit_ttm is not None
            and profit.revenue_ttm is not None
            and profit.revenue_ttm > 0
            else None
        )
        row = PeerMetrics(
            symbol=item.symbol,
            sector=item.company.sector,
            fiscal_date=item.latest_quarter,
            fetched_at=item.fetched_at,
            price_sales_ttm=ps,
            price_fcf_annual=round(100 / fcf_yield, 2)
            if fcf_yield is not None and fcf_yield > 0
            else None,
            ev_ebitda=valuation.ev_to_ebitda,
            gross_margin_pct=round(gross_margin, 2)
            if gross_margin is not None
            else None,
            quarterly_revenue_growth_yoy_pct=rev_growth,
            sales_growth_multiple=round(ps / rev_growth, 4)
            if ps is not None and ps > 0 and rev_growth is not None and rev_growth > 0
            else None,
            quality_score=quality,
            growth_score=growth,
            value_score=value,
        )
        if all(score is not None for score in (quality, growth, value)):
            row.weighted_score = round(
                quality * weights["quality"]
                + growth * weights["growth"]
                + value * weights["value"],
                1,
            )
        rows.append(row)
    if len({item.company.sector for item in items}) > 1:
        warnings.append(
            "These companies span different sectors; broad valuation thresholds and margins are not directly peer-adjusted."
        )
    if len({item.latest_quarter for item in items}) > 1:
        warnings.append(
            "Fiscal reporting periods differ. The table retains each date rather than claiming aligned periods."
        )
    rows.sort(
        key=lambda row: (
            row.weighted_score is None,
            -(row.weighted_score or 0),
            row.symbol,
        )
    )
    previous_score, previous_rank = None, None
    for index, row in enumerate(rows, 1):
        if row.weighted_score is not None:
            row.rank = previous_rank if row.weighted_score == previous_score else index
            previous_score, previous_rank = row.weighted_score, row.rank
    return PeerComparisonResponse(
        preset=preset, weights=weights, rows=rows, warnings=warnings
    )
