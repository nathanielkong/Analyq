from fastapi.testclient import TestClient

from app.api.schema.stock import StockQuoteResponse
from app.api.schema.stock_history import StockHistoryBarResponse, StockHistoryResponse
from app.api.services import stock_research_data_services
from app.main import create_app


def make_history(symbol: str) -> StockHistoryResponse:
    return StockHistoryResponse(
        symbol=symbol,
        provider="alpaca",
        timeframe="1Day",
        adjusted=True,
        requested_bar_count=30,
        warnings=[],
        bars=[
            StockHistoryBarResponse(
                timestamp="2026-09-18T04:00:00Z",
                open=100.0,
                high=102.0,
                low=99.0,
                close=101.0,
                volume=1_000_000,
                source="Alpaca (IEX, adjusted)",
            )
        ],
    )


def test_research_data_endpoint_collects_stock_and_benchmark(monkeypatch) -> None:
    requested_history_symbols: list[str] = []

    def fake_get_quote(symbol: str) -> StockQuoteResponse:
        assert symbol == "NVDA"

        return StockQuoteResponse(
            symbol="NVDA",
            company_name="NVIDIA Corp",
            price=180.0,
            currency="USD",
            change=None,
            change_percent=None,
            volume=1_000_000,
            latest_trading_day="2026-09-18T20:00:00Z",
            previous_close=None,
            open=179.0,
            high=181.0,
            low=178.0,
            source="Alpaca (IEX)",
        )

    def fake_get_history(
        symbol: str,
        provider: str,
        timeframe: str,
        limit: int,
    ) -> StockHistoryResponse:
        assert provider == "alpaca"
        assert timeframe == "1Day"
        assert limit == 30
        requested_history_symbols.append(symbol)
        return make_history(symbol)

    monkeypatch.setattr(
        stock_research_data_services,
        "get_stock_quote",
        fake_get_quote,
    )
    monkeypatch.setattr(
        stock_research_data_services,
        "get_stock_history",
        fake_get_history,
    )
    monkeypatch.setattr(
        stock_research_data_services,
        "_utc_timestamp",
        lambda: "2026-09-20T02:00:00Z",
    )
    client = TestClient(create_app())

    response = client.get(
        "/stocks/nvda/research-data",
        params={"benchmark": "spy", "history_limit": 30},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "NVDA"
    assert payload["benchmark_symbol"] == "SPY"
    assert payload["collected_at"] == "2026-09-20T02:00:00Z"
    assert payload["quote"]["price"] == 180.0
    assert payload["price_history"]["symbol"] == "NVDA"
    assert payload["benchmark_history"]["symbol"] == "SPY"
    assert payload["coverage"] == {
        "latest_quote": True,
        "adjusted_daily_ohlcv": True,
        "benchmark_daily_ohlcv": True,
        "fundamentals": False,
        "news": False,
        "options": False,
        "macro": False,
    }
    assert requested_history_symbols == ["NVDA", "SPY"]
