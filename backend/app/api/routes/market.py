from fastapi import APIRouter, HTTPException, Query

from app.api.schema.market_watch import MarketWatchResponse
from app.api.schema.peer_comparison import PeerComparisonRequest, PeerComparisonResponse
from app.api.services.market_watch_services import get_market_watch
from app.api.services.peer_comparison_services import compare_fundamentals
from app.api.services.stock_fundamentals_services import get_stock_fundamentals
from app.api.services.stock_history_services import normalize_stock_symbol
from app.clients.errors import MarketDataError, MarketDataRateLimitError

router = APIRouter(prefix="/market", tags=["market"])


@router.post("/rank", response_model=PeerComparisonResponse)
def rank_watchlist(request: PeerComparisonRequest) -> PeerComparisonResponse:
    try:
        symbols = list(
            dict.fromkeys(normalize_stock_symbol(symbol) for symbol in request.symbols)
        )
        if len(symbols) < 2:
            raise HTTPException(
                status_code=422, detail="Choose at least two different symbols."
            )
        return compare_fundamentals(
            [get_stock_fundamentals(symbol) for symbol in symbols], request.preset
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/watch", response_model=MarketWatchResponse)
def get_stocks_to_watch(
    limit: int = Query(8, ge=3, le=12),
) -> MarketWatchResponse:
    try:
        return get_market_watch(limit=limit)
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
