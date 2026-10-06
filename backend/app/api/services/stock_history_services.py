import re
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app.api.schema.stock_history import (
    StockHistoryBarResponse,
    StockHistoryResponse,
)
from app.api.services.ttl_cache import TTLCache
from app.core.report_policy import report_day
from app.clients.alpaca import AlpacaClient, AlpacaHistoricalBar
from app.clients.errors import MarketDataError, StockSymbolNotFoundError
from app.core.config import settings


HistoryProvider = Literal["alpaca"]
HistoryTimeframe = Literal["1Day"]
ALPACA_ADJUSTMENT = "all"
EXTREME_DAILY_MOVE_THRESHOLD = 0.35
STALE_AFTER_CALENDAR_DAYS = 7
MIN_EXPECTED_BAR_RATIO = 0.9
HISTORY_CACHE_TTL_SECONDS = 900
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{1,10}(?:[.-][A-Z0-9]{1,3})?$")
_history_cache: TTLCache[tuple[str, ...], StockHistoryResponse] = TTLCache(
    ttl_seconds=HISTORY_CACHE_TTL_SECONDS
)


def get_stock_history(
    symbol: str,
    provider: HistoryProvider,
    timeframe: HistoryTimeframe,
    limit: int,
) -> StockHistoryResponse:
    normalized_symbol = normalize_stock_symbol(symbol)
    today = _current_market_date()
    end_date = today - timedelta(days=1)
    start_date = end_date - timedelta(days=max(90, (limit * 2) + 30))
    cache_key = (
        report_day(),
        normalized_symbol,
        provider,
        timeframe,
        str(limit),
        end_date.isoformat(),
        ALPACA_ADJUSTMENT,
        settings.alpaca_data_feed,
    )
    cached_history = _history_cache.get(cache_key)

    if cached_history is not None:
        return cached_history

    bars = AlpacaClient().get_historical_bars(
        symbol=normalized_symbol,
        timeframe=timeframe,
        limit=limit,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        adjustment=ALPACA_ADJUSTMENT,
    )
    warnings = validate_historical_bars(
        bars=bars,
        requested_bar_count=limit,
        today=today,
    )

    history = StockHistoryResponse(
        symbol=normalized_symbol,
        provider=provider,
        timeframe=timeframe,
        adjusted=True,
        requested_bar_count=limit,
        warnings=warnings,
        bars=[
            StockHistoryBarResponse(
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                source=f"Alpaca ({settings.alpaca_data_feed.upper()}, adjusted)",
            )
            for bar in bars
        ],
    )
    _history_cache.set(cache_key, history)

    return history


def normalize_stock_symbol(symbol: str) -> str:
    candidate = symbol.strip().upper()

    if not candidate or not SYMBOL_PATTERN.fullmatch(candidate):
        raise StockSymbolNotFoundError(
            "Stock symbol format is invalid. Use letters or numbers with an optional "
            "class suffix, such as BRK.B."
        )

    return candidate.replace("-", ".")


def validate_historical_bars(
    bars: list[AlpacaHistoricalBar],
    requested_bar_count: int,
    today: date,
) -> list[str]:
    if not bars:
        raise MarketDataError("The market-data provider returned no historical bars.")

    timestamps = [bar.timestamp for bar in bars]

    if len(timestamps) != len(set(timestamps)):
        raise MarketDataError("Historical bars contain duplicate timestamps.")

    if timestamps != sorted(timestamps):
        raise MarketDataError("Historical bars are not ordered from oldest to newest.")

    bar_dates: list[date] = []

    for bar in bars:
        bar_date = _parse_bar_date(bar.timestamp)
        bar_dates.append(bar_date)

        if bar.low <= 0 or bar.high <= 0 or bar.open <= 0 or bar.close <= 0:
            raise MarketDataError("Historical bars must contain positive prices.")

        if bar.high < bar.low:
            raise MarketDataError("Historical bar high price is below its low price.")

        if not bar.low <= bar.open <= bar.high:
            raise MarketDataError(
                "Historical bar open price is outside its high-low range."
            )

        if not bar.low <= bar.close <= bar.high:
            raise MarketDataError(
                "Historical bar close price is outside its high-low range."
            )

        if bar.volume < 0:
            raise MarketDataError("Historical bar volume cannot be negative.")

    warnings: list[str] = []
    minimum_expected = max(1, int(requested_bar_count * MIN_EXPECTED_BAR_RATIO))

    if len(bars) < minimum_expected:
        warnings.append(
            f"Received {len(bars)} of {requested_bar_count} requested daily bars; "
            "metrics use a shorter history."
        )

    age_in_days = (today - bar_dates[-1]).days

    if age_in_days > STALE_AFTER_CALENDAR_DAYS:
        warnings.append(
            f"Newest historical bar is {age_in_days} calendar days old; data may be stale."
        )

    for previous_bar, current_bar in zip(bars, bars[1:]):
        daily_return = (current_bar.close / previous_bar.close) - 1

        if abs(daily_return) >= EXTREME_DAILY_MOVE_THRESHOLD:
            warnings.append(
                f"Detected a {daily_return * 100:.1f}% close-to-close move on "
                f"{current_bar.timestamp[:10]}; verify corporate-action adjustment "
                "and data quality."
            )

    return warnings


def _parse_bar_date(timestamp: str) -> date:
    try:
        return date.fromisoformat(timestamp[:10])
    except ValueError as error:
        raise MarketDataError(
            f"Historical bar timestamp {timestamp!r} is invalid."
        ) from error


def _current_market_date() -> date:
    return datetime.now(ZoneInfo("America/New_York")).date()
