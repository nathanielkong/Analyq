from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.schema.auth import (
    AuthConfigResponse,
    AuthUserResponse,
    GoogleLoginRequest,
    PasswordLoginRequest,
    PasswordRegisterRequest,
)
from app.api.services.auth_services import (
    GoogleAuthenticationError,
    authenticate_with_google,
    create_session_token,
    get_current_user,
)
from app.core.config import settings
from app.db.session import get_db_session
from app.models.user import User
from app.api.services.password_auth import (
    guard_password_request,
    register_password_account,
    authenticate_password,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config", response_model=AuthConfigResponse)
def get_auth_config() -> AuthConfigResponse:
    return AuthConfigResponse(
        password_enabled=bool(settings.auth_session_secret),
        google_enabled=settings.google_auth_enabled,
        google_client_id=(
            settings.google_client_id if settings.google_auth_enabled else None
        ),
    )


@router.post("/google", response_model=AuthUserResponse)
def login_with_google(
    login_data: GoogleLoginRequest,
    response: Response,
    db: Session = Depends(get_db_session),
) -> User:
    if not settings.google_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured.",
        )

    try:
        user = authenticate_with_google(db, login_data.credential)
    except GoogleAuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error

    set_session_cookie(response, user)
    return user


def set_session_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=create_session_token(user.id),
        max_age=settings.auth_session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthUserResponse, status_code=201)
def register_with_password(
    data: PasswordRegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
) -> User:
    guard_password_request(request, data.username)
    user = register_password_account(
        db, data.username, data.password.get_secret_value()
    )
    set_session_cookie(response, user)
    return user


@router.post("/login", response_model=AuthUserResponse)
def login_with_password(
    data: PasswordLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
) -> User:
    guard_password_request(request, data.username)
    user = authenticate_password(db, data.username, data.password.get_secret_value())
    set_session_cookie(response, user)
    return user


@router.get("/me", response_model=AuthUserResponse)
def get_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
