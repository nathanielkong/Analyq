from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.services import stock_history_services
from app.api.services.stock_history_services import validate_historical_bars
from app.clients.alpaca import AlpacaClient, AlpacaHistoricalBar
from app.clients.alpha_vantage import AlphaVantageClient, AlphaVantageDailyBar
from app.clients.errors import (
    MarketDataError,
    MarketDataRateLimitError,
    StockSymbolNotFoundError,
)
from app.main import create_app


def make_bar(
    timestamp: str,
    close: float,
    *,
    open_price: float | None = None,
    high: float | None = None,
    low: float | None = None,
    volume: int = 1_000_000,
) -> AlpacaHistoricalBar:
    resolved_open = close if open_price is None else open_price

    return AlpacaHistoricalBar(
        timestamp=timestamp,
        open=resolved_open,
        high=close if high is None else high,
        low=close if low is None else low,
        close=close,
        volume=volume,
    )


class FakeAlpacaHistoryClient:
    def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        start: str,
        end: str,
        adjustment: str,
    ) -> list[AlpacaHistoricalBar]:
        assert symbol == "NVDA"
        assert timeframe == "1Day"
        assert limit == 2
        assert start < end
        assert end == "2026-09-19"
        assert adjustment == "all"

        return [
            AlpacaHistoricalBar(
                timestamp="2026-09-17T04:00:00Z",
                open=175.0,
                high=181.0,
                low=174.5,
                close=180.0,
                volume=42_000_000,
            ),
            AlpacaHistoricalBar(
                timestamp="2026-09-18T04:00:00Z",
                open=180.5,
                high=184.0,
                low=179.0,
                close=183.25,
                volume=45_000_000,
            ),
        ]


class MissingHistoryAlpacaClient:
    def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        start: str,
        end: str,
        adjustment: str,
    ) -> list[AlpacaHistoricalBar]:
        raise StockSymbolNotFoundError(f"Stock symbol {symbol} was not found.")


class RateLimitedHistoryAlpacaClient:
    def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        start: str,
        end: str,
        adjustment: str,
    ) -> list[AlpacaHistoricalBar]:
        raise MarketDataRateLimitError("Alpaca rate limit reached.")


def test_stock_history_endpoint_returns_adjusted_daily_bars(monkeypatch) -> None:
    monkeypatch.setattr(
        stock_history_services,
        "AlpacaClient",
        FakeAlpacaHistoryClient,
    )
    monkeypatch.setattr(
        stock_history_services,
        "_current_market_date",
        lambda: date(2026, 9, 20),
    )
    client = TestClient(create_app())

    response = client.get("/stocks/nvda/history", params={"limit": 2})

    assert response.status_code == 200
    assert response.json() == {
        "symbol": "NVDA",
        "provider": "alpaca",
        "timeframe": "1Day",
        "adjusted": True,
        "requested_bar_count": 2,
        "warnings": [],
        "bars": [
            {
                "timestamp": "2026-09-17T04:00:00Z",
                "open": 175.0,
                "high": 181.0,
                "low": 174.5,
                "close": 180.0,
                "volume": 42_000_000,
                "source": "Alpaca (IEX, adjusted)",
            },
            {
                "timestamp": "2026-09-18T04:00:00Z",
                "open": 180.5,
                "high": 184.0,
                "low": 179.0,
                "close": 183.25,
                "volume": 45_000_000,
                "source": "Alpaca (IEX, adjusted)",
            },
        ],
    }


def test_stock_history_endpoint_returns_404_for_unknown_symbol(monkeypatch) -> None:
    monkeypatch.setattr(
        stock_history_services,
        "AlpacaClient",
        MissingHistoryAlpacaClient,
    )
    client = TestClient(create_app())

    response = client.get("/stocks/UNKNOWN/history", params={"limit": 2})

    assert response.status_code == 404
    assert response.json()["detail"] == "Stock symbol UNKNOWN was not found."


def test_stock_history_endpoint_returns_429_for_provider_rate_limit(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        stock_history_services,
        "AlpacaClient",
        RateLimitedHistoryAlpacaClient,
    )
    client = TestClient(create_app())

    response = client.get("/stocks/NVDA/history", params={"limit": 30})

    assert response.status_code == 429
    assert response.json()["detail"] == "Alpaca rate limit reached."


def test_stock_history_normalizes_class_share_separator() -> None:
    assert stock_history_services.normalize_stock_symbol(" brk-b ") == "BRK.B"


def test_alpaca_historical_bars_request_adjusted_data(monkeypatch) -> None:
    captured_path = ""
    captured_params: dict[str, str] = {}
    client = AlpacaClient()

    def fake_get_data_json(path: str, params: dict[str, str]) -> dict:
        nonlocal captured_path
        captured_path = path
        captured_params.update(params)

        return {
            "bars": [
                {
                    "t": "2026-09-18T04:00:00Z",
                    "o": 180.5,
                    "h": 184.0,
                    "l": 179.0,
                    "c": 183.25,
                    "v": 45_000_000,
                },
                {
                    "t": "2026-09-17T04:00:00Z",
                    "o": 175.0,
                    "h": 181.0,
                    "l": 174.5,
                    "c": 180.0,
                    "v": 42_000_000,
                },
            ]
        }

    monkeypatch.setattr(client, "_get_data_json", fake_get_data_json)

    bars = client.get_historical_bars(
        symbol="nvda",
        timeframe="1Day",
        limit=2,
        start="2026-01-01",
        end="2026-09-19",
        adjustment="all",
    )

    assert captured_path == "/v2/stocks/NVDA/bars"
    assert captured_params == {
        "timeframe": "1Day",
        "start": "2026-01-01",
        "end": "2026-09-19",
        "limit": "2",
        "adjustment": "all",
        "feed": "iex",
        "sort": "desc",
    }
    assert [bar.timestamp for bar in bars] == [
        "2026-09-17T04:00:00Z",
        "2026-09-18T04:00:00Z",
    ]


def test_historical_validation_rejects_close_outside_daily_range() -> None:
    invalid_bar = make_bar(
        "2026-09-18T04:00:00Z",
        105.0,
        open_price=100.0,
        high=104.0,
        low=99.0,
    )

    with pytest.raises(
        MarketDataError,
        match="close price is outside its high-low range",
    ):
        validate_historical_bars([invalid_bar], 1, date(2026, 9, 20))


def test_historical_validation_warns_about_short_stale_extreme_series() -> None:
    bars = [
        make_bar("2026-09-01T04:00:00Z", 100.0),
        make_bar("2026-09-02T04:00:00Z", 150.0),
    ]

    warnings = validate_historical_bars(bars, 100, date(2026, 9, 20))

    assert any("2 of 100" in warning for warning in warnings)
    assert any("18 calendar days old" in warning for warning in warnings)
    assert any("50.0% close-to-close move" in warning for warning in warnings)


def test_stock_history_reuses_temporary_cache(monkeypatch) -> None:
    class CountingAlpacaHistoryClient:
        calls = 0

        def get_historical_bars(
            self,
            symbol: str,
            timeframe: str,
            limit: int,
            start: str,
            end: str,
            adjustment: str,
        ) -> list[AlpacaHistoricalBar]:
            CountingAlpacaHistoryClient.calls += 1

            return [
                make_bar(f"2026-08-{day:02d}T04:00:00Z", 100.0 + day)
                for day in range(1, 31)
            ]

    stock_history_services._history_cache.clear()
    monkeypatch.setattr(
        stock_history_services,
        "AlpacaClient",
        CountingAlpacaHistoryClient,
    )
    monkeypatch.setattr(
        stock_history_services,
        "_current_market_date",
        lambda: date(2026, 9, 1),
    )

    first = stock_history_services.get_stock_history(
        symbol="NVDA",
        provider="alpaca",
        timeframe="1Day",
        limit=30,
    )
    second = stock_history_services.get_stock_history(
        symbol="NVDA",
        provider="alpaca",
        timeframe="1Day",
        limit=30,
    )

    assert first is second
    assert CountingAlpacaHistoryClient.calls == 1


def test_alpha_vantage_daily_bars_are_still_parseable(monkeypatch) -> None:
    captured_params: dict[str, str] = {}
    client = AlphaVantageClient()

    def fake_get_json(params: dict[str, str]) -> dict:
        captured_params.update(params)

        return {
            "Time Series (Daily)": {
                "2026-09-18": {
                    "1. open": "180.5000",
                    "2. high": "184.0000",
                    "3. low": "179.0000",
                    "4. close": "183.2500",
                    "5. volume": "45000000",
                }
            }
        }

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    bars = client.get_daily_bars("nvda", limit=1)

    assert captured_params["function"] == "TIME_SERIES_DAILY"
    assert bars == [
        AlphaVantageDailyBar(
            timestamp="2026-09-18",
            open=180.5,
            high=184.0,
            low=179.0,
            close=183.25,
            volume=45_000_000,
        )
    ]
