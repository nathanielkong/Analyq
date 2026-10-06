from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.routes import stocks as stock_routes
from app.api.services.stock_fundamentals_services import build_stock_fundamentals
from app.clients import alpha_vantage
from app.clients.alpha_vantage import (
    AlphaVantageBalanceSheetSnapshot,
    AlphaVantageCashFlowSnapshot,
    AlphaVantageClient,
    AlphaVantageCompanyOverview,
)
from app.main import create_app


def make_overview() -> AlphaVantageCompanyOverview:
    return AlphaVantageCompanyOverview(
        symbol="TEST",
        asset_type="Common Stock",
        name="Test Corporation",
        description="A test company.",
        exchange="NASDAQ",
        currency="USD",
        country="USA",
        sector="Technology",
        industry="Software",
        fiscal_year_end="December",
        latest_quarter="2026-06-30",
        market_capitalization=100_000_000_000,
        ebitda=25_000_000_000,
        pe_ratio=15.0,
        trailing_pe=15.0,
        forward_pe=18.0,
        peg_ratio=1.2,
        price_to_sales_ttm=2.0,
        price_to_book=3.0,
        ev_to_revenue=2.5,
        ev_to_ebitda=10.0,
        eps=8.0,
        diluted_eps_ttm=7.5,
        dividend_yield=0.012,
        profit_margin=0.2,
        operating_margin_ttm=0.25,
        return_on_assets_ttm=0.12,
        return_on_equity_ttm=0.24,
        revenue_ttm=75_000_000_000,
        gross_profit_ttm=45_000_000_000,
        quarterly_earnings_growth_yoy=0.3,
        quarterly_revenue_growth_yoy=0.18,
        analyst_target_price=150.0,
        beta=1.1,
        high_52_week=145.0,
        low_52_week=85.0,
    )


def make_balance_sheet() -> AlphaVantageBalanceSheetSnapshot:
    return AlphaVantageBalanceSheetSnapshot(
        fiscal_date_ending="2026-06-30",
        reported_currency="USD",
        total_assets=180_000_000_000,
        total_current_assets=80_000_000_000,
        cash_and_short_term_investments=20_000_000_000,
        total_current_liabilities=40_000_000_000,
        total_liabilities=100_000_000_000,
        short_term_debt=5_000_000_000,
        long_term_debt=35_000_000_000,
        long_term_debt_noncurrent=30_000_000_000,
        total_shareholder_equity=50_000_000_000,
    )


def make_cash_flow() -> AlphaVantageCashFlowSnapshot:
    return AlphaVantageCashFlowSnapshot(
        fiscal_date_ending="2025-12-31",
        reported_currency="USD",
        operating_cash_flow=20_000_000_000,
        capital_expenditures=5_000_000_000,
        dividend_payout=2_000_000_000,
        share_repurchases=3_000_000_000,
    )


def test_alpha_vantage_parses_fundamental_endpoints(monkeypatch) -> None:
    client = AlphaVantageClient()
    requested_functions: list[str] = []

    def fake_get_json(params: dict[str, str]) -> dict:
        requested_functions.append(params["function"])

        if params["function"] == "OVERVIEW":
            return {
                "Symbol": "TEST",
                "AssetType": "Common Stock",
                "Name": "Test Corporation",
                "Sector": "TECHNOLOGY",
                "MarketCapitalization": "100000000000",
                "TrailingPE": "15.0",
                "ForwardPE": "18.0",
                "PEGRatio": "1.2",
                "ProfitMargin": "0.2",
                "QuarterlyRevenueGrowthYOY": "0.18",
            }

        if params["function"] == "BALANCE_SHEET":
            return {
                "quarterlyReports": [
                    {
                        "fiscalDateEnding": "2026-06-30",
                        "reportedCurrency": "USD",
                        "cashAndShortTermInvestments": "20000000000",
                        "shortTermDebt": "5000000000",
                        "longTermDebtNoncurrent": "30000000000",
                    }
                ]
            }

        return {
            "annualReports": [
                {
                    "fiscalDateEnding": "2025-12-31",
                    "reportedCurrency": "USD",
                    "operatingCashflow": "20000000000",
                    "capitalExpenditures": "5000000000",
                }
            ]
        }

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    overview = client.get_company_overview("test")
    balance = client.get_latest_balance_sheet("test")
    cash_flow = client.get_latest_annual_cash_flow("test")

    assert requested_functions == ["OVERVIEW", "BALANCE_SHEET", "CASH_FLOW"]
    assert overview.trailing_pe == 15.0
    assert overview.profit_margin == 0.2
    assert balance is not None
    assert balance.cash_and_short_term_investments == 20_000_000_000
    assert cash_flow is not None
    assert cash_flow.operating_cash_flow == 20_000_000_000


def test_alpha_vantage_paces_provider_requests(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"{}"

    clock_values = iter([10.25, 10.25])
    sleep_calls: list[float] = []
    monkeypatch.setattr(alpha_vantage.settings, "market_data_api_key", "test-key")
    monkeypatch.setattr(alpha_vantage, "monotonic", lambda: next(clock_values))
    monkeypatch.setattr(alpha_vantage, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        alpha_vantage,
        "urlopen",
        lambda request, timeout: FakeResponse(),
    )
    monkeypatch.setattr(AlphaVantageClient, "_last_request_started_at", 10.0)

    payload = AlphaVantageClient()._get_json({"function": "OVERVIEW"})

    assert payload == {}
    assert sleep_calls == [pytest.approx(1.25)]


def test_fundamentals_service_builds_valuation_cash_flow_and_debt_metrics() -> None:
    response = build_stock_fundamentals(
        overview=make_overview(),
        balance_sheet=make_balance_sheet(),
        cash_flow=make_cash_flow(),
        fetched_at=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
    )

    assert response.valuation.profile == "lower_multiple"
    assert response.valuation.score == 6
    assert response.valuation.metric_count == 6
    assert response.valuation.free_cash_flow_yield_pct == 15.0
    assert response.valuation.dividend_yield_pct == 1.2
    assert response.profitability_growth.profit_margin_pct == 20.0
    assert response.profitability_growth.annual_free_cash_flow == 15_000_000_000
    assert response.profitability_growth.free_cash_flow_margin_pct == 20.0
    assert response.financial_health.total_debt == 35_000_000_000
    assert response.financial_health.net_debt == 15_000_000_000
    assert response.financial_health.current_ratio == 2.0
    assert response.financial_health.debt_to_equity == 0.7


def test_fundamentals_endpoint_returns_typed_response(monkeypatch) -> None:
    expected = build_stock_fundamentals(
        overview=make_overview(),
        balance_sheet=make_balance_sheet(),
        cash_flow=make_cash_flow(),
        fetched_at=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        stock_routes,
        "get_stock_fundamentals",
        lambda symbol: expected,
    )
    client = TestClient(create_app())

    response = client.get("/stocks/TEST/fundamentals")

    assert response.status_code == 200
    payload = response.json()
    assert payload["valuation"]["profile"] == "lower_multiple"
    assert payload["financial_health"]["current_ratio"] == 2.0
