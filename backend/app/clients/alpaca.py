import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.clients.errors import (
    MarketDataError,
    MarketDataRateLimitError,
    StockSymbolNotFoundError,
)
from app.core.config import settings


@dataclass(frozen=True)
class AlpacaBar:
    symbol: str
    close: float
    open: float | None
    high: float | None
    low: float | None
    volume: int | None
    timestamp: str | None


@dataclass(frozen=True)
class AlpacaHistoricalBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class AlpacaAsset:
    symbol: str
    name: str
    asset_class: str
    exchange: str
    status: str
    currency: str


@dataclass(frozen=True)
class AlpacaStockSnapshot:
    symbol: str
    latest_price: float | None
    latest_timestamp: str | None
    previous_close: float | None
    daily_open: float | None
    daily_high: float | None
    daily_low: float | None
    daily_volume: int | None


@dataclass(frozen=True)
class AlpacaScreenerMover:
    symbol: str
    price: float | None
    change: float | None
    percent_change: float | None


@dataclass(frozen=True)
class AlpacaStockMovers:
    gainers: list[AlpacaScreenerMover]
    losers: list[AlpacaScreenerMover]
    last_updated: str | None


@dataclass(frozen=True)
class AlpacaNewsArticle:
    headline: str
    summary: str
    url: str
    source: str
    created_at: str
    symbols: list[str]


class AlpacaClient:
    def get_latest_bar(self, symbol: str) -> AlpacaBar:
        normalized_symbol = symbol.strip().upper()
        payload = self._get_data_json(
            "/v2/stocks/bars/latest",
            {
                "symbols": normalized_symbol,
                "feed": settings.alpaca_data_feed,
            },
        )

        bars = payload.get("bars", {})
        bar = bars.get(normalized_symbol)

        if not bar:
            raise StockSymbolNotFoundError(f"Stock symbol {normalized_symbol} was not found.")

        close = _parse_required_float(bar.get("c"))

        return AlpacaBar(
            symbol=normalized_symbol,
            close=close,
            open=_parse_float(bar.get("o")),
            high=_parse_float(bar.get("h")),
            low=_parse_float(bar.get("l")),
            volume=_parse_int(bar.get("v")),
            timestamp=bar.get("t"),
        )

    def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        start: str,
        end: str,
        adjustment: str,
    ) -> list[AlpacaHistoricalBar]:
        normalized_symbol = symbol.strip().upper()
        encoded_symbol = quote(normalized_symbol, safe="")
        payload = self._get_data_json(
            f"/v2/stocks/{encoded_symbol}/bars",
            {
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": str(limit),
                "adjustment": adjustment,
                "feed": settings.alpaca_data_feed,
                "sort": "desc",
            },
        )
        raw_bars = payload.get("bars")

        if not isinstance(raw_bars, list) or not raw_bars:
            raise StockSymbolNotFoundError(
                f"No historical bars were found for stock symbol {normalized_symbol}."
            )

        bars = [
            AlpacaHistoricalBar(
                timestamp=_parse_required_string(bar.get("t"), "timestamp"),
                open=_parse_required_float(bar.get("o"), "open price"),
                high=_parse_required_float(bar.get("h"), "high price"),
                low=_parse_required_float(bar.get("l"), "low price"),
                close=_parse_required_float(bar.get("c"), "close price"),
                volume=_parse_required_int(bar.get("v")),
            )
            for bar in raw_bars
            if isinstance(bar, dict)
        ]
        bars.sort(key=lambda bar: bar.timestamp)

        return bars

    def get_stock_snapshots(
        self,
        symbols: list[str],
        feed: str | None = None,
    ) -> dict[str, AlpacaStockSnapshot]:
        normalized_symbols = list(
            dict.fromkeys(
                symbol.strip().upper()
                for symbol in symbols
                if symbol.strip()
            )
        )

        if not normalized_symbols:
            return {}

        payload = self._get_data_json(
            "/v2/stocks/snapshots",
            {
                "symbols": ",".join(normalized_symbols),
                "feed": feed or settings.alpaca_data_feed,
            },
        )
        raw_snapshots = payload.get("snapshots", payload)

        if not isinstance(raw_snapshots, dict):
            raise MarketDataError("Alpaca returned invalid stock snapshots.")

        snapshots: dict[str, AlpacaStockSnapshot] = {}

        for symbol in normalized_symbols:
            raw_snapshot = raw_snapshots.get(symbol)

            if not isinstance(raw_snapshot, dict):
                continue

            latest_trade = _mapping_or_empty(raw_snapshot.get("latestTrade"))
            minute_bar = _mapping_or_empty(raw_snapshot.get("minuteBar"))
            daily_bar = _mapping_or_empty(raw_snapshot.get("dailyBar"))
            previous_daily_bar = _mapping_or_empty(
                raw_snapshot.get("prevDailyBar")
            )
            latest_price = _first_float(
                latest_trade.get("p"),
                minute_bar.get("c"),
                daily_bar.get("c"),
            )
            latest_timestamp = _first_string(
                latest_trade.get("t"),
                minute_bar.get("t"),
                daily_bar.get("t"),
            )

            snapshots[symbol] = AlpacaStockSnapshot(
                symbol=symbol,
                latest_price=latest_price,
                latest_timestamp=latest_timestamp,
                previous_close=_parse_float(previous_daily_bar.get("c")),
                daily_open=_parse_float(daily_bar.get("o")),
                daily_high=_parse_float(daily_bar.get("h")),
                daily_low=_parse_float(daily_bar.get("l")),
                daily_volume=_parse_int(daily_bar.get("v")),
            )

        return snapshots

    def get_stock_movers(self, top: int = 20) -> AlpacaStockMovers:
        payload = self._get_data_json(
            "/v1beta1/screener/stocks/movers",
            {"top": str(top)},
        )

        return AlpacaStockMovers(
            gainers=_parse_screener_movers(payload.get("gainers")),
            losers=_parse_screener_movers(payload.get("losers")),
            last_updated=_first_string(
                payload.get("last_updated"),
                payload.get("updated_at"),
            ),
        )

    def get_market_news(
        self,
        start: str,
        end: str,
        limit: int = 50,
    ) -> list[AlpacaNewsArticle]:
        payload = self._get_data_json(
            "/v1beta1/news",
            {
                "start": start,
                "end": end,
                "sort": "desc",
                "limit": str(limit),
                "include_content": "false",
            },
        )
        raw_articles = payload.get("news", [])

        if not isinstance(raw_articles, list):
            raise MarketDataError("Alpaca returned invalid market news.")

        articles: list[AlpacaNewsArticle] = []

        for item in raw_articles:
            if not isinstance(item, dict):
                continue

            headline = _first_string(item.get("headline"))
            url = _first_string(item.get("url"))
            created_at = _first_string(item.get("created_at"), item.get("updated_at"))
            raw_symbols = item.get("symbols", [])

            if headline is None or url is None or created_at is None:
                continue

            symbols = [
                symbol.strip().upper()
                for symbol in raw_symbols
                if isinstance(symbol, str) and symbol.strip()
            ] if isinstance(raw_symbols, list) else []

            if not symbols:
                continue

            articles.append(
                AlpacaNewsArticle(
                    headline=headline,
                    summary=_first_string(item.get("summary")) or "",
                    url=url,
                    source=_first_string(item.get("source")) or "Alpaca News",
                    created_at=created_at,
                    symbols=symbols,
                )
            )

        return articles

    def list_assets(self) -> list[AlpacaAsset]:
        payload = self._get_trading_json(
            "/v2/assets",
            {
                "status": "active",
                "asset_class": "us_equity",
            },
        )

        if not isinstance(payload, list):
            raise MarketDataError("Alpaca returned invalid asset data.")

        return [
            AlpacaAsset(
                symbol=asset.get("symbol", ""),
                name=asset.get("name", ""),
                asset_class=asset.get("class", ""),
                exchange=asset.get("exchange", ""),
                status=asset.get("status", ""),
                currency="USD",
            )
            for asset in payload
            if asset.get("symbol") and asset.get("name")
        ]

    def _get_data_json(self, path: str, params: dict[str, str]) -> dict:
        url = _build_url(settings.alpaca_data_base_url, path, params)
        payload = self._get_json(url)

        if not isinstance(payload, dict):
            raise MarketDataError("Alpaca returned invalid market data.")

        return payload

    def _get_trading_json(self, path: str, params: dict[str, str]) -> dict | list:
        url = _build_url(settings.alpaca_trading_base_url, path, params)
        return self._get_json(url)

    def _get_json(self, url: str) -> dict | list:
        api_key = settings.alpaca_api_key
        secret_key = settings.alpaca_secret_key

        if not api_key or not secret_key:
            raise MarketDataError("Alpaca API credentials are not configured.")

        request = Request(
            url,
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
                "User-Agent": "ai-stock-intelligence-platform",
            },
        )

        try:
            with urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise _build_http_error(error) from error
        except (URLError, TimeoutError) as error:
            raise MarketDataError("Unable to reach Alpaca.") from error
        except json.JSONDecodeError as error:
            raise MarketDataError("Alpaca returned invalid JSON.") from error


def _build_url(base_url: str, path: str, params: dict[str, str]) -> str:
    query_params = urlencode(params)
    normalized_base_url = base_url.rstrip("/")

    return f"{normalized_base_url}{path}?{query_params}"


def _build_http_error(error: HTTPError) -> MarketDataError:
    if error.code == 401:
        return MarketDataError("Alpaca authentication failed.")

    if error.code == 403:
        return MarketDataError("Alpaca rejected this request for the current data plan.")

    if error.code == 429:
        return MarketDataRateLimitError(
            "Alpaca rate limit reached. Try again shortly."
        )

    if error.code == 404:
        return StockSymbolNotFoundError(
            "Alpaca did not find the requested stock symbol."
        )

    return MarketDataError(f"Alpaca request failed with status {error.code}.")


def _parse_required_float(value: object, field_name: str = "close price") -> float:
    parsed_value = _parse_float(value)

    if parsed_value is None:
        raise MarketDataError(f"Alpaca returned a bar without a valid {field_name}.")

    return parsed_value


def _parse_required_int(value: object) -> int:
    parsed_value = _parse_int(value)

    if parsed_value is None:
        raise MarketDataError("Alpaca returned a bar without valid volume.")

    return parsed_value


def _parse_required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise MarketDataError(f"Alpaca returned a bar without a valid {field_name}.")

    return value


def _parse_float(value: object) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: object) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mapping_or_empty(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _first_float(*values: object) -> float | None:
    for value in values:
        parsed_value = _parse_float(value)

        if parsed_value is not None:
            return parsed_value

    return None


def _first_string(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value

    return None


def _parse_screener_movers(value: object) -> list[AlpacaScreenerMover]:
    if not isinstance(value, list):
        return []

    movers: list[AlpacaScreenerMover] = []

    for item in value:
        if not isinstance(item, dict):
            continue

        symbol = _first_string(item.get("symbol"))

        if symbol is None:
            continue

        movers.append(
            AlpacaScreenerMover(
                symbol=symbol.upper(),
                price=_parse_float(item.get("price")),
                change=_parse_float(item.get("change")),
                percent_change=_first_float(
                    item.get("percent_change"),
                    item.get("change_percentage"),
                ),
            )
        )

    return movers
