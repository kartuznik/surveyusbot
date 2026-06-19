from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from matplotlib import font_manager


def generate_stats_pdf(db_path: str) -> bytes:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        total_users = int(
            (conn.execute("SELECT COUNT(DISTINCT telegram_id) FROM users").fetchone() or [0])[0]
        )
        surveys_count = int(
            (conn.execute("SELECT COUNT(*) FROM surveys WHERE COALESCE(is_demo,0)=0").fetchone() or [0])[
                0
            ]
        )
        responses_count = int(
            (conn.execute("SELECT COUNT(*) FROM responses WHERE status='completed'").fetchone() or [0])[0]
        )
        daily_rows = conn.execute(
            """
            SELECT date(completed_at) AS day, COUNT(*) AS responses
            FROM responses
            WHERE status='completed'
              AND completed_at IS NOT NULL
              AND datetime(completed_at) >= datetime('now', '-30 day')
            GROUP BY day
            ORDER BY day ASC
            """
        ).fetchall()
        top_surveys = conn.execute(
            """
            SELECT s.title, COUNT(r.id) AS responses_count
            FROM surveys s
            LEFT JOIN responses r ON r.survey_id = s.id AND r.status='completed'
            GROUP BY s.id, s.title
            ORDER BY responses_count DESC
            LIMIT 10
            """
        ).fetchall()
        top_users = conn.execute(
            """
            SELECT COALESCE(CAST(u.telegram_id AS TEXT), CAST(r.user_id AS TEXT)) AS user_id,
                   COUNT(a.id) AS answers_count
            FROM responses r
            LEFT JOIN users u ON u.id = r.user_id
            LEFT JOIN answers a ON a.response_id = r.id
            GROUP BY user_id
            ORDER BY answers_count DESC
            LIMIT 10
            """
        ).fetchall()
    finally:
        conn.close()

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()

    font_path = Path(font_manager.findfont("DejaVu Sans"))
    if font_path.exists():
        pdf.add_font("DejaVu", "", str(font_path), uni=True)
        font = "DejaVu"
    else:
        font = "Helvetica"
    pdf.set_font(font, size=16)
    pdf.cell(0, 10, "SurveyBot Statistics Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font, size=10)
    pdf.cell(
        0,
        8,
        f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)

    pdf.set_font(font, size=12)
    pdf.cell(0, 8, "Общая статистика", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font, size=10)
    pdf.multi_cell(
        0,
        7,
        f"Пользователи: {total_users}\n"
        f"Анкеты: {surveys_count}\n"
        f"Ответы: {responses_count}",
    )
    pdf.ln(1)

    pdf.set_font(font, size=12)
    pdf.cell(0, 8, "Активность по дням (30 дней)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font, size=9)
    for row in daily_rows:
        pdf.cell(0, 6, f"{row['day']}: {row['responses']}", new_x="LMARGIN", new_y="NEXT")
    if not daily_rows:
        pdf.cell(0, 6, "Нет данных", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    pdf.set_font(font, size=12)
    pdf.cell(0, 8, "Топ-10 анкет", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font, size=9)
    for row in top_surveys:
        pdf.cell(
            0,
            6,
            f"{row['title']}: {row['responses_count']}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
    if not top_surveys:
        pdf.cell(0, 6, "Нет данных", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    pdf.set_font(font, size=12)
    pdf.cell(0, 8, "Топ-10 пользователей", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font, size=9)
    for row in top_users:
        pdf.cell(
            0,
            6,
            f"{row['user_id']}: {row['answers_count']}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
    if not top_users:
        pdf.cell(0, 6, "Нет данных", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
