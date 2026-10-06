"""Local UI smoke-test server: real app routes/persistence, synthetic data, no paid APIs.

Run from backend: PYTHONPATH=.:tests .venv/bin/python tests/report_ui_server.py
"""

from datetime import UTC, datetime, timedelta
from threading import Lock
from unittest.mock import patch

import uvicorn
from sqlalchemy import DefaultClause, MetaData, create_engine, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_assistant import make_interpretation, make_quote, make_stock
from test_financial_quality import annual_rows
from test_stock_direction import make_history, make_news
from test_stock_fundamentals import make_balance_sheet, make_cash_flow, make_overview
from test_stock_analysis import make_history as make_pattern_history

from app.api.routes import market as market_routes
from app.api.routes import stocks as stock_routes
from app.api.services.pattern_backtest_services import build_daily_pattern_backtest
from app.api.schema.assistant import AssistantExplanation
from app.api.schema.research_report import (
    DeepDiveExplanation,
    ReportNarrative,
    ResearchChatGeneration,
)
from app.core.report_policy import REPORT_SECTIONS
from app.api.schema.stock_direction import StockOutlookResponse
from app.api.services import assistant_services as assistant
from app.api.services import research_report_services as reports
from app.core.config import settings
from app.api.services.financial_quality_services import build_financial_quality
from app.api.services.stock_direction_services import build_direction_model
from app.api.services.stock_fundamentals_services import build_stock_fundamentals
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app


@compiles(JSONB, "sqlite")
def jsonb_as_json(type_, compiler, **kwargs):
    return "JSON"


engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


@event.listens_for(engine, "connect")
def foreign_keys(connection, record):
    connection.execute("PRAGMA foreign_keys=ON")


metadata = MetaData()
for table in Base.metadata.sorted_tables:
    table.to_metadata(metadata)
metadata.tables["chat_messages"].c.message_metadata.server_default = DefaultClause(
    text("'{}'")
)
metadata.create_all(engine)
fixture_db_lock = Lock()


def db_session():
    # StaticPool shares one SQLite connection; concurrent HTTP requests must not
    # roll back each other's fixture transactions. Real concurrency is tested on PG.
    with fixture_db_lock, Session(engine) as db:
        yield db


def pattern_study(symbol, limit=250):
    history = make_pattern_history(
        symbol, [100] * 22 + [105, 106, 107, 100, 99, 98, 99, 100, 110, 111, 114]
    )
    cutoff = datetime.fromisoformat(history.bars[-1].timestamp).replace(
        tzinfo=UTC
    ) + timedelta(days=1, hours=12)
    return build_daily_pattern_backtest(history, as_of=cutoff)


def fundamentals(symbol):
    result = build_stock_fundamentals(
        make_overview(), make_balance_sheet(), make_cash_flow(), datetime.now(UTC)
    )
    result.symbol = symbol
    result.annual_financials = annual_rows()
    result.financial_quality = build_financial_quality(
        result.annual_financials, "Technology"
    )
    return result


def outlook(**kwargs):
    symbol = kwargs["symbol"]
    news = make_news()
    return StockOutlookResponse(
        symbol=symbol,
        benchmark_symbol="SPY",
        news=news,
        direction=build_direction_model(
            make_history(symbol), make_history("SPY", True), news
        ),
        additional_horizons=[
            build_direction_model(
                make_history(symbol),
                make_history("SPY", True),
                news,
                horizon_sessions=n,
            )
            for n in (3, 5)
        ],
    )


class DemoGemini:
    def interpret_stock_prompt(self, message, conversation_context=None):
        comparison = "compare" in message.lower()
        symbol = "AMD" if "amd" in message.lower() else "NVDA"
        symbols = (
            ["NVDA", "AMD", "INTC"]
            if comparison and "intc" in message.lower()
            else ["NVDA", "AMD"]
        )
        return make_interpretation(
            ["quote", "historical_analysis", "fundamentals"], stock_query=symbol
        ).model_copy(
            update={
                "intent": "stock_comparison" if comparison else "stock_research",
                "stock_queries": symbols if comparison else [symbol],
                "report_queries": symbols
                if comparison and "separate reports" in message.lower()
                else [],
                "ranking_preset": "growth"
                if "growth" in message.lower()
                else "quality",
            }
        )

    def generate_chat_response(
        self, message, interpretation, evidence, report_symbols, context
    ):
        narrative = DeepDiveExplanation(
            title="Research snapshot",
            answer="This synthetic test company has positive cash generation, with technical and valuation evidence kept separate.",
            sections=[
                {
                    "label": label,
                    "content": "This is deterministic test content. The saved report retains its original data and timestamps. "
                    * 8,
                }
                for label in REPORT_SECTIONS
            ],
        )
        return ResearchChatGeneration(
            answer=AssistantExplanation(
                title="This title must not be displayed in chat",
                answer="The technical entry zone is a price reference, not intrinsic value. See the saved market analysis for the full evidence.",
                visuals=["price"] if "chart" in message.lower() else [],
            ),
            reports=[
                ReportNarrative(symbol=symbol, explanation=narrative)
                for symbol in report_symbols
            ],
        )


settings.backend_cors_origins = (
    "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5174"
)
app = create_app()
app.dependency_overrides[get_db_session] = db_session
settings.auth_session_secret = (
    "synthetic-ui-only-session-secret-never-use-in-production"
)
settings.auth_cookie_secure = False
settings.google_client_id = None

if __name__ == "__main__":
    with (
        patch.object(reports, "GeminiClient", DemoGemini),
        patch.object(
            reports,
            "_resolve_stock",
            lambda query: make_stock().model_copy(
                update={
                    "symbol": query,
                    "name": {
                        "NVDA": "NVIDIA Corporation",
                        "AMD": "Advanced Micro Devices",
                        "INTC": "Intel Corporation",
                    }[query],
                }
            ),
        ),
        patch.object(
            assistant,
            "get_stock_quote",
            lambda symbol: make_quote().model_copy(update={"symbol": symbol}),
        ),
        patch.object(
            assistant,
            "get_stock_history",
            lambda **kwargs: make_history(kwargs["symbol"]),
        ),
        patch.object(assistant, "get_stock_fundamentals", fundamentals),
        patch.object(assistant, "get_stock_outlook", outlook),
        patch.object(market_routes, "get_stock_fundamentals", fundamentals),
        patch.object(stock_routes, "get_daily_pattern_backtest", pattern_study),
    ):
        uvicorn.run(app, host="127.0.0.1", port=8011)
