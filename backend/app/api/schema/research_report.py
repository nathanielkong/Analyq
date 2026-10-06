from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.api.schema.assistant import (
    AssistantAnswerSection,
    AssistantExplanation,
    AssistantResearchResponse,
)
from app.api.schema.chat import ChatMessageResponse
from app.core.config import settings
from app.core.report_policy import REPORT_SECTIONS, as_utc, snapshot_is_current, utc_now


class DeepDiveSection(AssistantAnswerSection):
    label: Literal[
        "Market report",
        "Market outlook",
        "Fundamentals",
        "Sentiment report",
        "News report",
        "Bull and bear case",
        "Investment plan",
        "Risk management",
    ]


class DeepDiveExplanation(AssistantExplanation):
    sections: list[DeepDiveSection] = Field(min_length=8, max_length=8)

    @field_validator("sections")
    @classmethod
    def complete_report_sections(
        cls, sections: list[DeepDiveSection]
    ) -> list[DeepDiveSection]:
        if [section.label for section in sections] != list(REPORT_SECTIONS):
            raise ValueError("Report must contain the eight named sections in order")
        return sections


class ResearchChatRequest(BaseModel):
    session_id: UUID
    request_id: UUID
    message: str = Field(min_length=1, max_length=2_000)
    refresh_report_id: UUID | None = None
    context_report_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def nonempty_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value.strip()


class ReportNarrative(BaseModel):
    symbol: str
    explanation: DeepDiveExplanation


class ChatAnswerGeneration(BaseModel):
    answer: AssistantExplanation


class ResearchChatGeneration(ChatAnswerGeneration):
    reports: list[ReportNarrative] = Field(default_factory=list, max_length=5)


class ResearchReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    symbol: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    format_version: int = 0
    research: AssistantResearchResponse

    @field_validator("created_at", "updated_at", "expires_at")
    @classmethod
    def timezone_aware_timestamp(cls, value: datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None

    @computed_field
    @property
    def is_current(self) -> bool:
        return snapshot_is_current(
            self.updated_at, self.expires_at, self.format_version, utc_now()
        )

    @computed_field
    @property
    def report_timezone(self) -> str:
        return settings.report_timezone


class ResearchChatResponse(BaseModel):
    session_id: UUID
    message: ChatMessageResponse
    reports: list[ResearchReportResponse]
