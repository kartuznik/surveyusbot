from __future__ import annotations

from datetime import UTC, datetime

import pytest

import config
from bot.handlers.health import render_health_text
from bot.handlers.stats import _build_stats_payload
from database import (
    add_question,
    complete_response,
    create_response,
    create_survey,
    get_all_users_with_meta,
    get_questions,
    init_db,
    save_answer,
    set_broadcast_audit,
)
from web.pdf_export import generate_survey_pdf
from web.stats_pdf_export import generate_stats_pdf
import web.app as web_app


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    config.get_settings.cache_clear()
    return db_path


@pytest.mark.asyncio
async def test_create_and_take_survey_flow(isolated_db):
    await init_db()
    survey_id = await create_survey("Survey A", "desc")
    await add_question(survey_id, "Q1", "text")
    questions = await get_questions(survey_id)
    assert len(questions) == 1

    response_id = await create_response(survey_id=survey_id, user_id=123456789)
    await save_answer(response_id=response_id, question_id=int(questions[0]["id"]), answer_text="A1")
    await complete_response(response_id)


@pytest.mark.asyncio
async def test_broadcast_dry_data_available(isolated_db):
    await init_db()
    survey_id = await create_survey("Survey B", "desc")
    await add_question(survey_id, "Q1", "text")
    q = await get_questions(survey_id)
    response_id = await create_response(survey_id=survey_id, user_id=111)
    await save_answer(response_id=response_id, question_id=int(q[0]["id"]), answer_text="x")
    await complete_response(response_id)
    await set_broadcast_audit(111, "forbidden", "blocked")
    users = await get_all_users_with_meta()
    assert users
    assert int(users[0]["user_id"]) == 111


def test_health_render_output_contains_sections():
    state = {
        "bot_online": True,
        "last_db_ok": True,
        "last_db_error": None,
        "free_disk_bytes": 5 * 1024 * 1024 * 1024,
        "active_users": 2,
        "uptime_seconds": 150,
        "last_heal_at": None,
        "last_critical_error": None,
        "last_critical_at": None,
        "last_db_check": datetime.now(tz=UTC),
    }
    text = render_health_text(state, "ru")
    assert "Состояние системы" in text
    assert "Статус бота" in text


@pytest.mark.asyncio
async def test_pdf_exports_create_binary(isolated_db):
    await init_db()
    survey_id = await create_survey("Survey PDF", "desc")
    await add_question(survey_id, "Q1", "text")
    q = await get_questions(survey_id)
    response_id = await create_response(survey_id=survey_id, user_id=22)
    await save_answer(response_id=response_id, question_id=int(q[0]["id"]), answer_text="ok")
    await complete_response(response_id)

    pdf = generate_survey_pdf(survey_id=survey_id, db_path=str(isolated_db))
    stats_pdf = generate_stats_pdf(db_path=str(isolated_db))
    assert len(pdf) > 100
    assert len(stats_pdf) > 100


@pytest.mark.asyncio
async def test_stats_payload_builds(isolated_db):
    await init_db()
    text, _top, _daily = await _build_stats_payload()
    assert "Статистика" in text


@pytest.mark.asyncio
async def test_csv_export_route(isolated_db):
    await init_db()
    survey_id = await create_survey("Survey CSV", "desc")
    await add_question(survey_id, "Q1", "text")
    q = await get_questions(survey_id)
    response_id = await create_response(survey_id=survey_id, user_id=999)
    await save_answer(response_id=response_id, question_id=int(q[0]["id"]), answer_text="csv")
    await complete_response(response_id)

    web_app.DB_PATH = str(isolated_db)
    client = web_app.app.test_client()
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    resp = client.get(f"/export/{survey_id}")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
