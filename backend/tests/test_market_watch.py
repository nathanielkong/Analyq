from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes import market as market_routes
from app.api.schema.market_watch import MarketWatchResponse
from app.api.services.market_watch_services import _market_session, get_market_watch
from app.clients import alpha_vantage as alpha_vantage_module
from app.clients.alpaca import (
    AlpacaClient,
    AlpacaNewsArticle,
    AlpacaScreenerMover,
    AlpacaStockMovers,
    AlpacaStockSnapshot,
)
from app.clients.alpha_vantage import (
    AlphaVantageClient,
    AlphaVantageMarketMover,
    AlphaVantageMarketMovers,
    AlphaVantageMarketNewsArticle,
    AlphaVantageTickerSentiment,
)
from app.clients.errors import MarketDataError
from app.main import create_app


def test_alpha_vantage_provider_error_redacts_api_key(monkeypatch) -> None:
    monkeypatch.setattr(
        alpha_vantage_module.settings,
        "market_data_api_key",
        "secret-api-key",
    )

    error = alpha_vantage_module._build_provider_message_error(
        "Request failed for apikey=secret-api-key"
    )

    assert "secret-api-key" not in str(error)
    assert "[redacted]" in str(error)


def test_alpha_vantage_parses_broad_news_and_market_movers(monkeypatch) -> None:
    client = AlphaVantageClient()
    requests: list[dict[str, str]] = []

    def fake_get_json(params: dict[str, str]) -> dict:
        requests.append(params)

        if params["function"] == "NEWS_SENTIMENT":
            return {
                "feed": [
                    {
                        "title": "SanDisk gains attention after product news",
                        "url": "https://example.com/sndk",
                        "source": "Example News",
                        "time_published": "20260921T010000",
                        "ticker_sentiment": [
                            {
                                "ticker": "SNDK",
                                "relevance_score": "0.92",
                                "ticker_sentiment_score": "0.31",
                                "ticker_sentiment_label": "Bullish",
                            }
                        ],
                    }
                ]
            }

        return {
            "last_updated": "2026-09-21 16:15:59 US/Eastern",
            "top_gainers": [
                {
                    "ticker": "SNDK",
                    "price": "88.50",
                    "change_amount": "8.50",
                    "change_percentage": "10.625%",
                    "volume": "12500000",
                }
            ],
            "top_losers": [],
            "most_actively_traded": [],
        }

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    news = client.get_market_news(
        time_from="20260920T0000",
        time_to="20260921T1200",
        limit=200,
    )
    movers = client.get_top_movers()

    assert "tickers" not in requests[0]
    assert news[0].ticker_sentiments[0].ticker == "SNDK"
    assert news[0].ticker_sentiments[0].relevance_score == 0.92
    assert movers.top_gainers[0].change_percentage == 10.625
    assert movers.top_gainers[0].volume == 12_500_000


def test_alpaca_parses_multi_symbol_stock_snapshots(monkeypatch) -> None:
    client = AlpacaClient()

    monkeypatch.setattr(
        client,
        "_get_data_json",
        lambda path, params: {
            "SNDK": {
                "latestTrade": {"p": 90.0, "t": "2026-09-21T12:00:00Z"},
                "dailyBar": {
                    "o": 86.0,
                    "h": 91.0,
                    "l": 85.0,
                    "c": 90.0,
                    "v": 8_000_000,
                },
                "prevDailyBar": {"c": 80.0},
            }
        },
    )

    snapshots = client.get_stock_snapshots(["sndk"], feed="iex")

    assert snapshots["SNDK"].latest_price == 90.0
    assert snapshots["SNDK"].previous_close == 80.0
    assert snapshots["SNDK"].daily_volume == 8_000_000


def test_alpaca_parses_movers_and_broad_news(monkeypatch) -> None:
    client = AlpacaClient()

    def fake_get_data_json(path: str, params: dict[str, str]) -> dict:
        if path.endswith("/movers"):
            return {
                "last_updated": "2026-09-21T12:00:00Z",
                "gainers": [
                    {
                        "symbol": "SNDK",
                        "price": 90.0,
                        "change": 10.0,
                        "percent_change": 12.5,
                    }
                ],
                "losers": [],
            }

        return {
            "news": [
                {
                    "headline": "SanDisk launches new storage product",
                    "summary": "Investors respond positively.",
                    "url": "https://example.com/alpaca-sndk",
                    "source": "Example Wire",
                    "created_at": "2026-09-21T11:30:00Z",
                    "symbols": ["SNDK"],
                }
            ]
        }

    monkeypatch.setattr(client, "_get_data_json", fake_get_data_json)

    movers = client.get_stock_movers(top=10)
    news = client.get_market_news(
        start="2026-09-20T00:00:00Z",
        end="2026-09-21T12:00:00Z",
    )

    assert movers.gainers[0].symbol == "SNDK"
    assert movers.gainers[0].percent_change == 12.5
    assert news[0].symbols == ["SNDK"]


def test_market_watch_combines_news_momentum_and_activity() -> None:
    news = [
        AlphaVantageMarketNewsArticle(
            title="SanDisk announces a major storage update",
            url="https://example.com/sndk",
            source="Example News",
            published_at="2026-09-21T01:00:00Z",
            ticker_sentiments=[
                AlphaVantageTickerSentiment(
                    ticker="SNDK",
                    relevance_score=0.95,
                    sentiment_score=0.4,
                    sentiment_label="Bullish",
                )
            ],
        )
    ]
    movers = AlphaVantageMarketMovers(
        last_updated="2026-09-21 close",
        top_gainers=[
            AlphaVantageMarketMover(
                ticker="SNDK",
                price=88.5,
                change_amount=8.5,
                change_percentage=10.625,
                volume=12_500_000,
            )
        ],
        top_losers=[],
        most_actively_traded=[
            AlphaVantageMarketMover(
                ticker="NVDA",
                price=200.0,
                change_amount=1.0,
                change_percentage=0.5,
                volume=50_000_000,
            ),
            AlphaVantageMarketMover(
                ticker="SNDK",
                price=88.5,
                change_amount=8.5,
                change_percentage=10.625,
                volume=12_500_000,
            ),
        ],
    )

    class FakeClient:
        def get_market_news(self, **kwargs: object):
            return news

        def get_top_movers(self):
            return movers

    class FakeSnapshotClient:
        def get_stock_movers(self, top: int = 20):
            return AlpacaStockMovers(gainers=[], losers=[], last_updated=None)

        def get_market_news(self, start: str, end: str, limit: int = 50):
            return []

        def get_stock_snapshots(self, symbols: list[str], feed: str | None = None):
            assert "SNDK" in symbols
            return {
                "SNDK": AlpacaStockSnapshot(
                    symbol="SNDK",
                    latest_price=90.0,
                    latest_timestamp="2026-09-21T12:00:00Z",
                    previous_close=80.0,
                    daily_open=86.0,
                    daily_high=91.0,
                    daily_low=85.0,
                    daily_volume=8_000_000,
                )
            }

    response = get_market_watch(
        limit=5,
        now=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
        client=FakeClient(),
        snapshot_client=FakeSnapshotClient(),
    )

    assert response.candidates[0].symbol == "SNDK"
    assert response.candidates[0].signal == "mixed_attention"
    assert response.candidates[0].sentiment == "bullish"
    assert response.candidates[0].change_percent == 12.5
    assert response.candidates[0].market_session == "premarket"
    assert response.movers[0].symbol == "SNDK"
    assert response.news_catalysts[0].symbol == "SNDK"
    assert len(response.candidates[0].reasons) == 3


def test_market_watch_uses_alpaca_when_alpha_is_unavailable() -> None:
    class FailingAlphaClient:
        def get_market_news(self, **kwargs: object):
            raise MarketDataError("Alpha unavailable")

        def get_top_movers(self):
            raise MarketDataError("Alpha unavailable")

    class FakeAlpacaClient:
        def get_stock_movers(self, top: int = 20):
            return AlpacaStockMovers(
                gainers=[
                    AlpacaScreenerMover(
                        symbol="SNDK",
                        price=90.0,
                        change=10.0,
                        percent_change=12.5,
                    )
                ],
                losers=[],
                last_updated="2026-09-21T12:00:00Z",
            )

        def get_market_news(self, start: str, end: str, limit: int = 50):
            return [
                AlpacaNewsArticle(
                    headline="SanDisk launches a major new product",
                    summary="The announcement receives a positive response.",
                    url="https://example.com/alpaca-sndk",
                    source="Example Wire",
                    created_at="2026-09-21T11:30:00Z",
                    symbols=["SNDK"],
                )
            ]

        def get_stock_snapshots(self, symbols: list[str], feed: str | None = None):
            return {
                "SNDK": AlpacaStockSnapshot(
                    symbol="SNDK",
                    latest_price=90.0,
                    latest_timestamp="2026-09-21T12:00:00Z",
                    previous_close=80.0,
                    daily_open=86.0,
                    daily_high=91.0,
                    daily_low=85.0,
                    daily_volume=8_000_000,
                )
            }

    response = get_market_watch(
        limit=5,
        now=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
        client=FailingAlphaClient(),
        snapshot_client=FakeAlpacaClient(),
    )

    assert response.provider == "Alpaca"
    assert response.movers[0].symbol == "SNDK"
    assert response.news_catalysts[0].symbol == "SNDK"
    assert response.market_data_freshness == "combined_snapshot"


def test_market_watch_route_returns_ranked_candidates(monkeypatch) -> None:
    expected = MarketWatchResponse(
        generated_at="2026-09-21T12:00:00Z",
        provider="Alpha Vantage",
        period_start="2026-09-20T00:00:00Z",
        period_end="2026-09-21T12:00:00Z",
        market_snapshot_at="2026-09-21 close",
        market_data_freshness="provider_snapshot",
        market_session="closed",
        snapshot_feed=None,
        candidates=[],
        movers=[],
        news_catalysts=[],
        warnings=[],
    )
    monkeypatch.setattr(
        market_routes,
        "get_market_watch",
        lambda limit: expected,
    )
    client = TestClient(create_app())

    response = client.get("/market/watch", params={"limit": 8})

    assert response.status_code == 200
    assert response.json()["provider"] == "Alpha Vantage"


def test_market_session_labels_extended_hours() -> None:
    assert _market_session(
        datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    ) == "premarket"
    assert _market_session(
        datetime(2026, 9, 21, 14, 0, tzinfo=timezone.utc)
    ) == "regular"
    assert _market_session(
        datetime(2026, 9, 21, 21, 0, tzinfo=timezone.utc)
    ) == "after_hours"
    assert _market_session(
        datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)
    ) == "overnight"
