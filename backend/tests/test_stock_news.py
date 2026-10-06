from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.services import stock_news_services
from app.api.services.stock_news_services import build_stock_news_response
from app.clients.alpha_vantage import (
    AlphaVantageClient,
    AlphaVantageNewsArticle,
    AlphaVantageNewsTopic,
)
from app.main import create_app


def make_article(
    title: str,
    url: str,
    published_at: str,
    sentiment_score: float,
    relevance_score: float = 0.9,
) -> AlphaVantageNewsArticle:
    return AlphaVantageNewsArticle(
        title=title,
        summary="The company reported results to investors.",
        url=url,
        source="Example News",
        source_domain="example.com",
        published_at=published_at,
        authors=["Market Reporter"],
        topics=[AlphaVantageNewsTopic(name="Financial Markets", relevance_score=0.8)],
        overall_sentiment_score=sentiment_score,
        overall_sentiment_label="Somewhat-Bullish",
        ticker_relevance_score=relevance_score,
        ticker_sentiment_score=sentiment_score,
        ticker_sentiment_label="Somewhat-Bullish",
    )


def test_alpha_vantage_news_parser_uses_symbol_specific_sentiment(monkeypatch) -> None:
    client = AlphaVantageClient()
    captured_params: dict[str, str] = {}

    def fake_get_json(params: dict[str, str]) -> dict:
        captured_params.update(params)
        return {
            "feed": [
                {
                    "title": "NVIDIA reports strong growth",
                    "summary": "Revenue beat expectations.",
                    "url": "https://example.com/nvda",
                    "time_published": "20260919T143000",
                    "source": "Example News",
                    "source_domain": "example.com",
                    "authors": ["Reporter"],
                    "topics": [
                        {"topic": "Earnings", "relevance_score": "0.75"}
                    ],
                    "overall_sentiment_score": "0.2",
                    "overall_sentiment_label": "Somewhat-Bullish",
                    "ticker_sentiment": [
                        {
                            "ticker": "AMD",
                            "relevance_score": "0.1",
                            "ticker_sentiment_score": "-0.4",
                            "ticker_sentiment_label": "Bearish",
                        },
                        {
                            "ticker": "NVDA",
                            "relevance_score": "0.95",
                            "ticker_sentiment_score": "0.35",
                            "ticker_sentiment_label": "Bullish",
                        },
                    ],
                }
            ]
        }

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    articles = client.get_news_sentiment(
        symbol="nvda",
        time_from="20260901T0000",
        time_to="20260920T0000",
        limit=100,
    )

    assert captured_params["function"] == "NEWS_SENTIMENT"
    assert captured_params["tickers"] == "NVDA"
    assert captured_params["sort"] == "LATEST"
    assert articles[0].published_at == "2026-09-19T14:30:00Z"
    assert articles[0].ticker_relevance_score == 0.95
    assert articles[0].ticker_sentiment_score == 0.35


def test_news_service_deduplicates_and_scores_articles() -> None:
    articles = [
        make_article(
            "Company posts excellent growth and record profit",
            "https://example.com/story?utm_source=test",
            "2026-09-19T14:30:00Z",
            0.4,
        ),
        make_article(
            "Company posts excellent growth and record profit",
            "https://example.com/story",
            "2026-09-19T14:30:00Z",
            0.4,
        ),
        make_article(
            "Company warns of terrible losses and weak demand",
            "https://example.com/second-story",
            "2026-09-18T12:00:00Z",
            -0.4,
        ),
        make_article(
            "A broad market article that barely mentions the company",
            "https://example.com/low-relevance",
            "2026-09-18T10:00:00Z",
            0.1,
            relevance_score=0.2,
        ),
    ]

    response = build_stock_news_response(
        symbol="NVDA",
        articles=articles,
        period_start=datetime(2026, 9, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 9, 20, tzinfo=timezone.utc),
        requested_limit=10,
        fetched_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
    )

    assert response.summary.article_count == 2
    assert response.summary.positive_count == 1
    assert response.summary.negative_count == 1
    assert response.summary.source_count == 1
    assert response.articles[0].vader_label == "positive"
    assert response.articles[1].vader_label == "negative"
    assert response.result_limit_reached is False
    assert any("ticker relevance" in warning for warning in response.warnings)


def test_news_endpoint_returns_period_summary(monkeypatch) -> None:
    stock_news_services._news_cache.clear()

    class FakeAlphaVantageClient:
        def get_news_sentiment(
            self,
            symbol: str,
            time_from: str,
            time_to: str,
            limit: int,
        ) -> list[AlphaVantageNewsArticle]:
            assert symbol == "NVDA"
            assert limit == 50
            return [
                make_article(
                    "NVIDIA reports strong demand and higher profit",
                    "https://example.com/nvidia",
                    "2026-09-19T14:30:00Z",
                    0.3,
                )
            ]

    monkeypatch.setattr(
        stock_news_services,
        "AlphaVantageClient",
        FakeAlphaVantageClient,
    )
    monkeypatch.setattr(
        stock_news_services,
        "datetime",
        FixedDateTime,
    )
    client = TestClient(create_app())

    response = client.get("/stocks/nvda/news", params={"days": 30, "limit": 50})

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "NVDA"
    assert payload["model"] == "VADER 3.3.2"
    assert payload["summary"]["article_count"] == 1
    assert payload["summary"]["label"] == "positive"


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
