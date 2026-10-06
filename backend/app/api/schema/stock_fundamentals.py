from typing import Literal

from pydantic import BaseModel, Field

from app.api.schema.financial_quality import AnnualFinancials, FinancialQualityResponse


ValuationProfile = Literal[
    "lower_multiple",
    "balanced",
    "premium_multiple",
    "unprofitable",
    "insufficient_data",
]


class CompanyProfileResponse(BaseModel):
    name: str | None
    asset_type: str | None
    exchange: str | None
    currency: str | None
    country: str | None
    sector: str | None
    industry: str | None
    fiscal_year_end: str | None
    description: str | None


class StockValuationResponse(BaseModel):
    profile: ValuationProfile
    score: int
    metric_count: int
    market_capitalization: int | None
    trailing_pe: float | None
    forward_pe: float | None
    peg_ratio: float | None
    price_to_sales_ttm: float | None
    price_to_book: float | None
    ev_to_revenue: float | None
    ev_to_ebitda: float | None
    free_cash_flow_yield_pct: float | None
    dividend_yield_pct: float | None
    analyst_target_price: float | None
    reasons: list[str]


class StockProfitabilityGrowthResponse(BaseModel):
    revenue_ttm: int | None
    gross_profit_ttm: int | None
    ebitda: int | None
    eps: float | None
    diluted_eps_ttm: float | None
    profit_margin_pct: float | None
    operating_margin_pct: float | None
    return_on_assets_pct: float | None
    return_on_equity_pct: float | None
    quarterly_revenue_growth_yoy_pct: float | None
    quarterly_earnings_growth_yoy_pct: float | None
    annual_operating_cash_flow: int | None
    annual_capital_expenditures: int | None
    annual_free_cash_flow: int | None
    free_cash_flow_margin_pct: float | None
    cash_flow_period_end: str | None


class StockFinancialHealthResponse(BaseModel):
    balance_sheet_period_end: str | None
    total_assets: int | None
    total_current_assets: int | None
    total_current_liabilities: int | None
    total_liabilities: int | None
    cash_and_short_term_investments: int | None
    total_debt: int | None
    net_debt: int | None
    total_shareholder_equity: int | None
    current_ratio: float | None
    debt_to_equity: float | None


class StockMarketContextResponse(BaseModel):
    beta: float | None
    high_52_week: float | None
    low_52_week: float | None


class StockFundamentalsResponse(BaseModel):
    annual_financials: list[AnnualFinancials] = Field(default_factory=list)
    financial_quality: FinancialQualityResponse | None = None
    fundamentals_version: str
    symbol: str
    provider: str
    fetched_at: str
    latest_quarter: str | None
    company: CompanyProfileResponse
    valuation: StockValuationResponse
    profitability_growth: StockProfitabilityGrowthResponse
    financial_health: StockFinancialHealthResponse
    market_context: StockMarketContextResponse
    highlights: list[str]
    warnings: list[str]
