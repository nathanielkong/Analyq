class MarketDataError(Exception):
    """Raised when a market data provider cannot return a usable response."""


class MarketDataRateLimitError(MarketDataError):
    """Raised when a market data provider rejects a request due to its quota."""


class StockSymbolNotFoundError(MarketDataError):
    """Raised when a provider does not recognize the requested stock symbol."""
