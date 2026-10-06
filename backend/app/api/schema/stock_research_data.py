from pydantic import BaseModel

from app.api.schema.stock import StockQuoteResponse
from app.api.schema.stock_history import StockHistoryResponse


class ResearchDataCoverageResponse(BaseModel):
    latest_quote: bool
    adjusted_daily_ohlcv: bool
    benchmark_daily_ohlcv: bool
    fundamentals: bool
    news: bool
    options: bool
    macro: bool


class StockResearchDataResponse(BaseModel):
    symbol: str
    benchmark_symbol: str
    collected_at: str
    quote: StockQuoteResponse
    price_history: StockHistoryResponse
    benchmark_history: StockHistoryResponse
    coverage: ResearchDataCoverageResponse
    warnings: list[str]
