"""Модуль для работы с SQLite базой данных SurveyBot.

В этом файле собраны:
1) Подключение к БД через aiosqlite (асинхронно для бота).
2) Инициализация схемы таблиц для MVP.
3) Базовые pragma-настройки, чтобы бот и Flask могли безопасно
   работать с одним SQLite-файлом в двух независимых процессах.
"""

from __future__ import annotations

import json
import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any

import aiosqlite

from config import get_settings


def _resolve_db_path() -> Path:
    """Возвращает путь к файлу БД и гарантирует наличие родительской папки."""

    settings = get_settings()
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


async def get_db() -> aiosqlite.Connection:
    """Создает и возвращает асинхронное подключение к SQLite.

    Важно:
    - check_same_thread=False позволяет использовать соединение в разных
      потоках внутри процесса, что полезно для некоторых сценариев.
    - journal_mode=WAL улучшает совместную работу нескольких процессов
      (например, Telegram-бот + Flask-админка).
    """

    db_path = _resolve_db_path()

    connection = await aiosqlite.connect(
        database=str(db_path),
        check_same_thread=False,
    )
    connection.row_factory = aiosqlite.Row

    # Ключевые настройки для более стабильной параллельной работы SQLite.
    await connection.execute("PRAGMA journal_mode=WAL;")
    await connection.execute("PRAGMA foreign_keys=ON;")
    await connection.execute("PRAGMA synchronous=NORMAL;")
    await connection.execute("PRAGMA busy_timeout=5000;")

    return connection


async def _execute_with_retry(
    db: aiosqlite.Connection,
    query: str,
    params: tuple[Any, ...] = (),
    retries: int = 3,
) -> aiosqlite.Cursor:
    for attempt in range(1, retries + 1):
        try:
            return await db.execute(query, params)
        except aiosqlite.OperationalError as error:
            if "database is locked" in str(error).lower() and attempt < retries:
                await asyncio.sleep(0.2 * attempt)
                continue
            raise
    raise RuntimeError("Retry limit exceeded")


async def init_db() -> None:
    """Инициализирует БД и создает таблицы, если они еще не существуют."""

    db = await get_db()
    try:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                role TEXT NOT NULL DEFAULT 'user'
                    CHECK (role IN ('admin', 'user')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
                    CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                question_type TEXT NOT NULL
                    CHECK (question_type IN ('text', 'choice')),
                choices_json TEXT,
                order_index INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'in_progress'
                    CHECK (status IN ('in_progress', 'completed')),
                FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                response_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                answer_text TEXT,
                FOREIGN KEY (response_id) REFERENCES responses(id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS broadcast_audit (
                user_id INTEGER PRIMARY KEY,
                last_status TEXT NOT NULL,
                last_error TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_users_telegram_id
                ON users (telegram_id);
            CREATE INDEX IF NOT EXISTS idx_questions_survey_id_order
                ON questions (survey_id, order_index);
            CREATE INDEX IF NOT EXISTS idx_responses_survey_id
                ON responses (survey_id);
            CREATE INDEX IF NOT EXISTS idx_responses_user_id
                ON responses (user_id);
            CREATE INDEX IF NOT EXISTS idx_answers_response_id
                ON answers (response_id);
            """
        )
        columns = await (await db.execute("PRAGMA table_info(surveys)")).fetchall()
        column_names = {str(column[1]) for column in columns}
        if "is_demo" not in column_names:
            await db.execute("ALTER TABLE surveys ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")
        await db.commit()
    finally:
        await db.close()


async def create_survey(title: str, description: str | None) -> int:
    """Создает анкету и возвращает ее ID."""

    db = await get_db()
    try:
        await _execute_with_retry(
            db,
            """
            INSERT INTO surveys (title, description, is_active)
            VALUES (?, ?, 1)
            """,
            (title, description),
        )
        await db.commit()
        cursor = await db.execute("SELECT last_insert_rowid();")
        row = await cursor.fetchone()
        return int(row[0])
    except Exception as error:
        raise RuntimeError("Не удалось создать анкету в БД") from error
    finally:
        await db.close()


async def add_question(
    survey_id: int,
    text: str,
    q_type: str,
    choices: list[str] | None = None,
) -> None:
    """Добавляет вопрос в анкету."""

    choices_json = json.dumps(choices, ensure_ascii=False) if choices else None

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COALESCE(MAX(order_index), -1) + 1 FROM questions WHERE survey_id = ?",
            (survey_id,),
        )
        row = await cursor.fetchone()
        next_order_index = int(row[0]) if row else 0

        await _execute_with_retry(
            db,
            """
            INSERT INTO questions (
                survey_id,
                question_text,
                question_type,
                choices_json,
                order_index
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (survey_id, text, q_type, choices_json, next_order_index),
        )
        await db.commit()
    except Exception as error:
        raise RuntimeError("Не удалось добавить вопрос в БД") from error
    finally:
        await db.close()


async def get_active_surveys(include_demo: bool = False) -> list[dict[str, Any]]:
    """Возвращает список активных анкет."""

    db = await get_db()
    try:
        if include_demo:
            cursor = await db.execute(
                """
                SELECT id, title, description, is_active, created_at, COALESCE(is_demo, 0) AS is_demo
                FROM surveys
                WHERE is_active = 1
                ORDER BY created_at DESC
                """
            )
        else:
            cursor = await db.execute(
                """
                SELECT id, title, description, is_active, created_at, COALESCE(is_demo, 0) AS is_demo
                FROM surveys
                WHERE is_active = 1 AND COALESCE(is_demo, 0) = 0
                ORDER BY created_at DESC
                """
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as error:
        raise RuntimeError("Не удалось получить список активных анкет") from error
    finally:
        await db.close()


async def get_questions(survey_id: int) -> list[dict[str, Any]]:
    """Возвращает список вопросов анкеты в порядке order_index."""

    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT id, survey_id, question_text, question_type, choices_json, order_index
            FROM questions
            WHERE survey_id = ?
            ORDER BY order_index ASC
            """,
            (survey_id,),
        )
        rows = await cursor.fetchall()
        questions: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if item.get("choices_json"):
                item["choices"] = json.loads(item["choices_json"])
            else:
                item["choices"] = None
            questions.append(item)
        return questions
    except Exception as error:
        raise RuntimeError("Не удалось получить вопросы анкеты") from error
    finally:
        await db.close()


async def _get_or_create_user_by_telegram_id(
    db: aiosqlite.Connection,
    telegram_id: int,
) -> int:
    """Ищет или создает пользователя, затем возвращает внутренний user.id."""

    cursor = await db.execute(
        "SELECT id FROM users WHERE telegram_id = ?",
        (telegram_id,),
    )
    existing = await cursor.fetchone()
    if existing:
        return int(existing[0])

    await db.execute(
        """
        INSERT INTO users (telegram_id, username, role)
        VALUES (?, ?, 'user')
        """,
        (telegram_id, None),
    )
    await db.commit()
    cursor = await db.execute("SELECT last_insert_rowid();")
    row = await cursor.fetchone()
    return int(row[0])


async def create_response(survey_id: int, user_id: int) -> int:
    """Создает запись прохождения анкеты и возвращает response_id.

    Примечание:
    - В аргументе user_id ожидается Telegram ID пользователя.
    - В таблицу responses сохраняется внутренний users.id.
    """

    db = await get_db()
    try:
        internal_user_id = await _get_or_create_user_by_telegram_id(db, user_id)

        await _execute_with_retry(
            db,
            """
            INSERT INTO responses (survey_id, user_id, status)
            VALUES (?, ?, 'in_progress')
            """,
            (survey_id, internal_user_id),
        )
        await db.commit()
        cursor = await db.execute("SELECT last_insert_rowid();")
        row = await cursor.fetchone()
        return int(row[0])
    except Exception as error:
        raise RuntimeError("Не удалось создать запись прохождения анкеты") from error
    finally:
        await db.close()


async def save_answer(response_id: int, question_id: int, answer_text: str) -> None:
    """Сохраняет ответ пользователя на конкретный вопрос."""

    db = await get_db()
    try:
        await _execute_with_retry(
            db,
            """
            INSERT INTO answers (response_id, question_id, answer_text)
            VALUES (?, ?, ?)
            """,
            (response_id, question_id, answer_text),
        )
        await db.commit()
    except Exception as error:
        raise RuntimeError("Не удалось сохранить ответ в БД") from error
    finally:
        await db.close()


async def complete_response(response_id: int) -> None:
    """Отмечает прохождение анкеты как завершенное."""

    db = await get_db()
    try:
        await _execute_with_retry(
            db,
            """
            UPDATE responses
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (response_id,),
        )
        await db.commit()
    except Exception as error:
        raise RuntimeError("Не удалось завершить прохождение анкеты") from error
    finally:
        await db.close()


async def get_demo_surveys() -> list[dict[str, Any]]:
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT id, title, description, is_active, created_at, COALESCE(is_demo, 0) AS is_demo
            FROM surveys
            WHERE is_active = 1 AND COALESCE(is_demo, 0) = 1
            ORDER BY created_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def create_demo_surveys() -> None:
    seeds = [
        (
            "Опрос удовлетворённости клиентов",
            "Демо-анкета для оценки клиентского опыта",
            [
                ("Как вас зовут?", "text", None),
                ("Ваш возраст", "choice", ["18-24", "25-34", "35-44", "45+"]),
                ("Оцените сервис от 1 до 5", "choice", ["1", "2", "3", "4", "5"]),
                ("Комментарий", "text", None),
                ("Порекомендуете нас друзьям?", "choice", ["Да", "Нет"]),
            ],
        ),
        (
            "Оценка качества обслуживания",
            "Демо-анкета по работе менеджеров",
            [
                ("Вежливость сотрудника", "choice", ["Плохо", "Нормально", "Отлично"]),
                ("Скорость решения вопроса", "choice", ["Медленно", "Средне", "Быстро"]),
                ("Комментарий", "text", None),
            ],
        ),
        (
            "Сбор обратной связи",
            "Демо-анкета для продуктовой обратной связи",
            [
                ("Что понравилось больше всего?", "text", None),
                ("Что нужно улучшить?", "text", None),
                ("Насколько удобен интерфейс?", "choice", ["1", "2", "3", "4", "5"]),
                ("Хотите получить ответ от команды?", "choice", ["Да", "Нет"]),
            ],
        ),
    ]

    db = await get_db()
    try:
        for title, description, questions in seeds:
            existing = await (
                await db.execute(
                    "SELECT id FROM surveys WHERE title = ? AND COALESCE(is_demo, 0) = 1 LIMIT 1",
                    (title,),
                )
            ).fetchone()
            if existing:
                continue
            await db.execute(
                """
                INSERT INTO surveys (title, description, is_active, is_demo)
                VALUES (?, ?, 1, 1)
                """,
                (title, description),
            )
            survey_id = int((await (await db.execute("SELECT last_insert_rowid()")).fetchone())[0])
            for idx, (q_text, q_type, choices) in enumerate(questions):
                await db.execute(
                    """
                    INSERT INTO questions (survey_id, question_text, question_type, choices_json, order_index)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        survey_id,
                        q_text,
                        q_type,
                        json.dumps(choices, ensure_ascii=False) if choices else None,
                        idx,
                    ),
                )
        await db.commit()
    finally:
        await db.close()


async def get_all_users() -> list[int]:
    db = await get_db()
    try:
        users_rows = await (await db.execute("SELECT telegram_id FROM users")).fetchall()
        if users_rows:
            return sorted({int(row[0]) for row in users_rows})
    except Exception:
        pass
    finally:
        await db.close()

    db = await get_db()
    try:
        rows = await (
            await db.execute(
                """
                SELECT DISTINCT u.telegram_id
                FROM responses r
                LEFT JOIN users u ON u.id = r.user_id
                WHERE u.telegram_id IS NOT NULL
                """
            )
        ).fetchall()
        return sorted({int(row[0]) for row in rows})
    finally:
        await db.close()


async def get_all_users_with_meta() -> list[dict[str, Any]]:
    db = await get_db()
    try:
        rows = await (
            await db.execute(
                """
                SELECT
                    u.telegram_id AS user_id,
                    u.username AS username,
                    COALESCE(
                        (
                            SELECT MAX(COALESCE(r.completed_at, r.started_at))
                            FROM responses r
                            WHERE r.user_id = u.id
                        ),
                        u.created_at
                    ) AS last_activity,
                    COALESCE(ba.last_status, 'unknown') AS last_broadcast_status
                FROM users u
                LEFT JOIN broadcast_audit ba ON ba.user_id = u.telegram_id
                GROUP BY u.id, u.telegram_id, u.username, u.created_at, ba.last_status
                ORDER BY last_activity DESC
                """
            )
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def set_broadcast_audit(user_id: int, status: str, error: str | None = None) -> None:
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO broadcast_audit (user_id, last_status, last_error, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                last_status=excluded.last_status,
                last_error=excluded.last_error,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, status, error),
        )
        await db.commit()
    finally:
        await db.close()


async def get_users_count(period: str = "all") -> int:
    db = await get_db()
    try:
        if period == "all":
            row = await (await db.execute("SELECT COUNT(DISTINCT telegram_id) FROM users")).fetchone()
            return int(row[0] if row else 0)
        period_map = {"today": "-1 day", "week": "-7 day", "month": "-30 day"}
        delta = period_map.get(period, "-36500 day")
        row = await (
            await db.execute(
                """
                SELECT COUNT(DISTINCT telegram_id)
                FROM users
                WHERE datetime(created_at) >= datetime('now', ?)
                """,
                (delta,),
            )
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        await db.close()


async def get_surveys_count() -> int:
    db = await get_db()
    try:
        row = await (await db.execute("SELECT COUNT(*) FROM surveys WHERE COALESCE(is_demo, 0) = 0")).fetchone()
        return int(row[0] if row else 0)
    finally:
        await db.close()


async def get_responses_count() -> int:
    db = await get_db()
    try:
        row = await (await db.execute("SELECT COUNT(*) FROM responses WHERE status = 'completed'")).fetchone()
        return int(row[0] if row else 0)
    finally:
        await db.close()


async def get_top_surveys(limit: int = 5) -> list[dict[str, Any]]:
    db = await get_db()
    try:
        rows = await (
            await db.execute(
                """
                SELECT s.id, s.title, COUNT(r.id) AS responses_count
                FROM surveys s
                LEFT JOIN responses r ON r.survey_id = s.id AND r.status = 'completed'
                WHERE COALESCE(s.is_demo, 0) = 0
                GROUP BY s.id, s.title
                ORDER BY responses_count DESC, s.id ASC
                LIMIT ?
                """,
                (limit,),
            )
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_daily_activity(days: int = 30) -> list[dict[str, Any]]:
    db = await get_db()
    try:
        user_rows = await (
            await db.execute(
                """
                SELECT date(created_at) AS day, COUNT(DISTINCT telegram_id) AS users_count
                FROM users
                WHERE datetime(created_at) >= datetime('now', ?)
                GROUP BY day
                ORDER BY day ASC
                """,
                (f"-{days} day",),
            )
        ).fetchall()
        response_rows = await (
            await db.execute(
                """
                SELECT date(completed_at) AS day, COUNT(*) AS responses_count
                FROM responses
                WHERE status = 'completed'
                  AND completed_at IS NOT NULL
                  AND datetime(completed_at) >= datetime('now', ?)
                GROUP BY day
                ORDER BY day ASC
                """,
                (f"-{days} day",),
            )
        ).fetchall()
        users_map = {row["day"]: int(row["users_count"]) for row in user_rows if row["day"]}
        responses_map = {
            row["day"]: int(row["responses_count"]) for row in response_rows if row["day"]
        }
        all_days = sorted(set(users_map) | set(responses_map))
        return [
            {
                "day": day,
                "new_users": users_map.get(day, 0),
                "responses": responses_map.get(day, 0),
            }
            for day in all_days
        ]
    finally:
        await db.close()


async def get_average_completion_time() -> timedelta:
    db = await get_db()
    try:
        row = await (
            await db.execute(
                """
                SELECT AVG(strftime('%s', completed_at) - strftime('%s', started_at)) AS avg_seconds
                FROM responses
                WHERE status = 'completed'
                  AND completed_at IS NOT NULL
                """
            )
        ).fetchone()
        seconds = float(row[0]) if row and row[0] is not None else 0.0
        return timedelta(seconds=int(seconds))
    finally:
        await db.close()


async def get_survey_title(survey_id: int) -> str:
    db = await get_db()
    try:
        row = await (
            await db.execute("SELECT title FROM surveys WHERE id = ? LIMIT 1", (survey_id,))
        ).fetchone()
        return str(row[0]) if row else f"#{survey_id}"
    finally:
        await db.close()


async def get_response_notification_payload(response_id: int) -> dict[str, Any]:
    db = await get_db()
    try:
        row = await (
            await db.execute(
                """
                SELECT
                    r.survey_id,
                    s.title AS survey_title,
                    u.telegram_id,
                    r.started_at,
                    r.completed_at,
                    (
                        SELECT COUNT(*)
                        FROM answers a
                        WHERE a.response_id = r.id
                    ) AS answers_count,
                    (
                        SELECT COUNT(*)
                        FROM questions q
                        WHERE q.survey_id = r.survey_id
                    ) AS questions_count
                FROM responses r
                LEFT JOIN users u ON u.id = r.user_id
                LEFT JOIN surveys s ON s.id = r.survey_id
                WHERE r.id = ?
                LIMIT 1
                """,
                (response_id,),
            )
        ).fetchone()
        if row is None:
            return {}
        return dict(row)
    finally:
        await db.close()
