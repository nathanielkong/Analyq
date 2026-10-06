from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schema.assistant import AssistantPromptRequest, AssistantResearchResponse
from app.api.schema.research_report import (
    ResearchChatRequest,
    ResearchChatResponse,
    ResearchReportResponse,
)
from app.api.services.assistant_services import (
    AssistantRequestError,
    research_stock_prompt,
)
from app.api.services.auth_services import get_optional_current_user
from app.api.services.chat_services import (
    ChatSessionNotFoundError,
    list_chat_messages,
)
from app.api.services.research_report_services import (
    answer_research_chat,
    list_research_reports,
)
from app.clients.errors import (
    MarketDataError,
    MarketDataRateLimitError,
    StockSymbolNotFoundError,
)
from app.clients.gemini import GeminiClientError
from app.db.session import get_db_session
from app.models.chat import ChatMessage
from app.models.user import User
from app.api.services.generation_control import (
    GenerationCancelled,
    register_generation,
    check_generation,
    finish_generation,
    cancel_generation,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get(
    "/sessions/{session_id}/reports", response_model=list[ResearchReportResponse]
)
def get_reports(
    session_id: UUID,
    db: Session = Depends(get_db_session),
    user: User | None = Depends(get_optional_current_user),
) -> list[ResearchReportResponse]:
    try:
        return list_research_reports(db, session_id, user.id if user else None)
    except ChatSessionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Chat session not found") from error


@router.post("/chat", response_model=ResearchChatResponse)
def chat_with_reports(
    request: ResearchChatRequest,
    db: Session = Depends(get_db_session),
    user: User | None = Depends(get_optional_current_user),
) -> ResearchChatResponse:
    try:
        register_generation(
            db, request.session_id, request.request_id, user.id if user else None
        )
        return answer_research_chat(
            db,
            request,
            user.id if user else None,
            check_cancelled=lambda: check_generation(db, request.request_id),
            finish=lambda: finish_generation(db, request.request_id),
        )
    except GenerationCancelled as error:
        db.rollback()
        raise HTTPException(409, detail=str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(400, detail=str(error)) from error
    except ChatSessionNotFoundError as error:
        db.rollback()
        raise HTTPException(status_code=404, detail="Chat session not found") from error
    except AssistantRequestError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    except StockSymbolNotFoundError as error:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        db.rollback()
        raise HTTPException(status_code=429, detail=str(error)) from error
    except GeminiClientError as error:
        db.rollback()
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except MarketDataError as error:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/sessions/{session_id}/requests/{request_id}/cancel")
def stop_generation(
    session_id: UUID,
    request_id: UUID,
    db: Session = Depends(get_db_session),
    user: User | None = Depends(get_optional_current_user),
) -> dict[str, str]:
    try:
        return {
            "status": cancel_generation(
                db, session_id, request_id, user.id if user else None
            )
        }
    except ChatSessionNotFoundError as error:
        raise HTTPException(404, "Chat session not found") from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/research", response_model=AssistantResearchResponse)
def research_from_prompt(
    request: AssistantPromptRequest,
    db: Session = Depends(get_db_session),
    user: User | None = Depends(get_optional_current_user),
) -> AssistantResearchResponse:
    try:
        conversation_context: list[dict[str, object]] = []

        if request.session_id is not None:
            messages = list_chat_messages(
                db,
                request.session_id,
                user.id if user else None,
            )
            conversation_context = _build_conversation_context(messages)

        return research_stock_prompt(
            request.message,
            conversation_context=conversation_context,
        )
    except ChatSessionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Chat session not found") from error
    except AssistantRequestError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except StockSymbolNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except MarketDataRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except GeminiClientError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


def _build_conversation_context(
    messages: list[ChatMessage],
) -> list[dict[str, object]]:
    context: list[dict[str, object]] = []

    for message in messages[-8:]:
        context_item: dict[str, object] = {
            "role": message.role,
            "content": message.content[:1_000],
        }
        stock = message.message_metadata.get("stock")

        if isinstance(stock, dict):
            symbol = stock.get("symbol")
            name = stock.get("name")

            if isinstance(symbol, str):
                context_item["stock_symbol"] = symbol

            if isinstance(name, str):
                context_item["stock_name"] = name

        context.append(context_item)

    return context
