from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings

REPORT_FORMAT_VERSION = 3
REPORT_SECTIONS = (
    "Market report",
    "Market outlook",
    "Fundamentals",
    "Sentiment report",
    "News report",
    "Bull and bear case",
    "Investment plan",
    "Risk management",
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    # SQLite fixtures return naive timestamps; production PostgreSQL retains UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def report_day(now: datetime | None = None) -> str:
    return (
        as_utc(now or utc_now())
        .astimezone(ZoneInfo(settings.report_timezone))
        .date()
        .isoformat()
    )


def report_expiry(now: datetime) -> datetime:
    zone = ZoneInfo(settings.report_timezone)
    tomorrow = as_utc(now).astimezone(zone).date() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, zone).astimezone(UTC)


def snapshot_is_current(
    generated_at: datetime, expires_at: datetime | None, version: int, now: datetime
) -> bool:
    return bool(
        expires_at
        and version == REPORT_FORMAT_VERSION
        and as_utc(generated_at) <= as_utc(now) < as_utc(expires_at)
        and as_utc(expires_at) == report_expiry(generated_at)
        and report_day(generated_at) == report_day(now)
    )
