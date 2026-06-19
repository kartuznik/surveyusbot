from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from matplotlib import font_manager


def generate_survey_pdf(survey_id: int, db_path: str) -> bytes:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        survey = connection.execute(
            "SELECT id, title, description, created_at FROM surveys WHERE id = ?",
            (survey_id,),
        ).fetchone()
        if survey is None:
            raise ValueError("Survey not found")

        rows = connection.execute(
            """
            SELECT
                COALESCE(CAST(u.telegram_id AS TEXT), CAST(r.user_id AS TEXT)) AS user_id,
                q.question_text AS question,
                a.answer_text AS answer,
                COALESCE(r.completed_at, r.started_at) AS created_at
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
        connection.close()

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()

    font_path = Path(font_manager.findfont("DejaVu Sans"))
    if font_path.exists():
        pdf.add_font("DejaVu", "", str(font_path), uni=True)
        pdf.set_font("DejaVu", size=16)
        body_font = "DejaVu"
    else:
        pdf.set_font("Helvetica", size=16)
        body_font = "Helvetica"

    pdf.cell(0, 10, f"{survey['title']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(body_font, size=11)
    pdf.multi_cell(
        0,
        7,
        f"Описание: {survey['description'] or '-'}\n"
        f"Дата создания: {survey['created_at']}\n"
        f"Количество строк ответов: {len(rows)}",
    )
    pdf.ln(2)

    headers = ["user_id", "вопрос", "ответ", "дата"]
    col_widths = [35, 95, 130, 35]
    for header, width in zip(headers, col_widths, strict=False):
        pdf.cell(width, 8, header, border=1)
    pdf.ln()

    pdf.set_font(body_font, size=9)
    for row in rows:
        values = [
            str(row["user_id"] or ""),
            str(row["question"] or ""),
            str(row["answer"] or ""),
            str(row["created_at"] or ""),
        ]
        for value, width in zip(values, col_widths, strict=False):
            truncated = value[:120]
            pdf.cell(width, 7, truncated, border=1)
        pdf.ln()

    pdf.ln(3)
    pdf.set_font(body_font, size=8)
    pdf.cell(
        0,
        6,
        f"Сгенерировано SurveyBot {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
    )

    return bytes(pdf.output())
