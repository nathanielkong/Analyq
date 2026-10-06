from pydantic import BaseModel


class StockHistoryBarResponse(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str


class StockHistoryResponse(BaseModel):
    symbol: str
    provider: str
    timeframe: str
    adjusted: bool
    requested_bar_count: int
    warnings: list[str]
    bars: list[StockHistoryBarResponse]
