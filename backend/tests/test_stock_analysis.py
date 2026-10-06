from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.schema.stock_history import StockHistoryBarResponse, StockHistoryResponse
from app.api.services import stock_analysis_services
from app.api.services.stock_analysis_services import (
    StockAnalysisError,
    _classify_risk,
    build_stock_analysis,
)
from app.main import create_app


def make_history(
    symbol: str,
    closes: list[float],
    *,
    warnings: list[str] | None = None,
) -> StockHistoryResponse:
    start_date = date(2026, 1, 2)

    return StockHistoryResponse(
        symbol=symbol,
        provider="alpaca",
        timeframe="1Day",
        adjusted=True,
        requested_bar_count=len(closes),
        warnings=warnings or [],
        bars=[
            StockHistoryBarResponse(
                timestamp=(start_date + timedelta(days=index)).isoformat(),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1_000_000,
                source="Alpaca (IEX, adjusted)",
            )
            for index, close in enumerate(closes)
        ],
    )


def test_stock_analysis_endpoint_returns_versioned_adjusted_statistics(
    monkeypatch,
) -> None:
    closes = [100.0 + index for index in range(60)]

    def fake_get_stock_history(
        symbol: str,
        provider: str,
        timeframe: str,
        limit: int,
    ) -> StockHistoryResponse:
        assert symbol == "NVDA"
        assert provider == "alpaca"
        assert timeframe == "1Day"
        assert limit == 60

        return make_history("NVDA", closes)

    monkeypatch.setattr(
        stock_analysis_services,
        "get_stock_history",
        fake_get_stock_history,
    )
    monkeypatch.setattr(
        stock_analysis_services,
        "_utc_timestamp",
        lambda: "2026-09-20T01:00:00Z",
    )
    client = TestClient(create_app())

    response = client.get("/stocks/nvda/analysis", params={"limit": 60})

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_version"] == "2.2.0"
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "alpaca"
    assert payload["timeframe"] == "1Day"
    assert payload["mode"] == "historical"
    assert payload["as_of"] == "2026-09-20T01:00:00Z"
    assert payload["data_through"] == "2026-03-02"
    assert payload["adjusted"] is True
    assert payload["bar_count"] == 60
    assert payload["sample_sufficient"] is True
    assert payload["trend_sample_sufficient"] is True
    assert payload["first_close"] == 100.0
    assert payload["latest_close"] == 159.0
    assert payload["period_return_pct"] == 59.0
    assert payload["annualized_volatility_pct"] is not None
    assert payload["moving_average_20"] == 149.5
    assert payload["moving_average_50"] == 134.5
    assert payload["max_drawdown_pct"] == 0.0
    assert payload["trend"] == "uptrend"
    assert payload["risk_level"] == "low"
    assert payload["entry_context"]["atr_14"] == 1.0
    assert payload["entry_context"]["rsi_14"] == 100.0
    assert len(payload["entry_context"]["zones"]) == 2
    assert payload["entry_context"]["zones"][0]["label"] == (
        "Near-term pullback zone"
    )
    assert payload["entry_context"]["plan"]["signal"] == "wait_for_pullback"
    assert any("may be noisy" in warning for warning in payload["warnings"])


def test_stock_analysis_returns_insufficient_data_instead_of_false_low_risk(
    monkeypatch,
) -> None:
    def fake_get_stock_history(
        symbol: str,
        provider: str,
        timeframe: str,
        limit: int,
    ) -> StockHistoryResponse:
        return make_history("NEW", [100.0 + index for index in range(20)])

    monkeypatch.setattr(
        stock_analysis_services,
        "get_stock_history",
        fake_get_stock_history,
    )
    client = TestClient(create_app())

    response = client.get("/stocks/NEW/analysis", params={"limit": 30})

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_sufficient"] is False
    assert payload["trend_sample_sufficient"] is False
    assert payload["annualized_volatility_pct"] is None
    assert payload["risk_level"] == "insufficient_data"
    assert payload["trend"] == "insufficient_data"
    assert payload["entry_context"]["position"] == "insufficient_data"
    assert len(payload["entry_context"]["zones"]) == 1
    assert payload["entry_context"]["zones"][0]["label"] == (
        "Near-term pullback zone"
    )


def test_stock_analysis_calculates_known_return_and_drawdown() -> None:
    history = make_history("TEST", [100.0, 120.0, 90.0])

    analysis = build_stock_analysis(
        history,
        "historical",
        as_of="2026-09-20T01:00:00Z",
    )

    assert analysis.period_return_pct == -10.0
    assert analysis.max_drawdown_pct == -25.0
    assert analysis.annualized_volatility_pct is None
    assert analysis.risk_level == "insufficient_data"


def test_stock_analysis_rejects_a_single_bar() -> None:
    history = make_history("TEST", [100.0])

    with pytest.raises(
        StockAnalysisError,
        match="At least two historical bars are required",
    ):
        build_stock_analysis(history, "historical")


def test_stock_analysis_calculates_moving_averages_and_uptrend() -> None:
    history = make_history("NVDA", [float(close) for close in range(1, 61)])

    analysis = build_stock_analysis(
        history,
        "historical",
        as_of="2026-09-20T01:00:00Z",
    )

    assert analysis.moving_average_20 == 50.5
    assert analysis.moving_average_50 == 35.5
    assert analysis.trend == "uptrend"


def test_entry_context_uses_atr_rsi_and_moving_average_zones() -> None:
    closes = [100.0 + (index * 0.5) for index in range(60)]
    history = make_history("NVDA", closes)

    for bar in history.bars:
        bar.high = bar.close + 2.0
        bar.low = bar.close - 2.0

    analysis = build_stock_analysis(
        history,
        "historical",
        as_of="2026-09-20T01:00:00Z",
    )

    entry = analysis.entry_context
    assert entry.atr_14 == 4.0
    assert entry.rsi_14 == 100.0
    assert entry.recent_low_20 == 118.0
    assert entry.recent_high_20 == 131.5
    assert entry.zones[0].lower_price == analysis.moving_average_20 - 2.0
    assert entry.zones[0].upper_price == analysis.moving_average_20 + 1.0
    assert entry.position == "above_near_term_zone"
    assert entry.plan.signal == "wait_for_pullback"
    assert entry.plan.preferred_entry_lower == entry.zones[0].lower_price
    assert entry.plan.patient_entry_lower == entry.zones[1].lower_price
    assert entry.plan.upside_reference_price == 131.5
    assert entry.plan.invalidation_price == 101.0
    assert entry.plan.estimated_reward_risk_ratio == 0.3118


def test_risk_threshold_boundaries_are_inclusive() -> None:
    assert _classify_risk(40.0, 0.0) == "high"
    assert _classify_risk(20.0, 0.0) == "medium"
    assert _classify_risk(19.9999, -9.9999) == "low"
    assert _classify_risk(None, -50.0) == "insufficient_data"
