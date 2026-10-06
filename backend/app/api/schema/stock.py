from pydantic import BaseModel


class StockQuoteResponse(BaseModel):
    symbol: str
    company_name: str | None = None
    price: float
    currency: str
    change: float | None = None
    change_percent: float | None = None
    volume: int | None = None
    latest_trading_day: str | None = None
    previous_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    source: str


class StockSearchResultResponse(BaseModel):
    symbol: str
    name: str
    type: str
    region: str
    currency: str
    match_score: float | None = None
