from __future__ import annotations

import config
import pytest

from bot.integrations.google_sheets import export_to_google_sheets
from bot.integrations.webhook import _send
from database import add_question, create_response, create_survey, init_db, save_answer


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    db_path = tmp_path / "integrations.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    config.get_settings.cache_clear()
    return db_path


@pytest.mark.asyncio
async def test_webhook_disabled_no_exception(isolated_env):
    await init_db()
    await _send("new_response", {"a": 1})


@pytest.mark.asyncio
async def test_google_sheets_mock(monkeypatch, isolated_env):
    await init_db()
    survey_id = await create_survey("S", "d")
    await add_question(survey_id, "Q", "text")
    response_id = await create_response(survey_id, 1)
    await save_answer(response_id, 1, "A")

    class FakeWorksheet:
        id = 123

        def update(self, *_args, **_kwargs):
            return None

        def format(self, *_args, **_kwargs):
            return None

        def columns_auto_resize(self, *_args, **_kwargs):
            return None

    class FakeSpreadsheet:
        def add_worksheet(self, **_kwargs):
            return FakeWorksheet()

    class FakeGSpread:
        def open_by_key(self, _key):
            return FakeSpreadsheet()

    monkeypatch.setenv("GOOGLE_SHEETS_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "sheet123")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", "/tmp/fake.json")
    config.get_settings.cache_clear()

    import bot.integrations.google_sheets as gs

    monkeypatch.setattr(gs.gspread, "service_account", lambda filename: FakeGSpread())
    url = export_to_google_sheets(survey_id)
    assert "sheet123" in url
