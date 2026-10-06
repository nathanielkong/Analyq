from datetime import date, datetime, timedelta, timezone
from math import sin
import pytest

from app.api.schema.stock_history import StockHistoryBarResponse, StockHistoryResponse
from app.api.schema.stock_news import StockNewsResponse
from app.api.services.stock_direction_services import (
    _build_model_rows,
    _classify_lean,
    _classify_validation_status,
    build_direction_model,
)
from app.api.services.stock_news_services import build_stock_news_response
from app.clients.alpha_vantage import AlphaVantageNewsArticle


def make_history(symbol: str, benchmark: bool = False) -> StockHistoryResponse:
    start_date = date(2025, 1, 2)
    bars: list[StockHistoryBarResponse] = []

    for index in range(220):
        cycle = sin(index * (0.41 if benchmark else 0.67))
        close = (400 if benchmark else 100) + (index * 0.08) + (cycle * 2.5)
        open_price = close * (1 - (0.002 * sin(index * 0.29)))
        high = max(close, open_price) * 1.01
        low = min(close, open_price) * 0.99
        bars.append(
            StockHistoryBarResponse(
                timestamp=(start_date + timedelta(days=index)).isoformat(),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1_000_000 + ((index % 13) * 25_000),
                source="test",
            )
        )

    return StockHistoryResponse(
        symbol=symbol,
        provider="alpaca",
        timeframe="1Day",
        adjusted=True,
        requested_bar_count=220,
        warnings=[],
        bars=bars,
    )


def make_news() -> StockNewsResponse:
    articles = []

    for index in range(20):
        published = datetime(2025, 3, 1, 15, tzinfo=timezone.utc) + timedelta(
            days=index * 7
        )
        positive = index % 2 == 0
        articles.append(
            AlphaVantageNewsArticle(
                title=(
                    "Company reports excellent growth and strong profit"
                    if positive
                    else "Company reports weak demand and disappointing loss"
                ),
                summary="Management discussed the latest quarter.",
                url=f"https://example.com/article-{index}",
                source="Example News",
                source_domain="example.com",
                published_at=published.isoformat().replace("+00:00", "Z"),
                authors=[],
                topics=[],
                overall_sentiment_score=0.2 if positive else -0.2,
                overall_sentiment_label=None,
                ticker_relevance_score=0.9,
                ticker_sentiment_score=0.2 if positive else -0.2,
                ticker_sentiment_label=None,
            )
        )

    return build_stock_news_response(
        symbol="TEST",
        articles=articles,
        period_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 1, 1, tzinfo=timezone.utc),
        requested_limit=1000,
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize("horizon", [1, 3, 5])
def test_horizon_targets_and_unknown_future_rows(horizon):
    history = make_history("TEST")
    rows = _build_model_rows(
        history, make_history("SPY", benchmark=True), None, horizon_sessions=horizon
    )
    assert all(row.target is None for row in rows[-horizon:])
    assert rows[0].target == int(
        history.bars[20 + horizon].close > history.bars[20].close
    )
    result = build_direction_model(
        history,
        make_history("SPY", benchmark=True),
        make_news(),
        horizon_sessions=horizon,
    )
    assert result.horizon_sessions == horizon
    assert result.training_end == history.bars[-horizon - 1].timestamp
    assert result.training_sample_count == 220 - 20 - horizon
    assert result.validation_fold_count >= 2
    assert 0 <= result.up_probability_pct <= 100


def test_walk_forward_purges_future_labels(monkeypatch):
    from sklearn.model_selection import TimeSeriesSplit
    from app.api.services import stock_direction_services as services

    gaps = []

    def splitter(**kwargs):
        gaps.append(kwargs["gap"])
        return TimeSeriesSplit(**kwargs)

    monkeypatch.setattr(services, "TimeSeriesSplit", splitter)
    build_direction_model(
        make_history("TEST"),
        make_history("SPY", benchmark=True),
        make_news(),
        horizon_sessions=5,
    )
    assert gaps == [5]


def test_direction_model_returns_walk_forward_probability() -> None:
    result = build_direction_model(
        stock_history=make_history("TEST"),
        benchmark_history=make_history("SPY", benchmark=True),
        news=make_news(),
        generated_at="2026-01-01T00:00:00Z",
    )

    assert result.model_version == "1.2.0"
    assert result.model_type == "logistic_regression"
    assert result.target == "next_completed_close_is_higher"
    assert result.generated_at == "2026-01-01T00:00:00Z"
    assert result.training_sample_count >= 60
    assert result.validation_sample_count > 0
    assert result.validation_fold_count >= 2
    assert result.validation_status in {
        "validated_edge",
        "inconclusive",
        "no_edge",
    }
    assert 0 <= result.up_probability_pct <= 100
    assert round(result.up_probability_pct + result.down_probability_pct, 2) == 100
    assert 0 <= result.validation_accuracy_pct <= 100
    assert 0 <= result.validation_balanced_accuracy_pct <= 100
    assert 0 <= result.validation_precision_pct <= 100
    assert 0 <= result.validation_recall_pct <= 100
    assert 0 <= result.validation_f1_pct <= 100
    assert result.validation_roc_auc is None or 0 <= result.validation_roc_auc <= 1
    assert 0 <= result.baseline_brier_score <= 1
    assert result.validation_log_loss >= 0
    assert (
        sum(
            (
                result.confusion_matrix.true_down_predicted_down,
                result.confusion_matrix.true_down_predicted_up,
                result.confusion_matrix.true_up_predicted_down,
                result.confusion_matrix.true_up_predicted_up,
            )
        )
        == result.validation_sample_count
    )
    assert sum(item.sample_count for item in result.calibration) == (
        result.validation_sample_count
    )
    assert len(result.folds) == result.validation_fold_count
    assert len(result.feature_stability) == len(result.feature_names)
    assert result.news_features_used is True
    assert "rsi_14" in result.feature_names
    assert "news_vader_compound" in result.feature_names
    assert set(result.feature_names) == set(result.latest_feature_values)


def test_direction_model_excludes_incomplete_news_history() -> None:
    capped_news = make_news().model_copy(update={"result_limit_reached": True})

    result = build_direction_model(
        stock_history=make_history("TEST"),
        benchmark_history=make_history("SPY", benchmark=True),
        news=capped_news,
        generated_at="2026-01-01T00:00:00Z",
    )

    assert result.news_features_used is False
    assert "news_vader_compound" not in result.feature_names
    assert any("provider limit" in warning for warning in result.warnings)


def test_validation_gate_requires_accuracy_auc_and_probability_improvements() -> None:
    assert (
        _classify_validation_status(
            accuracy_edge=0.03,
            roc_auc=0.56,
            brier_score=0.23,
            baseline_brier_score=0.25,
        )
        == "validated_edge"
    )
    assert (
        _classify_validation_status(
            accuracy_edge=0.03,
            roc_auc=0.49,
            brier_score=0.23,
            baseline_brier_score=0.25,
        )
        == "no_edge"
    )
    assert _classify_lean(0.7, "no_edge") == "mixed"
    assert _classify_lean(0.7, "validated_edge") == "leaning_up"
