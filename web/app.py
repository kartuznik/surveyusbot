from __future__ import annotations

import csv
import io
import os
import sqlite3
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from pdf_export import generate_survey_pdf

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

ADMIN_WEB_PASSWORD = os.getenv("ADMIN_WEB_PASSWORD", "admin")
DB_PATH = os.getenv("DB_PATH", "/opt/bots/SurveyBot/data/surveybot.db")
SECRET_KEY = os.getenv("FLASK_SECRET", "surveybot-web-secret")

app = Flask(__name__, template_folder="templates")
app.secret_key = SECRET_KEY


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    return connection


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if ADMIN_WEB_PASSWORD and password == ADMIN_WEB_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("index"))

        flash("Неверный пароль", "danger")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    with get_db_connection() as connection:
        surveys = connection.execute(
            """
            SELECT
                s.id,
                s.title,
                s.created_at,
                COUNT(DISTINCT r.id) AS response_count
            FROM surveys s
            LEFT JOIN responses r ON r.survey_id = s.id
            GROUP BY s.id, s.title, s.created_at
            ORDER BY s.created_at DESC
            """
        ).fetchall()

    return render_template("index.html", surveys=surveys)


def _get_survey_answers(survey_id: int) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    with get_db_connection() as connection:
        survey = connection.execute(
            "SELECT id, title, created_at FROM surveys WHERE id = ?",
            (survey_id,),
        ).fetchone()
        if not survey:
            return None, []

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

    return survey, rows


@app.route("/survey/<int:survey_id>")
@login_required
def survey_detail(survey_id: int):
    survey, rows = _get_survey_answers(survey_id)
    if not survey:
        flash("Анкета не найдена", "warning")
        return redirect(url_for("index"))

    return render_template("survey.html", survey=survey, rows=rows)


@app.route("/export/<int:survey_id>")
@login_required
def export_csv(survey_id: int):
    survey, rows = _get_survey_answers(survey_id)
    if not survey:
        flash("Анкета не найдена", "warning")
        return redirect(url_for("index"))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "question", "answer", "created_at"])
    for row in rows:
        writer.writerow(
            [
                row["user_id"],
                row["question"],
                row["answer"] or "",
                row["created_at"] or "",
            ]
        )

    csv_data = output.getvalue()
    output.close()
    filename = f"survey_{survey_id}_answers.csv"

    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/export_pdf/<int:survey_id>")
@login_required
def export_pdf(survey_id: int):
    try:
        pdf_bytes = generate_survey_pdf(survey_id, DB_PATH)
    except ValueError:
        flash("Анкета не найдена", "warning")
        return redirect(url_for("index"))

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"survey_{survey_id}.pdf",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
