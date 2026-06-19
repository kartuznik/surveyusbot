"""Модуль для работы с SQLite базой данных SurveyBot.

В этом файле собраны:
1) Подключение к БД через aiosqlite (асинхронно для бота).
2) Инициализация схемы таблиц для MVP.
3) Базовые pragma-настройки, чтобы бот и Flask могли безопасно
   работать с одним SQLite-файлом в двух независимых процессах.
"""

from __future__ import annotations

import json
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

    return connection


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
        await db.commit()
    finally:
        await db.close()


async def create_survey(title: str, description: str | None) -> int:
    """Создает анкету и возвращает ее ID."""

    db = await get_db()
    try:
        await db.execute(
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

        await db.execute(
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


async def get_active_surveys() -> list[dict[str, Any]]:
    """Возвращает список активных анкет."""

    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT id, title, description, is_active, created_at
            FROM surveys
            WHERE is_active = 1
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

        await db.execute(
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
        await db.execute(
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
        await db.execute(
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
