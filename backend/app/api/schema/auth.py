from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class AuthConfigResponse(BaseModel):
    password_enabled: bool = False
    google_enabled: bool
    google_client_id: str | None


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=10_000)


class PasswordLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()


class PasswordRegisterRequest(PasswordLoginRequest):
    password: SecretStr = Field(min_length=15, max_length=128)


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None
    username: str | None = None
    display_name: str
    avatar_url: str | None
    created_at: datetime
