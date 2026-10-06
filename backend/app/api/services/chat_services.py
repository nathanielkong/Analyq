from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schema.chat import ChatMessageCreate
from app.models.chat import ChatMessage, ChatSession


class ChatSessionNotFoundError(Exception):
    pass


def create_chat_session(
    db: Session,
    title: str,
    user_id: UUID | None = None,
) -> ChatSession:
    session = ChatSession(title=title.strip(), user_id=user_id)

    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def list_chat_sessions(
    db: Session,
    user_id: UUID | None = None,
) -> list[ChatSession]:
    statement = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
    )

    return list(db.scalars(statement).all())


def get_chat_session(
    db: Session,
    session_id: UUID,
    user_id: UUID | None = None,
) -> ChatSession:
    session = db.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )

    if session is None:
        raise ChatSessionNotFoundError

    return session


def create_chat_message(
    db: Session,
    session_id: UUID,
    message_data: ChatMessageCreate,
    user_id: UUID | None = None,
) -> ChatMessage:
    session = get_chat_session(db, session_id, user_id)
    message = ChatMessage(
        session_id=session.id,
        role=message_data.role,
        content=message_data.content,
        message_metadata=message_data.message_metadata,
    )

    session.updated_at = datetime.now(UTC)
    db.add(message)
    db.commit()
    db.refresh(message)

    return message


def list_chat_messages(
    db: Session,
    session_id: UUID,
    user_id: UUID | None = None,
) -> list[ChatMessage]:
    get_chat_session(db, session_id, user_id)
    statement = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )

    return list(db.scalars(statement).all())


def delete_chat_session(
    db: Session,
    session_id: UUID,
    user_id: UUID | None = None,
) -> None:
    session = get_chat_session(db, session_id, user_id)

    db.delete(session)
    db.commit()
