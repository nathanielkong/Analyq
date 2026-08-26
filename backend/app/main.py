from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.service_name,
        version=settings.api_version,
    )
    app.include_router(health_router)
    return app


app = create_app()
