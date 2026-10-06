from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.services.auth_services import get_optional_current_user
from app.api.schema.chat import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
)
from app.api.services.chat_services import (
    ChatSessionNotFoundError,
    create_chat_message,
    create_chat_session,
    delete_chat_session,
    list_chat_messages,
    list_chat_sessions,
)
from app.db.session import get_db_session
from app.models.user import User


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    session_data: ChatSessionCreate,
    db: Session = Depends(get_db_session),
    user: User | None = Depends(get_optional_current_user),
) -> ChatSessionResponse:
    return create_chat_session(db, session_data.title, user.id if user else None)


@router.get("/sessions", response_model=list[ChatSessionResponse])
def get_sessions(
    db: Session = Depends(get_db_session),
    user: User | None = Depends(get_optional_current_user),
) -> list[ChatSessionResponse]:
    return list_chat_sessions(db, user.id if user else None)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_message(
    session_id: UUID,
    message_data: ChatMessageCreate,
    db: Session = Depends(get_db_session),
    user: User | None = Depends(get_optional_current_user),
) -> ChatMessageResponse:
    try:
        return create_chat_message(
            db,
            session_id,
            message_data,
            user.id if user else None,
        )
    except ChatSessionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Chat session not found") from error


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessageResponse],
)
def get_messages(
    session_id: UUID,
    db: Session = Depends(get_db_session),
    user: User | None = Depends(get_optional_current_user),
) -> list[ChatMessageResponse]:
    try:
        return list_chat_messages(db, session_id, user.id if user else None)
    except ChatSessionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Chat session not found") from error


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session(
    session_id: UUID,
    db: Session = Depends(get_db_session),
    user: User | None = Depends(get_optional_current_user),
) -> Response:
    try:
        delete_chat_session(db, session_id, user.id if user else None)
    except ChatSessionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Chat session not found") from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
