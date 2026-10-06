from datetime import datetime, timezone

from app.api.schema.stock_research_data import (
    ResearchDataCoverageResponse,
    StockResearchDataResponse,
)
from app.api.services.stock_history_services import (
    get_stock_history,
    normalize_stock_symbol,
)
from app.api.services.stock_services import get_stock_quote
from app.clients.errors import StockSymbolNotFoundError


def collect_stock_research_data(
    symbol: str,
    benchmark_symbol: str,
    history_limit: int,
) -> StockResearchDataResponse:
    normalized_symbol = normalize_stock_symbol(symbol)
    normalized_benchmark = normalize_stock_symbol(benchmark_symbol)
    quote = get_stock_quote(normalized_symbol)

    if quote is None:
        raise StockSymbolNotFoundError(
            f"Stock symbol {normalized_symbol} was not found."
        )

    price_history = get_stock_history(
        symbol=normalized_symbol,
        provider="alpaca",
        timeframe="1Day",
        limit=history_limit,
    )
    benchmark_history = get_stock_history(
        symbol=normalized_benchmark,
        provider="alpaca",
        timeframe="1Day",
        limit=history_limit,
    )

    return StockResearchDataResponse(
        symbol=normalized_symbol,
        benchmark_symbol=normalized_benchmark,
        collected_at=_utc_timestamp(),
        quote=quote,
        price_history=price_history,
        benchmark_history=benchmark_history,
        coverage=ResearchDataCoverageResponse(
            latest_quote=True,
            adjusted_daily_ohlcv=True,
            benchmark_daily_ohlcv=True,
            fundamentals=False,
            news=False,
            options=False,
            macro=False,
        ),
        warnings=[
            *[f"Stock history: {warning}" for warning in price_history.warnings],
            *[
                f"Benchmark history: {warning}"
                for warning in benchmark_history.warnings
            ],
        ],
    )


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
