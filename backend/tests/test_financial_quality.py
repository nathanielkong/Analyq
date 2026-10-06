from datetime import datetime, timezone

import pytest
from test_stock_fundamentals import make_balance_sheet, make_cash_flow, make_overview

from app.api.schema.financial_quality import AnnualFinancials
from app.api.services.financial_quality_services import (
    align_annual_statements,
    build_financial_quality,
    cagr,
)
from app.api.services.peer_comparison_services import compare_fundamentals
from app.api.services.stock_fundamentals_services import build_stock_fundamentals
from app.clients.alpha_vantage import AlphaVantageClient
from app.clients.errors import MarketDataRateLimitError


def annual_rows():
    return [
        AnnualFinancials(
            fiscal_date=f"{year}-12-31",
            currency="USD",
            revenue=100 * 1.1**index,
            eps=2 * 1.1**index,
            net_income=20,
            free_cash_flow=15,
            gross_margin_pct=50,
            operating_margin_pct=15 + index,
            net_margin_pct=20,
            roe_pct=20,
            roa_pct=10,
            debt_equity=0.5,
            current_ratio=2,
            fcf_margin_pct=15,
            cash_conversion=1.2,
            total_debt=30,
            cash=20 + index,
        )
        for index, year in enumerate(range(2020, 2026))
    ]


def test_quality_growth_are_transparent_and_unvalidated():
    result = build_financial_quality(annual_rows(), "Technology")
    assert result.years_available == 6
    assert result.revenue_cagr_3y_pct == pytest.approx(10, abs=0.02)
    assert result.revenue_cagr_5y_pct == pytest.approx(10, abs=0.02)
    assert result.quality.score == pytest.approx(93.8)
    assert result.growth.score == pytest.approx(67.5, abs=0.1)
    assert result.net_debt_change == -2
    assert result.moat_label == "supportive_proxies"
    assert result.quality.validation_status == "unvalidated_heuristic"
    assert sum(part.weight for part in result.quality.components) == 1


def test_missing_cash_flow_does_not_become_zero_or_shift_weights():
    rows = annual_rows()
    rows[-1].cash_conversion = None
    result = build_financial_quality(rows, "Technology")
    assert result.quality.score is None
    assert result.quality.coverage_pct == 75


@pytest.mark.parametrize("sector", ["Financial Services", "REAL ESTATE"])
def test_nonindustrial_sectors_are_not_scored(sector):
    result = build_financial_quality(annual_rows(), sector)
    assert result.quality.score is None
    assert result.growth.score is None
    assert result.moat_label == "insufficient_evidence"


def test_cagr_rejects_negative_eps_missing_years_and_currency_changes():
    rows = annual_rows()
    rows[-4].eps = -1
    assert cagr(rows, "eps", 3) is None
    rows[-2].currency = "EUR"
    assert cagr(rows, "revenue", 3) is None
    assert cagr(annual_rows()[::2], "revenue", 2) is None
    assert build_financial_quality([], None).quality.score is None


def test_align_statements_by_exact_date_not_position_and_ignore_bad_numbers():
    statements = {
        "INCOME_STATEMENT": [
            {
                "fiscalDateEnding": "2025-12-31",
                "reportedCurrency": "USD",
                "totalRevenue": "100",
                "grossProfit": "60",
                "netIncome": "10",
            },
            {
                "fiscalDateEnding": "2024-12-31",
                "reportedCurrency": "USD",
                "totalRevenue": "nan",
            },
            {"fiscalDateEnding": "invalid"},
        ],
        "CASH_FLOW": [
            {
                "fiscalDateEnding": "2025-12-31",
                "reportedCurrency": "USD",
                "operatingCashflow": "20",
                "capitalExpenditures": "-5",
            }
        ],
        "BALANCE_SHEET": [
            {
                "fiscalDateEnding": "2025-12-31",
                "reportedCurrency": "EUR",
                "totalAssets": "1000",
            }
        ],
    }
    rows = align_annual_statements(statements)
    assert len(rows) == 2
    assert rows[0].revenue is None
    assert rows[0].free_cash_flow is None
    assert rows[1].free_cash_flow == 15
    assert rows[1].fcf_margin_pct == 15
    assert rows[1].total_assets is None
    assert rows[1].gross_margin_pct == 60


def test_statement_client_reuses_balance_and_cash_payloads(monkeypatch):
    client = AlphaVantageClient()
    calls = []

    def fetch(params):
        calls.append(params["function"])
        return {"annualReports": [], "quarterlyReports": []}

    monkeypatch.setattr(client, "_get_json", fetch)
    client.get_latest_balance_sheet("TEST")
    client.get_latest_annual_cash_flow("TEST")
    client.get_annual_statements("TEST")
    assert calls.count("BALANCE_SHEET") == 1
    assert calls.count("CASH_FLOW") == 1
    assert set(calls) == {"BALANCE_SHEET", "CASH_FLOW", "INCOME_STATEMENT", "EARNINGS"}


def test_annual_collection_stops_on_quota_error(monkeypatch):
    client = AlphaVantageClient()
    calls = []

    def fetch(params):
        calls.append(params)
        raise MarketDataRateLimitError("quota")

    monkeypatch.setattr(client, "_get_json", fetch)
    statements, warnings = client.get_annual_statements("TEST")
    assert len(calls) == 1
    assert statements == {}
    assert warnings


def test_peer_scores_exclude_incomplete_and_nonpositive_growth():
    stock = build_stock_fundamentals(
        make_overview(),
        make_balance_sheet(),
        make_cash_flow(),
        datetime.now(timezone.utc),
    )
    stock.financial_quality = build_financial_quality(annual_rows(), "Technology")
    missing = stock.model_copy(deep=True)
    missing.symbol = "MISSING"
    missing.financial_quality = None
    missing.profitability_growth.quarterly_revenue_growth_yoy_pct = -5
    result = compare_fundamentals([missing, stock], "growth")
    assert result.weights["growth"] == 0.6
    assert result.rows[0].rank == 1
    assert result.rows[1].rank is None
    assert result.rows[1].weighted_score is None
    assert result.rows[1].sales_growth_multiple is None
    assert result.rows[0].price_sales_forward is None
    assert result.rows[0].price_fcf_annual == pytest.approx(6.67)
