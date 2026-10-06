from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from test_stock_analysis import make_history

from app.api.routes import stocks
from app.api.services import pattern_backtest_services as backtest
from app.api.services.stock_pattern_services import build_daily_patterns
from app.clients.errors import (
    MarketDataError,
    MarketDataRateLimitError,
    StockSymbolNotFoundError,
)
from app.main import create_app


def evaluate(closes):
    history = make_history("TEST", closes)
    cutoff = datetime.fromisoformat(history.bars[-1].timestamp).replace(
        tzinfo=timezone.utc
    ) + timedelta(days=1, hours=12)
    return backtest.build_daily_pattern_backtest(history, as_of=cutoff)


def pattern(result, name="rising_streak_high_rsi"):
    return next(item for item in result.results if item.name == name)


def test_known_streak_reversal_at_each_horizon():
    closes = [100] * 22 + [105, 106, 107, 100, 99, 98, 99, 100]
    result = evaluate(closes)
    tested = pattern(result)
    assert tested.initial_active_excluded == 0
    for item, target in zip(tested.horizons, [100, 98, 100]):
        assert item.signal_count == item.pattern.count == 1
        assert item.pending_outcomes == item.overlap_excluded == 0
        assert item.pattern.reversal_rate_pct == 100
        assert item.pattern.mean_return_pct == pytest.approx((target / 107 - 1) * 100)
        assert item.pattern.median_return_pct == item.pattern.mean_return_pct
        assert item.status == "small_sample"
        assert item.approximate_wilson_95_low_pct < 30  # One success is weak evidence.
        assert item.outcomes[0].signal_timestamp == "2026-01-26"
        assert item.outcomes[0].reversed
        # RSI becomes evaluable at index 14, with a horizon-specific right cutoff.
        assert item.baseline.count == len(closes) - 14 - item.horizon_bars
        assert item.reversal_rate_difference_pp == pytest.approx(
            100 - item.baseline.reversal_rate_pct
        )
    assert result.completed_bar_count == 30
    assert result.evaluation == "exploratory_historical_study"


def test_downward_streak_uses_upward_reversal_not_downward():
    result = evaluate([100] * 22 + [95, 94, 93, 98, 99, 100, 100, 100])
    tested = pattern(result, "falling_streak_low_rsi")
    assert tested.reversal_direction == "up"
    assert all(item.pattern.reversals == 1 for item in tested.horizons)


def test_unfinished_labels_are_pending_not_losses():
    result = evaluate([100] * 22 + [105, 106, 107, 100])
    one, three, five = pattern(result).horizons
    assert one.pattern.count == 1
    for item in (three, five):
        assert item.signal_count == item.pending_outcomes == 1
        assert item.pattern.count == 0
        assert item.pattern.reversal_rate_pct is None
        assert item.reversal_rate_difference_pp is None
        assert item.approximate_wilson_95_low_pct is None


def test_flat_final_close_is_not_a_reversal():
    result = evaluate([100] * 22 + [105, 106, 107, 107])
    one = pattern(result).horizons[0]
    assert one.pattern.count == one.pattern.flat_outcomes == 1
    assert one.pattern.reversal_rate_pct == 0
    assert one.pattern.mean_return_pct == 0


def test_persistent_pattern_counts_once_not_each_day():
    result = evaluate([100] * 22 + [105, 106, 107, 108, 109, 110, 111, 112])
    for item in pattern(result).horizons:
        assert item.signal_count == item.pattern.count == 1
        assert item.pattern.reversals == 0


def test_already_active_when_history_starts_is_excluded():
    result = evaluate([100 + index for index in range(40)])
    tested = pattern(result)
    assert tested.initial_active_excluded == 1
    for item in tested.horizons:
        assert item.signal_count == 0
        assert item.pattern.reversal_rate_pct is None
        assert item.baseline.count > 0
        assert item.baseline.reversal_rate_pct == 0


def test_overlap_exclusion_is_horizon_specific():
    bars = make_history("TEST", [100 + i for i in range(12)]).bars
    states = [
        False,
        True,
        False,
        True,
        False,
        False,
        False,
        True,
        False,
        False,
        False,
        False,
    ]
    one = backtest._evaluate_horizon(bars, states, [1, 3, 7], "up", 1)
    five = backtest._evaluate_horizon(bars, states, [1, 3, 7], "up", 5)
    assert one.pattern.count == 3
    assert five.pattern.count == 1
    assert five.overlap_excluded == 1
    assert five.pending_outcomes == 1
    assert (
        five.signal_count
        == five.pattern.count + five.pending_outcomes + five.overlap_excluded
    )


def test_wilson_interval_known_example_and_no_samples():
    assert backtest._wilson_interval(0, 0) == (None, None)
    low, high = backtest._wilson_interval(5, 10)
    assert low == pytest.approx(23.6593, abs=0.001)
    assert high == pytest.approx(76.3407, abs=0.001)
    assert backtest._wilson_interval(0, 10)[0] == pytest.approx(0)
    assert backtest._wilson_interval(10, 10)[1] == pytest.approx(100)


def test_historical_cutoff_excludes_same_day_future_outcomes():
    history = make_history("TEST", [100] * 22 + [105, 106, 107, 100, 99, 98, 97, 96])
    # At Jan 27 01:00 UTC it is still Jan 26 in New York, so Jan 26 is excluded.
    cutoff = datetime(2026, 1, 27, 1, tzinfo=timezone.utc)
    full = backtest.build_daily_pattern_backtest(history, as_of=cutoff)
    prefix = backtest.build_daily_pattern_backtest(
        history.model_copy(update={"bars": history.bars[:24]}), as_of=cutoff
    )
    assert full.completed_bar_count == 24
    assert full.results == prefix.results
    assert full.data_through == "2026-01-25"


def test_every_historical_detection_uses_only_its_prefix(monkeypatch):
    calls = []

    def spy(history, *, as_of=None):
        calls.append((len(history.bars), as_of))
        return build_daily_patterns(history, as_of=as_of)

    monkeypatch.setattr(backtest, "build_daily_patterns", spy)
    evaluate([100] * 22 + [105, 106, 107, 100])
    assert [count for count, _ in calls[1:]] == list(range(1, 27))
    assert all(cutoff.tzinfo is not None for _, cutoff in calls)


def test_short_or_empty_history_has_no_fabricated_rate():
    history = make_history("TEST", [])
    result = backtest.build_daily_pattern_backtest(history)
    assert result.completed_bar_count == 0
    assert result.data_through is None
    for tested in result.results:
        for item in tested.horizons:
            assert item.status == "no_observations"
            assert item.baseline.reversal_rate_pct is None
            assert item.pattern.reversal_rate_pct is None


@pytest.mark.parametrize(
    "problem", ["unadjusted", "zero", "nan", "unordered", "duplicate", "intraday"]
)
def test_bad_input_is_rejected(problem):
    history = make_history("TEST", [100] * 30)
    if problem == "unadjusted":
        history.adjusted = False
    elif problem == "zero":
        history.bars[0].close = 0
    elif problem == "nan":
        history.bars[0].close = float("nan")
    elif problem == "unordered":
        history.bars.reverse()
    elif problem == "duplicate":
        history.bars.append(history.bars[-1])
    else:
        history.timeframe = "5Min"
    with pytest.raises(MarketDataError):
        backtest.build_daily_pattern_backtest(
            history, as_of=datetime(2026, 3, 1, tzinfo=timezone.utc)
        )


def test_api_fetches_once_and_returns_auditable_results(monkeypatch):
    calls = []

    def fetch(**kwargs):
        calls.append(kwargs)
        return make_history("NVDA", [100] * 22 + [105, 106, 107, 100, 99, 98, 99, 100])

    monkeypatch.setattr(backtest, "get_stock_history", fetch)
    client = TestClient(create_app())
    response = client.get("/stocks/NVDA/patterns/backtest?limit=100")
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 4
    assert data["latest_patterns"]["symbol"] == data["symbol"]
    assert data["latest_patterns"]["data_through"] == data["data_through"]
    assert data["latest_patterns"]["completed_bar_count"] == data["completed_bar_count"]
    assert data["results"][0]["horizons"][0]["outcomes"][0]["reversed"] is True
    assert calls == [
        {"symbol": "NVDA", "provider": "alpaca", "timeframe": "1Day", "limit": 100}
    ]
    assert client.get("/stocks/NVDA/patterns/backtest?limit=1000").status_code == 422


@pytest.mark.parametrize(
    "error,status",
    [
        (StockSymbolNotFoundError("unknown"), 404),
        (MarketDataRateLimitError("limited"), 429),
        (MarketDataError("bad data"), 502),
    ],
)
def test_api_provider_errors(monkeypatch, error, status):
    def fail(*args):
        raise error

    monkeypatch.setattr(stocks, "get_daily_pattern_backtest", fail)
    assert (
        TestClient(create_app()).get("/stocks/NVDA/patterns/backtest").status_code
        == status
    )
