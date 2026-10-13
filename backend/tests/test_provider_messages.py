from app.clients.alpha_vantage import _build_provider_message_error
from app.clients.errors import MarketDataRateLimitError


def test_premium_message_does_not_expose_subscription_advertisement():
    error = _build_provider_message_error(
        "Thank you for using Alpha Vantage! This is a premium endpoint. "
        "Subscribe at https://www.alphavantage.co/premium/"
    )
    assert str(error) == "This data is not available on the current provider plan."


def test_rate_limit_keeps_its_error_type():
    assert isinstance(
        _build_provider_message_error("API call frequency exceeded"),
        MarketDataRateLimitError,
    )
