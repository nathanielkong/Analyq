from time import monotonic

from app.clients.alpaca import AlpacaAsset, AlpacaClient
from app.clients.alpha_vantage import AlphaVantageClient
from app.api.schema.stock import StockQuoteResponse, StockSearchResultResponse
from app.api.services.ttl_cache import TTLCache
from app.core.report_policy import report_day
from app.core.config import settings


SEARCH_CACHE_TTL_SECONDS = 300
ASSET_CACHE_TTL_SECONDS = 3600
QUOTE_CACHE_TTL_SECONDS = 30
_search_cache: dict[str, tuple[float, list[StockSearchResultResponse]]] = {}
_asset_cache: tuple[float, list[AlpacaAsset]] | None = None
_quote_cache: TTLCache[tuple[str, ...], StockQuoteResponse] = TTLCache(
    ttl_seconds=QUOTE_CACHE_TTL_SECONDS
)


def get_stock_quote(symbol: str) -> StockQuoteResponse | None:
    normalized_symbol = symbol.strip().upper()

    if not normalized_symbol:
        return None

    provider = settings.market_data_provider.lower()
    cache_key = (provider, normalized_symbol, settings.alpaca_data_feed, report_day())
    cached_quote = _quote_cache.get(cache_key)

    if cached_quote is not None:
        return cached_quote

    if provider == "alpaca":
        quote = _get_alpaca_stock_quote(normalized_symbol)
    else:
        quote = _get_alpha_vantage_stock_quote(normalized_symbol)

    _quote_cache.set(cache_key, quote)

    return quote


def _get_alpha_vantage_stock_quote(symbol: str) -> StockQuoteResponse:
    quote = AlphaVantageClient().get_quote(symbol)

    return StockQuoteResponse(
        symbol=quote.symbol,
        company_name=None,
        price=quote.price,
        currency="USD",
        change=quote.change,
        change_percent=quote.change_percent,
        volume=quote.volume,
        latest_trading_day=quote.latest_trading_day,
        previous_close=quote.previous_close,
        open=quote.open,
        high=quote.high,
        low=quote.low,
        source="Alpha Vantage",
    )


def _get_alpaca_stock_quote(symbol: str) -> StockQuoteResponse:
    client = AlpacaClient()
    snapshot = client.get_stock_snapshots([symbol]).get(symbol)
    if snapshot is None or snapshot.latest_price is None or snapshot.latest_price <= 0:
        from app.clients.errors import StockSymbolNotFoundError

        raise StockSymbolNotFoundError(f"No price snapshot is available for {symbol}.")
    asset = _find_alpaca_asset_by_symbol(symbol)
    previous = snapshot.previous_close
    change = (
        snapshot.latest_price - previous
        if previous is not None and previous > 0
        else None
    )

    return StockQuoteResponse(
        symbol=symbol,
        company_name=asset.name if asset else None,
        price=snapshot.latest_price,
        currency=asset.currency if asset else "USD",
        change=round(change, 4) if change is not None else None,
        change_percent=round(change / previous * 100, 4)
        if change is not None
        else None,
        volume=snapshot.daily_volume,
        latest_trading_day=snapshot.latest_timestamp,
        previous_close=previous,
        open=snapshot.daily_open,
        high=snapshot.daily_high,
        low=snapshot.daily_low,
        source=f"Alpaca ({settings.alpaca_data_feed.upper()})",
    )


def search_stocks(query: str) -> list[StockSearchResultResponse]:
    normalized_query = query.strip()

    if not normalized_query:
        return []

    cache_key = normalized_query.lower()
    cached_result = _search_cache.get(cache_key)
    current_time = monotonic()

    if cached_result is not None:
        cached_at, cached_matches = cached_result

        if current_time - cached_at < SEARCH_CACHE_TTL_SECONDS:
            return cached_matches

    if settings.market_data_provider.lower() == "alpaca":
        matches = _search_alpaca_stocks(normalized_query)
    else:
        matches = _search_alpha_vantage_stocks(normalized_query)

    matches.sort(key=lambda match: _stock_search_sort_key(match, normalized_query))

    _search_cache[cache_key] = (current_time, matches)

    return matches


def _search_alpha_vantage_stocks(query: str) -> list[StockSearchResultResponse]:
    client = AlphaVantageClient()
    results = client.search_symbols(query)

    return [
        StockSearchResultResponse(
            symbol=result.symbol,
            name=result.name,
            type=result.type,
            region=result.region,
            currency=result.currency,
            match_score=result.match_score,
        )
        for result in results
    ]


def _search_alpaca_stocks(query: str) -> list[StockSearchResultResponse]:
    normalized_query = _normalize_for_search_rank(query)
    assets = _get_cached_alpaca_assets()
    matches = [
        StockSearchResultResponse(
            symbol=asset.symbol,
            name=asset.name,
            type="Equity",
            region="United States",
            currency=asset.currency,
            match_score=_score_alpaca_asset_match(asset, normalized_query),
        )
        for asset in assets
        if _alpaca_asset_matches(asset, normalized_query)
    ]

    return matches[:25]


def _get_cached_alpaca_assets() -> list[AlpacaAsset]:
    global _asset_cache

    current_time = monotonic()

    if _asset_cache is not None:
        cached_at, cached_assets = _asset_cache

        if current_time - cached_at < ASSET_CACHE_TTL_SECONDS:
            return cached_assets

    assets = AlpacaClient().list_assets()
    _asset_cache = (current_time, assets)

    return assets


def _find_alpaca_asset_by_symbol(symbol: str) -> AlpacaAsset | None:
    normalized_symbol = symbol.upper()

    return next(
        (
            asset
            for asset in _get_cached_alpaca_assets()
            if asset.symbol.upper() == normalized_symbol
        ),
        None,
    )


def _alpaca_asset_matches(asset: AlpacaAsset, normalized_query: str) -> bool:
    normalized_symbol = _normalize_for_search_rank(asset.symbol)
    normalized_name = _normalize_for_search_rank(asset.name)

    return normalized_query in normalized_symbol or normalized_query in normalized_name


def _score_alpaca_asset_match(asset: AlpacaAsset, normalized_query: str) -> float:
    normalized_symbol = _normalize_for_search_rank(asset.symbol)
    normalized_name = _normalize_for_search_rank(asset.name)

    if normalized_symbol == normalized_query:
        return 1.0

    if normalized_name.startswith(normalized_query):
        return 0.9

    if normalized_symbol.startswith(normalized_query):
        return 0.8

    return 0.5


def _stock_search_sort_key(
    match: StockSearchResultResponse,
    query: str,
) -> tuple[int, int, int, int, float, str]:
    normalized_query = _normalize_for_search_rank(query)
    normalized_name = _normalize_for_search_rank(match.name)
    normalized_symbol = _normalize_for_search_rank(match.symbol)
    is_exact_symbol = normalized_symbol == normalized_query
    name_starts_with_query = normalized_name.startswith(normalized_query)
    is_equity = match.type.lower() == "equity"
    is_us_market = match.region.lower() == "united states"

    return (
        0 if is_exact_symbol else 1,
        0 if name_starts_with_query else 1,
        0 if is_equity else 1,
        0 if is_us_market else 1,
        -(match.match_score or 0),
        match.symbol,
    )


def _normalize_for_search_rank(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())
