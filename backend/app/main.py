from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.auth import router as auth_router
from app.api.routes.assistant import router as assistant_router
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.market import router as market_router
from app.api.routes.stocks import router as stocks_router
from app.core.config import settings
from app.api.services.auth_services import get_current_user


def create_app() -> FastAPI:
    if settings.require_auth and (
        not settings.auth_session_secret or len(settings.auth_session_secret) < 32
    ):
        raise ValueError(
            "REQUIRE_AUTH needs an AUTH_SESSION_SECRET of at least 32 characters"
        )
    app = FastAPI(
        title=settings.service_name,
        version=settings.api_version,
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # Authentication inputs must never be echoed in an error response.
        if request.url.path.startswith("/auth/"):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": [
                        {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
                        for item in error.errors()
                    ]
                },
            )
        return await request_validation_exception_handler(request, error)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    protected = [Depends(get_current_user)] if settings.require_auth else []
    app.include_router(market_router, dependencies=protected)
    app.include_router(stocks_router, dependencies=protected)
    app.include_router(chat_router, dependencies=protected)
    app.include_router(assistant_router, dependencies=protected)

    return app


app = create_app()
