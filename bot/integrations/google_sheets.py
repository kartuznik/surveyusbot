from __future__ import annotations

from datetime import datetime

import gspread
import sqlite3

from config import get_settings


def export_to_google_sheets(survey_id: int) -> str:
    settings = get_settings()
    if not settings.GOOGLE_SHEETS_ENABLED:
        raise RuntimeError("Google Sheets integration is disabled")
    if not settings.GOOGLE_SHEETS_SPREADSHEET_ID:
        raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID is empty")

    gc = gspread.service_account(filename=settings.GOOGLE_SHEETS_CREDENTIALS)
    spreadsheet = gc.open_by_key(settings.GOOGLE_SHEETS_SPREADSHEET_ID)

    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                COALESCE(CAST(u.telegram_id AS TEXT), CAST(r.user_id AS TEXT)) AS user_id,
                COALESCE(u.username, '') AS username,
                q.question_text AS question,
                COALESCE(a.answer_text, '') AS answer,
                COALESCE(r.completed_at, r.started_at) AS timestamp
            FROM responses r
            JOIN answers a ON a.response_id = r.id
            JOIN questions q ON q.id = a.question_id
            LEFT JOIN users u ON u.id = r.user_id
            WHERE r.survey_id = ?
            ORDER BY r.id ASC, q.order_index ASC
            """,
            (survey_id,),
        ).fetchall()
    finally:
        conn.close()

    title = f"Survey_{survey_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    worksheet = spreadsheet.add_worksheet(title=title[:100], rows=max(len(rows) + 10, 100), cols=8)

    values = [["user_id", "username", "question", "answer", "timestamp"]]
    for row in rows:
        values.append(
            [
                row["user_id"],
                row["username"],
                row["question"],
                row["answer"],
                row["timestamp"],
            ]
        )
    worksheet.update("A1:E{}".format(len(values)), values)
    worksheet.format("A1:E1", {"textFormat": {"bold": True}})
    worksheet.columns_auto_resize(0, 5)
    return f"https://docs.google.com/spreadsheets/d/{settings.GOOGLE_SHEETS_SPREADSHEET_ID}/edit#gid={worksheet.id}"
