from typing import Literal

from pydantic import BaseModel, Field


class AnnualFinancials(BaseModel):
    fiscal_date: str
    currency: str | None = None
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    eps: float | None = None
    operating_cash_flow: float | None = None
    capital_expenditures: float | None = None
    free_cash_flow: float | None = None
    total_assets: float | None = None
    equity: float | None = None
    total_debt: float | None = None
    cash: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    gross_margin_pct: float | None = None
    operating_margin_pct: float | None = None
    net_margin_pct: float | None = None
    fcf_margin_pct: float | None = None
    roe_pct: float | None = None
    roa_pct: float | None = None
    debt_equity: float | None = None
    current_ratio: float | None = None
    cash_conversion: float | None = None


class ScoreComponent(BaseModel):
    name: str
    score: float | None
    weight: float
    method: str


class CompositeScore(BaseModel):
    score: float | None = None
    coverage_pct: float
    components: list[ScoreComponent]
    validation_status: Literal["unvalidated_heuristic"] = "unvalidated_heuristic"


class FinancialQualityResponse(BaseModel):
    version: str = "1.0.0"
    years_available: int
    quality: CompositeScore
    growth: CompositeScore
    revenue_cagr_3y_pct: float | None
    revenue_cagr_5y_pct: float | None
    eps_cagr_3y_pct: float | None
    eps_cagr_5y_pct: float | None
    operating_margin_change_pp: float | None
    net_debt_change: float | None
    positive_revenue_growth_pct: float | None
    gross_margin_std_pp: float | None
    moat_label: Literal["supportive_proxies", "mixed_proxies", "insufficient_evidence"]
    moat_evidence: list[str]
    warnings: list[str] = Field(default_factory=list)
