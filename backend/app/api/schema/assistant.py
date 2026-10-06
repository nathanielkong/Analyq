from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.schema.stock import StockQuoteResponse, StockSearchResultResponse
from app.api.schema.stock_analysis import StockAnalysisResponse
from app.api.schema.stock_direction import StockOutlookResponse
from app.api.schema.stock_history import StockHistoryResponse
from app.api.schema.stock_fundamentals import StockFundamentalsResponse
from app.api.schema.horizon_signals import HorizonSignal
from app.api.schema.stock_news import StockNewsResponse


AssistantIntent = Literal[
    "stock_research",
    "stock_comparison",
    "general_finance",
    "unrelated",
    "unclear",
]
RequestedStockData = Literal[
    "quote",
    "historical_analysis",
    "fundamentals",
    "news_sentiment",
    "direction_outlook",
]
ResearchTimeHorizon = Literal[
    "current",
    "short_term",
    "long_term",
    "unspecified",
]


class AssistantPromptRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)
    session_id: UUID | None = None


class StockPromptInterpretation(BaseModel):
    report_queries: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="For multi-stock requests only: identities copied from stock_queries for which the user explicitly requested separate full market analysis reports. Empty for ordinary comparison/ranking questions.",
    )
    ranking_preset: Literal["value", "growth", "quality"] = "quality"
    intent: AssistantIntent = Field(
        description="The category of request made by the user."
    )
    stock_queries: list[str] = Field(
        default_factory=list,
        max_length=5,
        description=(
            "Company names or verified stock tickers from the current message or "
            "recent conversation context, with request words removed."
        ),
    )
    requested_data: list[RequestedStockData] = Field(
        default_factory=list,
        max_length=5,
        description="Backend data operations needed to answer the request.",
    )
    time_horizon: ResearchTimeHorizon = Field(
        description="The investment or analysis horizon expressed by the user."
    )
    keywords: list[str] = Field(
        min_length=1,
        max_length=12,
        description=(
            "Important request concepts excluding company names, such as current "
            "price, volatility, news, risk, or bullish direction."
        ),
    )
    requires_clarification: bool = Field(
        description="Whether the backend needs more information before researching."
    )
    clarification_question: str = Field(
        default="",
        max_length=300,
        description="A short question to ask only when clarification is required.",
    )

    @model_validator(mode="after")
    def report_identities_are_requested(self) -> "StockPromptInterpretation":
        identities = {query.strip().casefold() for query in self.stock_queries}
        if any(
            query.strip().casefold() not in identities for query in self.report_queries
        ):
            raise ValueError("Report identities must also appear in stock_queries")
        return self


class AssistantAnswerSection(BaseModel):
    label: str = Field(
        min_length=1,
        max_length=50,
        description="A short tab label chosen for this specific analysis section.",
    )
    content: str = Field(
        min_length=1,
        max_length=5_000,
        description="Detailed Markdown analysis grounded in backend evidence.",
    )


class AssistantExplanation(BaseModel):
    visuals: list[Literal["price", "fundamentals", "news", "model"]] = Field(
        default_factory=list, max_length=2
    )
    title: str = Field(
        default="",
        max_length=120,
        description="Leave empty for conversational chat answers.",
    )
    answer: str = Field(
        min_length=1,
        max_length=6_000,
        description=(
            "A natural Markdown answer grounded only in the supplied backend evidence."
        ),
    )
    sections: list[AssistantAnswerSection] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Optional detailed sections for broad or multi-part analysis requests."
        ),
    )

    @field_validator("visuals")
    @classmethod
    def unique_visuals(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class AssistantResearchResponse(BaseModel):
    instrument: dict[str, object] = Field(default_factory=dict)
    news: StockNewsResponse | None = None
    horizon_signals: list[HorizonSignal] = Field(default_factory=list)
    interpretation: StockPromptInterpretation
    stock: StockSearchResultResponse
    quote: StockQuoteResponse
    history: StockHistoryResponse | None = None
    analysis: StockAnalysisResponse | None = None
    analysis_error: str | None = None
    fundamentals: StockFundamentalsResponse | None = None
    fundamentals_error: str | None = None
    outlook: StockOutlookResponse | None = None
    outlook_error: str | None = None
    explanation: AssistantExplanation | None = None
    explanation_error: str | None = None
