from hashlib import blake2b
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.report_policy import as_utc, snapshot_is_current, utc_now
from app.models.research_report import DailyResearchCache, ResearchReport


def cache_scope(user_id: UUID | None, session_id: UUID) -> str:
    return f"user:{user_id}" if user_id else f"chat:{session_id}"


def lock_report_generation(db: Session, scope: str) -> None:
    # Unlike a chat lock, this serializes first-time requests across two chats.
    # Transaction-scoped advisory locks also cover a cache row that does not exist yet.
    if db.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(
            blake2b(scope.encode(), digest_size=8).digest(), "big", signed=True
        )
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    # Lazy expiry cleanup is serialized within this account. Historical chat
    # snapshots are intentionally separate and remain readable with a stale label.
    db.execute(
        delete(DailyResearchCache)
        .where(
            DailyResearchCache.scope == scope,
            DailyResearchCache.expires_at <= utc_now(),
        )
        .execution_options(synchronize_session="fetch")
    )


def load_daily_report(
    db: Session, scope: str, symbol: str
) -> DailyResearchCache | None:
    cached = db.scalar(
        select(DailyResearchCache)
        .where(DailyResearchCache.scope == scope, DailyResearchCache.symbol == symbol)
        .execution_options(populate_existing=True)
    )
    if cached and snapshot_is_current(
        cached.generated_at, cached.expires_at, cached.format_version, utc_now()
    ):
        return cached
    return None


def store_daily_report(db: Session, scope: str, report: ResearchReport) -> None:
    cached = db.get(DailyResearchCache, (scope, report.symbol))
    if cached is None:
        cached = DailyResearchCache(scope=scope, symbol=report.symbol)
        db.add(cached)
    elif as_utc(cached.generated_at) > as_utc(report.updated_at):
        return
    cached.research = report.research
    cached.generated_at = report.updated_at
    cached.expires_at = report.expires_at
    cached.format_version = report.format_version
