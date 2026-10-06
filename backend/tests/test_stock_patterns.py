from datetime import datetime, timedelta, timezone
from statistics import fmean, stdev

import pytest
from fastapi.testclient import TestClient
from test_stock_analysis import make_history

from app.api.routes import stocks
from app.api.services import stock_pattern_services as patterns
from app.clients.errors import (
    MarketDataError,
    MarketDataRateLimitError,
    StockSymbolNotFoundError,
)
from app.main import create_app


def evaluate(closes):
    history = make_history("TEST", closes)
    day = datetime.fromisoformat(history.bars[-1].timestamp).replace(
        tzinfo=timezone.utc
    )
    return patterns.build_daily_patterns(
        history, as_of=day + timedelta(days=1, hours=12)
    )


def flags(result):
    return {check.name: check.detected for check in result.checks}


@pytest.mark.parametrize("sign", [1, -1])
def test_streak_and_rsi_both_sides(sign):
    result = evaluate([100 + sign * i for i in range(25)])
    assert result.signed_close_streak == sign * 24
    assert result.streak_reaches_history_start
    assert result.rsi_14 == (100 if sign == 1 else 0)
    assert flags(result)["rising_streak_high_rsi"] == (sign == 1)
    assert flags(result)["falling_streak_low_rsi"] == (sign == -1)


def test_three_changes_require_four_closes_and_flat_resets_streak():
    result = evaluate([100] * 20 + [101, 102, 103])
    assert result.signed_close_streak == 3
    assert flags(result)["rising_streak_high_rsi"] is True
    assert evaluate([100] * 20 + [101, 102]).signed_close_streak == 2
    flat = evaluate([100] * 20 + [101, 102, 102])
    assert flat.signed_close_streak == 0
    assert flags(flat)["rising_streak_high_rsi"] is False


def test_three_up_closes_alone_do_not_imply_high_rsi():
    result = evaluate([150 - i * 3 for i in range(20)] + [94, 95, 96])
    assert result.signed_close_streak == 3
    assert result.rsi_14 < 70
    assert flags(result)["rising_streak_high_rsi"] is False


@pytest.mark.parametrize("move", [8, -8])
def test_large_move_uses_only_twenty_prior_returns(move):
    prior_returns = [1.0, -1.0] * 10
    closes = [100.0]
    for change in prior_returns + [move]:
        closes.append(closes[-1] * (1 + change / 100))
    result = evaluate(closes)
    assert result.status == "available"
    assert result.prior_20_return_mean_pct == pytest.approx(
        fmean(prior_returns), abs=1e-10
    )
    assert result.prior_20_return_std_pct == pytest.approx(stdev(prior_returns))
    assert result.daily_return_zscore == pytest.approx(move / stdev(prior_returns))
    assert flags(result)["unusually_large_up_day"] == (move > 0)
    assert flags(result)["unusually_large_down_day"] == (move < 0)


def test_flat_baseline_and_short_history_are_unknown_not_false():
    flat = evaluate([100.0] * 22)
    assert flat.rsi_14 == 50
    assert flat.daily_return_zscore is None
    assert flags(flat)["unusually_large_up_day"] is None
    short = evaluate([100, 101, 102, 103])
    assert short.signed_close_streak == 3
    assert short.status == "insufficient_data"
    assert all(check.detected is None for check in short.checks)


def test_same_day_future_bars_excluded_and_historical_prefix_unchanged():
    history = make_history("TEST", [100 + i for i in range(25)])
    now = datetime(2026, 1, 25, 23, tzinfo=timezone.utc)
    expected = patterns.build_daily_patterns(
        history.model_copy(update={"bars": history.bars[:23]}), as_of=now
    )
    actual = patterns.build_daily_patterns(history, as_of=now)
    assert actual.completed_bar_count == 23
    assert actual.data_through == "2026-01-24"
    assert actual.signed_close_streak == expected.signed_close_streak
    assert actual.daily_return_zscore == expected.daily_return_zscore
    assert flags(actual) == flags(expected)


def test_market_timezone_not_utc_date_controls_completion():
    history = make_history("TEST", [100 + i for i in range(25)])
    now = datetime(2026, 1, 26, 1, tzinfo=timezone.utc)  # Still Jan 25 in New York.
    result = patterns.build_daily_patterns(history, as_of=now)
    assert result.data_through == "2026-01-24"


def test_stale_and_unadjusted_history_withhold_detection():
    history = make_history("TEST", [100 + i for i in range(25)])
    now = datetime(2026, 2, 10, 12, tzinfo=timezone.utc)
    stale = patterns.build_daily_patterns(history, as_of=now)
    assert stale.status == "stale"
    assert all(check.detected is None for check in stale.checks)
    unadjusted = patterns.build_daily_patterns(
        history.model_copy(update={"adjusted": False}), as_of=now
    )
    assert unadjusted.status == "unadjusted"
    assert all(check.detected is None for check in unadjusted.checks)


@pytest.mark.parametrize("close", [0, -1, float("nan"), float("inf")])
def test_invalid_closes_fail(close):
    with pytest.raises(MarketDataError, match="finite and positive"):
        evaluate([100] * 24 + [close])


@pytest.mark.parametrize(
    "problem", ["duplicate", "unordered", "timestamp", "timeframe"]
)
def test_bad_history_fails(problem):
    history = make_history("TEST", [100 + i for i in range(25)])
    if problem == "duplicate":
        history.bars.append(history.bars[-1])
    elif problem == "unordered":
        history.bars.reverse()
    elif problem == "timestamp":
        history.bars[-1].timestamp = "2026-01-26T12:00:00"  # Ambiguous timezone.
    else:
        history.timeframe = "5Min"
    with pytest.raises(MarketDataError):
        patterns.build_daily_patterns(history)


def test_patterns_endpoint_reuses_history_client_without_llm(monkeypatch):
    calls = []

    def get_history(**kwargs):
        calls.append(kwargs)
        return make_history("NVDA", [100 + i for i in range(25)])

    monkeypatch.setattr(patterns, "get_stock_history", get_history)
    response = TestClient(create_app()).get("/stocks/NVDA/patterns?limit=30")
    assert response.status_code == 200
    assert response.json()["symbol"] == "NVDA"
    assert len(response.json()["checks"]) == 4
    assert calls == [
        {"symbol": "NVDA", "provider": "alpaca", "timeframe": "1Day", "limit": 30}
    ]
    assert (
        TestClient(create_app()).get("/stocks/NVDA/patterns?limit=2").status_code == 422
    )


@pytest.mark.parametrize(
    "error,status",
    [
        (StockSymbolNotFoundError("missing"), 404),
        (MarketDataRateLimitError("limit"), 429),
        (MarketDataError("provider"), 502),
    ],
)
def test_patterns_endpoint_maps_provider_errors(monkeypatch, error, status):
    def fail(*args):
        raise error

    monkeypatch.setattr(stocks, "get_daily_patterns", fail)
    assert TestClient(create_app()).get("/stocks/NVDA/patterns").status_code == status
