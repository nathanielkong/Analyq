from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.api.services.chat_services import get_chat_session
from app.models.generation import GenerationRequest


class GenerationCancelled(Exception):
    pass


def register_generation(
    db: Session, session_id: UUID, request_id: UUID, user_id: UUID | None
) -> None:
    get_chat_session(db, session_id, user_id)
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    db.execute(
        insert(GenerationRequest)
        .values(id=request_id, session_id=session_id)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    db.commit()
    row = db.get(GenerationRequest, request_id)
    if row is None or row.session_id != session_id:
        raise ValueError("Request identifier belongs to another chat.")


def check_generation(db: Session, request_id: UUID) -> None:
    cancelled = db.scalar(
        select(GenerationRequest.cancelled_at).where(GenerationRequest.id == request_id)
    )
    if cancelled:
        raise GenerationCancelled("Generation stopped.")


def finish_generation(db: Session, request_id: UUID) -> None:
    # The update and chat commit share one transaction. Cancellation racing with
    # completion wins only if it acquired this row first; no late hidden answers.
    result = db.execute(
        update(GenerationRequest)
        .where(
            GenerationRequest.id == request_id, GenerationRequest.cancelled_at.is_(None)
        )
        .values(finished_at=datetime.now(UTC))
    )
    if not result.rowcount:
        raise GenerationCancelled("Generation stopped.")


def cancel_generation(
    db: Session, session_id: UUID, request_id: UUID, user_id: UUID | None
) -> str:
    register_generation(db, session_id, request_id, user_id)
    result = db.execute(
        update(GenerationRequest)
        .where(
            GenerationRequest.id == request_id, GenerationRequest.finished_at.is_(None)
        )
        .values(cancelled_at=datetime.now(UTC))
    )
    db.commit()
    return "stopped" if result.rowcount else "completed"
