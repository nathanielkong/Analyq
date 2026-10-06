from fastapi.testclient import TestClient

from app.api.services import stock_services
from app.clients.alpaca import AlpacaAsset, AlpacaBar
from app.clients.alpha_vantage import (
    AlphaVantageQuote,
    AlphaVantageSearchResult,
)
from app.clients.errors import StockSymbolNotFoundError
from app.main import create_app


class FakeAlphaVantageClient:
    def get_quote(self, symbol: str) -> AlphaVantageQuote:
        return AlphaVantageQuote(
            symbol=symbol,
            price=123.45,
            change=1.23,
            change_percent=1.01,
            volume=1000000,
            latest_trading_day="2026-09-11",
            previous_close=122.22,
            open=121.5,
            high=124.0,
            low=120.5,
        )

    def search_symbols(self, keywords: str) -> list[AlphaVantageSearchResult]:
        return [
            AlphaVantageSearchResult(
                symbol="DIS",
                name="The Walt Disney Company",
                type="Equity",
                region="United States",
                currency="USD",
                match_score=0.91,
            )
        ]


class MissingSymbolAlphaVantageClient:
    def get_quote(self, symbol: str) -> AlphaVantageQuote:
        raise StockSymbolNotFoundError(f"Stock symbol {symbol} was not found.")


class NoMatchAlphaVantageClient:
    queries: list[str] = []

    def search_symbols(self, keywords: str) -> list[AlphaVantageSearchResult]:
        self.queries.append(keywords)

        if keywords == "disney":
            return []

        if keywords == "disney company":
            return [
                AlphaVantageSearchResult(
                    symbol="DIS",
                    name="Walt Disney Co (The)",
                    type="Equity",
                    region="United States",
                    currency="USD",
                    match_score=0.71,
                )
            ]

        return []


class FakeAlpacaClient:
    def get_stock_snapshots(self, symbols):
        from app.clients.alpaca import AlpacaStockSnapshot
        return {symbol: AlpacaStockSnapshot(
            symbol=symbol, latest_price=200.5, latest_timestamp="2026-09-18T14:30:00Z",
            previous_close=200.0, daily_open=198.0, daily_high=202.0,
            daily_low=197.5, daily_volume=5000000,
        ) for symbol in symbols}

    def get_latest_bar(self, symbol: str) -> AlpacaBar:
        return AlpacaBar(
            symbol=symbol,
            close=200.5,
            open=198.0,
            high=202.0,
            low=197.5,
            volume=5000000,
            timestamp="2026-09-18T14:30:00Z",
        )

    def list_assets(self) -> list[AlpacaAsset]:
        return [
            AlpacaAsset(
                symbol="DIS",
                name="Walt Disney Co (The)",
                asset_class="us_equity",
                exchange="NYSE",
                status="active",
                currency="USD",
            ),
            AlpacaAsset(
                symbol="NVDA",
                name="NVIDIA Corp",
                asset_class="us_equity",
                exchange="NASDAQ",
                status="active",
                currency="USD",
            ),
        ]


def test_stock_endpoint_returns_quote(monkeypatch) -> None:
    monkeypatch.setattr(stock_services.settings, "market_data_provider", "alpha_vantage")
    monkeypatch.setattr(stock_services, "AlphaVantageClient", FakeAlphaVantageClient)
    client = TestClient(create_app())

    response = client.get("/stocks/NVDA")

    assert response.status_code == 200
    assert response.json() == {
        "symbol": "NVDA",
        "company_name": None,
        "price": 123.45,
        "currency": "USD",
        "change": 1.23,
        "change_percent": 1.01,
        "volume": 1000000,
        "latest_trading_day": "2026-09-11",
        "previous_close": 122.22,
        "open": 121.5,
        "high": 124.0,
        "low": 120.5,
        "source": "Alpha Vantage",
    }


def test_stock_endpoint_returns_404_for_unknown_symbol(monkeypatch) -> None:
    monkeypatch.setattr(stock_services.settings, "market_data_provider", "alpha_vantage")
    monkeypatch.setattr(
        stock_services,
        "AlphaVantageClient",
        MissingSymbolAlphaVantageClient,
    )
    client = TestClient(create_app())

    response = client.get("/stocks/UNKNOWN")

    assert response.status_code == 404
    assert response.json()["detail"] == "Stock symbol UNKNOWN was not found."


def test_stock_search_endpoint_returns_provider_matches(monkeypatch) -> None:
    stock_services._search_cache.clear()
    monkeypatch.setattr(stock_services.settings, "market_data_provider", "alpha_vantage")
    monkeypatch.setattr(stock_services, "AlphaVantageClient", FakeAlphaVantageClient)
    client = TestClient(create_app())

    response = client.get("/stocks/search", params={"query": "disney"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "symbol": "DIS",
            "name": "The Walt Disney Company",
            "type": "Equity",
            "region": "United States",
            "currency": "USD",
            "match_score": 0.91,
        }
    ]


def test_stock_search_endpoint_does_not_guess_a_second_query(monkeypatch) -> None:
    stock_services._search_cache.clear()
    NoMatchAlphaVantageClient.queries = []
    monkeypatch.setattr(stock_services.settings, "market_data_provider", "alpha_vantage")
    monkeypatch.setattr(
        stock_services,
        "AlphaVantageClient",
        NoMatchAlphaVantageClient,
    )
    client = TestClient(create_app())

    response = client.get("/stocks/search", params={"query": "disney"})

    assert response.status_code == 200
    assert response.json() == []
    assert NoMatchAlphaVantageClient.queries == ["disney"]


def test_stock_search_endpoint_can_use_alpaca_assets(monkeypatch) -> None:
    stock_services._search_cache.clear()
    stock_services._asset_cache = None
    monkeypatch.setattr(stock_services.settings, "market_data_provider", "alpaca")
    monkeypatch.setattr(stock_services, "AlpacaClient", FakeAlpacaClient)
    client = TestClient(create_app())

    response = client.get("/stocks/search", params={"query": "disney"})

    assert response.status_code == 200
    assert response.json()[0] == {
        "symbol": "DIS",
        "name": "Walt Disney Co (The)",
        "type": "Equity",
        "region": "United States",
        "currency": "USD",
        "match_score": 0.5,
    }


def test_stock_endpoint_can_use_alpaca_quote(monkeypatch) -> None:
    stock_services._asset_cache = None
    monkeypatch.setattr(stock_services.settings, "market_data_provider", "alpaca")
    monkeypatch.setattr(stock_services.settings, "alpaca_data_feed", "iex")
    monkeypatch.setattr(stock_services, "AlpacaClient", FakeAlpacaClient)
    client = TestClient(create_app())

    response = client.get("/stocks/NVDA")

    assert response.status_code == 200
    assert response.json() == {
        "symbol": "NVDA",
        "company_name": "NVIDIA Corp",
        "price": 200.5,
        "currency": "USD",
        "change": 0.5,
        "change_percent": 0.25,
        "volume": 5000000,
        "latest_trading_day": "2026-09-18T14:30:00Z",
        "previous_close": 200.0,
        "open": 198.0,
        "high": 202.0,
        "low": 197.5,
        "source": "Alpaca (IEX)",
    }
