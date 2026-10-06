from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.api.schema.stock import StockQuoteResponse, StockSearchResultResponse
from app.api.schema.stock_analysis import StockAnalysisResponse
from app.api.schema.stock_direction import StockOutlookResponse
from app.api.schema.stock_history import StockHistoryResponse
from app.api.schema.stock_patterns import DailyPatternsResponse
from app.api.services.stock_pattern_services import get_daily_patterns
from app.api.schema.pattern_backtest import DailyPatternBacktestResponse
from app.api.services.pattern_backtest_services import get_daily_pattern_backtest
from app.api.schema.stock_fundamentals import StockFundamentalsResponse
from app.api.schema.stock_news import StockNewsResponse
from app.api.schema.stock_research_data import StockResearchDataResponse
from app.api.services.stock_analysis_services import (
    StockAnalysisError,
    get_stock_analysis,
)
from app.api.services.stock_history_services import get_stock_history
from app.api.services.stock_fundamentals_services import get_stock_fundamentals
from app.api.services.stock_direction_services import (
    DirectionModelError,
    get_stock_outlook,
)
from app.api.services.stock_news_services import get_stock_news
from app.api.services.stock_research_data_services import collect_stock_research_data
from app.api.services.stock_services import get_stock_quote, search_stocks
from app.clients.errors import (
    MarketDataError,
    MarketDataRateLimitError,
    StockSymbolNotFoundError,
)


router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/search", response_model=list[StockSearchResultResponse])
def search_stock_symbols(
    query: str = Query(min_length=2, max_length=80),
) -> list[StockSearchResultResponse]:
    try:
        return search_stocks(query)
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/{symbol}/analysis", response_model=StockAnalysisResponse)
def get_stock_price_analysis(
    symbol: str,
    provider: Literal["alpaca"] = Query("alpaca"),
    timeframe: Literal["1Day"] = Query("1Day"),
    mode: Literal["historical"] = Query("historical"),
    limit: int = Query(100, ge=30, le=250),
) -> StockAnalysisResponse:
    try:
        return get_stock_analysis(
            symbol=symbol,
            provider=provider,
            timeframe=timeframe,
            mode=mode,
            limit=limit,
        )
    except StockSymbolNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except StockAnalysisError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/{symbol}/patterns", response_model=DailyPatternsResponse)
def get_stock_daily_patterns(
    symbol: str,
    limit: int = Query(100, ge=22, le=250),
) -> DailyPatternsResponse:
    try:
        return get_daily_patterns(symbol, limit)
    except StockSymbolNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/{symbol}/patterns/backtest", response_model=DailyPatternBacktestResponse)
def backtest_stock_daily_patterns(
    symbol: str,
    limit: int = Query(250, ge=22, le=250),
) -> DailyPatternBacktestResponse:
    try:
        return get_daily_pattern_backtest(symbol, limit)
    except StockSymbolNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/{symbol}/fundamentals", response_model=StockFundamentalsResponse)
def get_stock_company_fundamentals(symbol: str) -> StockFundamentalsResponse:
    try:
        return get_stock_fundamentals(symbol)
    except StockSymbolNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/{symbol}/news", response_model=StockNewsResponse)
def get_stock_company_news(
    symbol: str,
    days: int = Query(30, ge=1, le=3650),
    limit: int = Query(100, ge=50, le=1000),
) -> StockNewsResponse:
    try:
        return get_stock_news(symbol=symbol, days=days, limit=limit)
    except StockSymbolNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/{symbol}/outlook", response_model=StockOutlookResponse)
def get_stock_direction_outlook(
    symbol: str,
    benchmark: str = Query("SPY", min_length=1, max_length=14),
    history_limit: int = Query(250, ge=100, le=250),
    news_days: int = Query(180, ge=30, le=3650),
    news_limit: int = Query(1000, ge=50, le=1000),
) -> StockOutlookResponse:
    try:
        return get_stock_outlook(
            symbol=symbol,
            benchmark_symbol=benchmark,
            history_limit=history_limit,
            news_days=news_days,
            news_limit=news_limit,
        )
    except StockSymbolNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DirectionModelError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/{symbol}/research-data", response_model=StockResearchDataResponse)
def get_stock_research_data(
    symbol: str,
    benchmark: str = Query("SPY", min_length=1, max_length=14),
    history_limit: int = Query(100, ge=30, le=250),
) -> StockResearchDataResponse:
    try:
        return collect_stock_research_data(
            symbol=symbol,
            benchmark_symbol=benchmark,
            history_limit=history_limit,
        )
    except StockSymbolNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/{symbol}/history", response_model=StockHistoryResponse)
def get_stock_price_history(
    symbol: str,
    provider: Literal["alpaca"] = Query("alpaca"),
    timeframe: Literal["1Day"] = Query("1Day"),
    limit: int = Query(100, ge=1, le=250),
) -> StockHistoryResponse:
    try:
        return get_stock_history(
            symbol=symbol,
            provider=provider,
            timeframe=timeframe,
            limit=limit,
        )
    except StockSymbolNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/{symbol}", response_model=StockQuoteResponse)
def get_stock(symbol: str) -> StockQuoteResponse:
    try:
        stock = get_stock_quote(symbol)
    except StockSymbolNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    if stock is None:
        raise HTTPException(status_code=404, detail="Stock symbol not found")

    return stock
