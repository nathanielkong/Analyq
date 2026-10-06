from datetime import datetime, timezone

from app.api.schema.stock_fundamentals import (
    CompanyProfileResponse,
    StockFinancialHealthResponse,
    StockFundamentalsResponse,
    StockMarketContextResponse,
    StockProfitabilityGrowthResponse,
    StockValuationResponse,
    ValuationProfile,
)
from app.api.services.stock_history_services import normalize_stock_symbol
from app.api.services.ttl_cache import TTLCache
from app.core.report_policy import report_day
from app.clients.alpha_vantage import (
    AlphaVantageBalanceSheetSnapshot,
    AlphaVantageCashFlowSnapshot,
    AlphaVantageClient,
    AlphaVantageCompanyOverview,
)
from app.clients.errors import MarketDataError
from app.api.services.financial_quality_services import (
    align_annual_statements,
    build_financial_quality,
)


FUNDAMENTALS_VERSION = "1.0.0"
FUNDAMENTALS_CACHE_TTL_SECONDS = 86_400
_fundamentals_cache: TTLCache[str, StockFundamentalsResponse] = TTLCache(
    ttl_seconds=FUNDAMENTALS_CACHE_TTL_SECONDS
)


def get_stock_fundamentals(
    symbol: str,
    client: AlphaVantageClient | None = None,
    fetched_at: datetime | None = None,
) -> StockFundamentalsResponse:
    normalized_symbol = normalize_stock_symbol(symbol)
    cache_key = f"{normalized_symbol}:{report_day()}"
    cached_response = _fundamentals_cache.get(cache_key)

    if cached_response is not None and client is None and fetched_at is None:
        return cached_response

    provider = client or AlphaVantageClient()
    overview = provider.get_company_overview(normalized_symbol)
    warnings: list[str] = []
    balance_sheet: AlphaVantageBalanceSheetSnapshot | None = None
    cash_flow: AlphaVantageCashFlowSnapshot | None = None

    try:
        balance_sheet = provider.get_latest_balance_sheet(normalized_symbol)
    except MarketDataError as error:
        warnings.append(f"Balance-sheet data is unavailable: {error}")

    try:
        cash_flow = provider.get_latest_annual_cash_flow(normalized_symbol)
    except MarketDataError as error:
        warnings.append(f"Cash-flow data is unavailable: {error}")

    response = build_stock_fundamentals(
        overview=overview,
        balance_sheet=balance_sheet,
        cash_flow=cash_flow,
        fetched_at=fetched_at or datetime.now(timezone.utc),
        provider_warnings=warnings,
    )
    statements, statement_warnings = provider.get_annual_statements(normalized_symbol)
    response.annual_financials = align_annual_statements(statements)
    response.financial_quality = build_financial_quality(
        response.annual_financials, response.company.sector
    )
    response.warnings.extend(statement_warnings)
    # Use aligned annual revenue rather than dividing annual FCF by TTM revenue.
    annual = next(
        (
            row
            for row in response.annual_financials
            if row.fiscal_date == response.profitability_growth.cash_flow_period_end
        ),
        None,
    )
    response.profitability_growth.free_cash_flow_margin_pct = (
        annual.fcf_margin_pct if annual else None
    )

    if (
        client is None
        and fetched_at is None
        and not warnings
        and not statement_warnings
    ):
        _fundamentals_cache.set(cache_key, response)

    return response


def build_stock_fundamentals(
    overview: AlphaVantageCompanyOverview,
    balance_sheet: AlphaVantageBalanceSheetSnapshot | None,
    cash_flow: AlphaVantageCashFlowSnapshot | None,
    fetched_at: datetime,
    provider_warnings: list[str] | None = None,
) -> StockFundamentalsResponse:
    annual_free_cash_flow = _free_cash_flow(cash_flow)
    free_cash_flow_yield_pct = _percentage_ratio(
        annual_free_cash_flow,
        overview.market_capitalization,
    )
    free_cash_flow_margin_pct = _percentage_ratio(
        annual_free_cash_flow,
        overview.revenue_ttm,
    )
    total_debt = _total_debt(balance_sheet)
    cash = (
        balance_sheet.cash_and_short_term_investments
        if balance_sheet is not None
        else None
    )
    net_debt = (
        total_debt - cash if total_debt is not None and cash is not None else None
    )
    current_ratio = _ratio(
        balance_sheet.total_current_assets if balance_sheet else None,
        balance_sheet.total_current_liabilities if balance_sheet else None,
    )
    debt_to_equity = _ratio(
        total_debt,
        balance_sheet.total_shareholder_equity if balance_sheet else None,
    )
    valuation = _build_valuation(
        overview=overview,
        free_cash_flow_yield_pct=free_cash_flow_yield_pct,
    )
    warnings = list(provider_warnings or [])

    warnings.extend(
        [
            (
                "The valuation profile uses broad absolute thresholds and is not "
                "adjusted for the company's sector, growth durability, or accounting quality."
            ),
            (
                "Analyst targets are third-party opinions, not guaranteed fair values or "
                "future prices."
            ),
        ]
    )

    if balance_sheet is None:
        warnings.append(
            "No quarterly balance sheet was available, so liquidity and debt ratios are missing."
        )

    if cash_flow is None:
        warnings.append(
            "No annual cash-flow statement was available, so free-cash-flow metrics are missing."
        )
    else:
        warnings.append(
            "Free cash flow is calculated as annual operating cash flow minus the absolute "
            "value of annual capital expenditure."
        )

    return StockFundamentalsResponse(
        fundamentals_version=FUNDAMENTALS_VERSION,
        symbol=overview.symbol,
        provider="Alpha Vantage",
        fetched_at=_iso_timestamp(fetched_at),
        latest_quarter=overview.latest_quarter,
        company=CompanyProfileResponse(
            name=overview.name,
            asset_type=overview.asset_type,
            exchange=overview.exchange,
            currency=overview.currency,
            country=overview.country,
            sector=overview.sector,
            industry=overview.industry,
            fiscal_year_end=overview.fiscal_year_end,
            description=overview.description,
        ),
        valuation=valuation,
        profitability_growth=StockProfitabilityGrowthResponse(
            revenue_ttm=overview.revenue_ttm,
            gross_profit_ttm=overview.gross_profit_ttm,
            ebitda=overview.ebitda,
            eps=_round_optional(overview.eps),
            diluted_eps_ttm=_round_optional(overview.diluted_eps_ttm),
            profit_margin_pct=_as_percent(overview.profit_margin),
            operating_margin_pct=_as_percent(overview.operating_margin_ttm),
            return_on_assets_pct=_as_percent(overview.return_on_assets_ttm),
            return_on_equity_pct=_as_percent(overview.return_on_equity_ttm),
            quarterly_revenue_growth_yoy_pct=_as_percent(
                overview.quarterly_revenue_growth_yoy
            ),
            quarterly_earnings_growth_yoy_pct=_as_percent(
                overview.quarterly_earnings_growth_yoy
            ),
            annual_operating_cash_flow=(
                cash_flow.operating_cash_flow if cash_flow else None
            ),
            annual_capital_expenditures=(
                cash_flow.capital_expenditures if cash_flow else None
            ),
            annual_free_cash_flow=annual_free_cash_flow,
            free_cash_flow_margin_pct=_round_optional(free_cash_flow_margin_pct),
            cash_flow_period_end=(cash_flow.fiscal_date_ending if cash_flow else None),
        ),
        financial_health=StockFinancialHealthResponse(
            balance_sheet_period_end=(
                balance_sheet.fiscal_date_ending if balance_sheet else None
            ),
            total_assets=balance_sheet.total_assets if balance_sheet else None,
            total_current_assets=(
                balance_sheet.total_current_assets if balance_sheet else None
            ),
            total_current_liabilities=(
                balance_sheet.total_current_liabilities if balance_sheet else None
            ),
            total_liabilities=(
                balance_sheet.total_liabilities if balance_sheet else None
            ),
            cash_and_short_term_investments=cash,
            total_debt=total_debt,
            net_debt=net_debt,
            total_shareholder_equity=(
                balance_sheet.total_shareholder_equity if balance_sheet else None
            ),
            current_ratio=_round_optional(current_ratio),
            debt_to_equity=_round_optional(debt_to_equity),
        ),
        market_context=StockMarketContextResponse(
            beta=_round_optional(overview.beta),
            high_52_week=_round_optional(overview.high_52_week),
            low_52_week=_round_optional(overview.low_52_week),
        ),
        highlights=_build_highlights(
            overview=overview,
            annual_free_cash_flow=annual_free_cash_flow,
            total_debt=total_debt,
            net_debt=net_debt,
        ),
        warnings=warnings,
    )


def _build_valuation(
    overview: AlphaVantageCompanyOverview,
    free_cash_flow_yield_pct: float | None,
) -> StockValuationResponse:
    trailing_pe = _positive_value(overview.trailing_pe) or _positive_value(
        overview.pe_ratio
    )
    forward_pe = _positive_value(overview.forward_pe)
    peg_ratio = _positive_value(overview.peg_ratio)
    price_to_sales = _positive_value(overview.price_to_sales_ttm)
    price_to_book = _positive_value(overview.price_to_book)
    ev_to_ebitda = _positive_value(overview.ev_to_ebitda)
    score = 0
    metric_count = 0
    reasons: list[str] = []

    score, metric_count = _score_lower_multiple(
        label="Trailing P/E",
        value=trailing_pe,
        lower_threshold=20,
        upper_threshold=35,
        score=score,
        metric_count=metric_count,
        reasons=reasons,
    )
    score, metric_count = _score_lower_multiple(
        label="Forward P/E",
        value=forward_pe,
        lower_threshold=20,
        upper_threshold=35,
        score=score,
        metric_count=metric_count,
        reasons=reasons,
    )
    score, metric_count = _score_lower_multiple(
        label="PEG",
        value=peg_ratio,
        lower_threshold=1.5,
        upper_threshold=2.5,
        score=score,
        metric_count=metric_count,
        reasons=reasons,
    )
    score, metric_count = _score_lower_multiple(
        label="Price-to-sales",
        value=price_to_sales,
        lower_threshold=3,
        upper_threshold=10,
        score=score,
        metric_count=metric_count,
        reasons=reasons,
    )
    score, metric_count = _score_lower_multiple(
        label="EV/EBITDA",
        value=ev_to_ebitda,
        lower_threshold=15,
        upper_threshold=25,
        score=score,
        metric_count=metric_count,
        reasons=reasons,
    )
    score, metric_count = _score_higher_yield(
        value=free_cash_flow_yield_pct,
        score=score,
        metric_count=metric_count,
        reasons=reasons,
    )
    profile = _valuation_profile(
        eps=overview.diluted_eps_ttm or overview.eps,
        score=score,
        metric_count=metric_count,
    )

    if profile == "unprofitable":
        reasons.insert(
            0,
            "Trailing earnings are not positive, so earnings multiples are not a reliable valuation anchor.",
        )

    return StockValuationResponse(
        profile=profile,
        score=score,
        metric_count=metric_count,
        market_capitalization=overview.market_capitalization,
        trailing_pe=_round_optional(trailing_pe),
        forward_pe=_round_optional(forward_pe),
        peg_ratio=_round_optional(peg_ratio),
        price_to_sales_ttm=_round_optional(price_to_sales),
        price_to_book=_round_optional(price_to_book),
        ev_to_revenue=_round_optional(overview.ev_to_revenue),
        ev_to_ebitda=_round_optional(ev_to_ebitda),
        free_cash_flow_yield_pct=_round_optional(free_cash_flow_yield_pct),
        dividend_yield_pct=_as_percent(overview.dividend_yield),
        analyst_target_price=_round_optional(overview.analyst_target_price),
        reasons=reasons,
    )


def _score_lower_multiple(
    *,
    label: str,
    value: float | None,
    lower_threshold: float,
    upper_threshold: float,
    score: int,
    metric_count: int,
    reasons: list[str],
) -> tuple[int, int]:
    if value is None:
        return score, metric_count

    metric_count += 1

    if value <= lower_threshold:
        score += 1
        position = "below the broad lower-multiple threshold"
    elif value >= upper_threshold:
        score -= 1
        position = "above the broad premium-multiple threshold"
    else:
        position = "inside the broad neutral range"

    reasons.append(f"{label} is {value:.2f}, {position}.")
    return score, metric_count


def _score_higher_yield(
    *,
    value: float | None,
    score: int,
    metric_count: int,
    reasons: list[str],
) -> tuple[int, int]:
    if value is None:
        return score, metric_count

    metric_count += 1

    if value >= 5:
        score += 1
        position = "above the broad 5% cash-yield reference"
    elif value <= 2:
        score -= 1
        position = "below the broad 2% cash-yield reference"
    else:
        position = "between the broad 2% and 5% references"

    reasons.append(f"Free-cash-flow yield is {value:.2f}%, {position}.")
    return score, metric_count


def _valuation_profile(
    eps: float | None,
    score: int,
    metric_count: int,
) -> ValuationProfile:
    if eps is not None and eps <= 0:
        return "unprofitable"

    if metric_count < 2:
        return "insufficient_data"

    if score >= 2:
        return "lower_multiple"

    if score <= -2:
        return "premium_multiple"

    return "balanced"


def _build_highlights(
    overview: AlphaVantageCompanyOverview,
    annual_free_cash_flow: int | None,
    total_debt: int | None,
    net_debt: int | None,
) -> list[str]:
    highlights: list[str] = []

    if overview.profit_margin is not None:
        highlights.append(
            f"Trailing profit margin is {_as_percent(overview.profit_margin):.2f}%."
        )

    if overview.quarterly_revenue_growth_yoy is not None:
        highlights.append(
            "Latest reported quarterly revenue growth is "
            f"{_as_percent(overview.quarterly_revenue_growth_yoy):.2f}% year over year."
        )

    if overview.quarterly_earnings_growth_yoy is not None:
        highlights.append(
            "Latest reported quarterly earnings growth is "
            f"{_as_percent(overview.quarterly_earnings_growth_yoy):.2f}% year over year."
        )

    if annual_free_cash_flow is not None:
        highlights.append(
            f"Latest annual free cash flow is {annual_free_cash_flow:,} in reported currency."
        )

    if total_debt is not None and net_debt is not None:
        highlights.append(
            f"Reported debt is {total_debt:,}; net debt after cash is {net_debt:,}."
        )

    return highlights


def _free_cash_flow(cash_flow: AlphaVantageCashFlowSnapshot | None) -> int | None:
    if cash_flow is None or cash_flow.operating_cash_flow is None:
        return None

    if cash_flow.capital_expenditures is None:
        return None

    return cash_flow.operating_cash_flow - abs(cash_flow.capital_expenditures)


def _total_debt(
    balance_sheet: AlphaVantageBalanceSheetSnapshot | None,
) -> int | None:
    if balance_sheet is None:
        return None

    if balance_sheet.long_term_debt_noncurrent is not None:
        return balance_sheet.long_term_debt_noncurrent + (
            balance_sheet.short_term_debt or 0
        )

    if balance_sheet.long_term_debt is not None:
        return balance_sheet.long_term_debt

    return balance_sheet.short_term_debt


def _ratio(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None

    return numerator / denominator


def _percentage_ratio(
    numerator: int | None,
    denominator: int | None,
) -> float | None:
    ratio = _ratio(numerator, denominator)
    return ratio * 100 if ratio is not None else None


def _as_percent(value: float | None) -> float | None:
    return _round_optional(value * 100) if value is not None else None


def _positive_value(value: float | None) -> float | None:
    return value if value is not None and value > 0 else None


def _round_optional(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _iso_timestamp(value: datetime) -> str:
    normalized = (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
    return normalized.replace(microsecond=0).isoformat().replace("+00:00", "Z")
