from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "ai-stock-intelligence-api"
    api_version: str = "0.1.0"
    app_env: str = "development"
    log_level: str = "info"
    backend_cors_origins: str = "http://localhost:5173"
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/stock_intelligence"
    )
    market_data_provider: str = "alpha_vantage"
    market_data_api_key: str | None = None
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_data_feed: str = "iex"
    alpaca_trading_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_base_url: str = "https://data.alpaca.markets"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    google_client_id: str | None = None
    auth_session_secret: str | None = None
    auth_cookie_name: str = "stock_intelligence_session"
    auth_cookie_secure: bool = False
    auth_session_days: int = 7
    require_auth: bool = False
    report_timezone: str = "Australia/Melbourne"

    @field_validator("report_timezone")
    @classmethod
    def valid_report_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("REPORT_TIMEZONE must be an IANA timezone") from error
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.backend_cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def google_auth_enabled(self) -> bool:
        return bool(self.google_client_id and self.auth_session_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
