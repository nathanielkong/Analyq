# ruff: noqa: F811
# Pytest resolves the imported db/scenario fixtures by parameter name.
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_research_reports import ask
from test_research_reports import db as db
from test_research_reports import scenario as scenario

from app.api.schema import research_report as report_schema
from app.api.schema.research_report import DeepDiveExplanation, ResearchChatRequest
from app.api.services import daily_report_cache
from app.api.services import research_report_services as services
from app.core import report_policy
from app.core.config import Settings, settings
from app.models.chat import ChatSession
from app.models.research_report import DailyResearchCache
from app.models.user import User


@pytest.fixture
def clock(monkeypatch):
    instant = [datetime(2026, 9, 24, 3, tzinfo=UTC)]
    monkeypatch.setattr(settings, "report_timezone", "Australia/Melbourne")
    for module in (report_policy, daily_report_cache, services, report_schema):
        monkeypatch.setattr(module, "utc_now", lambda: instant[0])
    return instant


def new_user(db):
    key = uuid4().hex
    user = User(google_subject=key, email=f"{key}@example.test", display_name="Test")
    db.add(user)
    db.commit()
    return user


def new_chat(db, user):
    chat = ChatSession(title="Another research chat", user_id=user.id)
    db.add(chat)
    db.commit()
    return chat


def signed_ask(db, chat, client, user, **kwargs):
    return services.answer_research_chat(
        db,
        ResearchChatRequest(
            session_id=chat.id, request_id=uuid4(), message="Analyze NVIDIA", **kwargs
        ),
        user.id,
        client,
    )


def test_same_account_reuses_report_across_chats_without_renewing_expiry(
    db, scenario, clock
):
    _, client, collections = scenario
    user = new_user(db)
    first_chat = new_chat(db, user)
    first = signed_ask(db, first_chat, client, user).reports[0]
    clock[0] += timedelta(hours=3)
    second_chat = new_chat(db, user)
    second = signed_ask(db, second_chat, client, user).reports[0]
    assert first.id != second.id
    assert first.research == second.research
    assert report_policy.as_utc(first.updated_at) == report_policy.as_utc(
        second.updated_at
    )
    assert report_policy.as_utc(first.expires_at) == report_policy.as_utc(
        second.expires_at
    )
    assert collections == ["NVDA"]
    assert client.calls[-1][1] == []
    assert second.is_current


def test_new_day_regenerates_in_existing_and_then_reuses_in_new_chat(
    db, scenario, clock
):
    _, client, collections = scenario
    user = new_user(db)
    chat = new_chat(db, user)
    first = signed_ask(db, chat, client, user).reports[0]
    clock[0] = report_policy.as_utc(first.expires_at)
    assert not first.is_current
    second = signed_ask(db, chat, client, user).reports[0]
    assert second.id == first.id
    assert collections == ["NVDA", "NVDA"]
    assert client.calls[-1][1] == ["NVDA"]
    assert second.is_current
    signed_ask(db, new_chat(db, user), client, user)
    assert collections == ["NVDA", "NVDA"]
    assert client.calls[-1][1] == []
    assert len(list(db.scalars(select(DailyResearchCache)))) == 1


def test_midnight_is_calendar_boundary_not_rolling_24_hours(clock):
    late = datetime(2026, 9, 24, 13, 59, tzinfo=UTC)  # 23:59 Melbourne
    assert report_policy.report_expiry(late) - late == timedelta(minutes=1)
    # Melbourne's DST transition day has 23 hours, not a fixed 24-hour TTL.
    dst_start = datetime(2026, 10, 3, 14, tzinfo=UTC)
    assert report_policy.report_expiry(dst_start) - dst_start == timedelta(hours=23)
    with pytest.raises(ValueError):
        Settings(report_timezone="invalid/timezone")


def test_accounts_and_guest_chats_do_not_share_private_reports(db, scenario, clock):
    guest_chat, client, collections = scenario
    for _ in range(2):
        user = new_user(db)
        signed_ask(db, new_chat(db, user), client, user)
    ask(db, guest_chat, client)
    other_guest = ChatSession(title="Other guest")
    db.add(other_guest)
    db.commit()
    ask(db, other_guest, client)
    assert collections == ["NVDA"] * 4


def test_refresh_replaces_daily_cache_for_other_chats(db, scenario, clock):
    _, client, collections = scenario
    user = new_user(db)
    chat = new_chat(db, user)
    first = signed_ask(db, chat, client, user).reports[0]
    other = new_chat(db, user)
    signed_ask(db, other, client, user)
    clock[0] += timedelta(hours=1)
    refreshed = signed_ask(db, chat, client, user, refresh_report_id=first.id).reports[
        0
    ]
    reused = signed_ask(db, other, client, user).reports[0]
    assert report_policy.as_utc(reused.updated_at) == report_policy.as_utc(
        refreshed.updated_at
    )
    assert collections == ["NVDA", "NVDA"]


def test_cached_collection_survives_narrative_failure_and_chat_deletion(
    db, scenario, clock
):
    _, client, collections = scenario
    user = new_user(db)
    chat = new_chat(db, user)
    client.fail = True
    signed_ask(db, chat, client, user)
    db.delete(chat)
    db.commit()
    client.fail = False
    report = signed_ask(db, new_chat(db, user), client, user).reports[0]
    assert report.research.explanation
    assert collections == ["NVDA"]


def test_comparison_uses_daily_cache_without_adding_tabs(db, scenario, clock):
    _, client, collections = scenario
    user = new_user(db)
    signed_ask(db, new_chat(db, user), client, user)
    client.interpretation = client.interpretation.model_copy(
        update={"intent": "stock_comparison", "stock_queries": ["NVDA", "AMD"]}
    )
    response = signed_ask(db, new_chat(db, user), client, user)
    assert response.reports == []
    assert collections == ["NVDA", "AMD"]
    assert client.calls[-1][1] == []


def test_report_requires_all_named_sections():
    with pytest.raises(ValueError):
        DeepDiveExplanation(
            answer="Example",
            sections=[{"label": "Market report", "content": "Incomplete"}],
        )


def test_format_version_change_forces_new_report(db, scenario, clock):
    session, client, collections = scenario
    first = ask(db, session, client)
    report = services.list_research_reports(db, session.id, None)[0]
    cache = db.scalar(select(DailyResearchCache))
    report.format_version = 0
    cache.format_version = 0
    db.commit()
    second = ask(db, session, client)
    assert collections == ["NVDA", "NVDA"]
    assert second.reports[0].id == first.reports[0].id
    assert second.reports[0].updated_at.tzinfo is not None


def test_narration_crossing_midnight_keeps_original_snapshot_date(
    db, scenario, clock, monkeypatch
):
    session, client, collections = scenario
    clock[0] = datetime(2026, 9, 24, 13, 59, tzinfo=UTC)
    generate = client.generate_chat_response

    def crossing_midnight(*args):
        clock[0] += timedelta(minutes=2)
        return generate(*args)

    monkeypatch.setattr(client, "generate_chat_response", crossing_midnight)
    first = ask(db, session, client).reports[0]
    assert not first.is_current
    second = ask(db, session, client).reports[0]
    assert second.is_current
    assert collections == ["NVDA", "NVDA"]
