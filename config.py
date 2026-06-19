"""Конфигурация приложения SurveyBot.

Используем pydantic-settings для загрузки переменных окружения из .env
и системного окружения.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Централизованные настройки для бота и веб-части."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str = Field(..., description="Токен Telegram-бота")
    FLASK_SECRET: str = Field(..., description="Секретный ключ Flask сессии")
    ADMIN_IDS: list[int] = Field(
        default_factory=list,
        description="Список Telegram ID администраторов",
    )
    OWNER_ID: int | None = Field(
        default=None,
        description="Telegram ID владельца (если пусто, берется первый из ADMIN_IDS)",
    )
    DB_PATH: str = Field(
        default="data/surveybot.db",
        description="Путь к SQLite-файлу (общий для бота и Flask)",
    )
    ADMIN_WEB_PASSWORD: str = Field(
        default="admin",
        description="Простой пароль для входа в Flask-админку",
    )
    DEMO_MODE: bool = Field(
        default=False,
        description="Включает демо-анкеты для покупателей",
    )
    NOTIFY_ON_RESPONSE: bool = Field(
        default=True,
        description="Отправлять уведомления админам о новых ответах",
    )
    WEB_ADMIN_BASE_URL: str = Field(
        default="http://localhost:5000",
        description="Базовый URL веб-админки для ссылок из Telegram",
    )
    BROADCAST_DELAY: float = Field(
        default=0.5,
        description="Базовая задержка между сообщениями в рассылке",
    )
    GOOGLE_SHEETS_ENABLED: bool = Field(
        default=False,
        description="Включает экспорт в Google Sheets",
    )
    GOOGLE_SHEETS_CREDENTIALS: str = Field(
        default="credentials/google_sheets.json",
        description="Путь к credentials сервисного аккаунта Google",
    )
    GOOGLE_SHEETS_SPREADSHEET_ID: str = Field(
        default="",
        description="ID Google Spreadsheet для экспорта",
    )
    WEBHOOK_ENABLED: bool = Field(
        default=False,
        description="Включает CRM webhook интеграцию",
    )
    WEBHOOK_URL: str = Field(
        default="",
        description="URL для отправки webhook событий",
    )
    WEBHOOK_SECRET: str = Field(
        default="",
        description="Секрет для HMAC подписи webhook",
    )
    LANGUAGE: str = Field(
        default="ru",
        description="Язык интерфейса (ru или en)",
    )

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: Any) -> list[int]:
        """Преобразует ADMIN_IDS из строки/списка в list[int].

        Поддерживаем несколько форматов:
        - "123,456,789"
        - [123, 456]
        - ["123", "456"]
        """

        if value is None or value == "":
            return []

        if isinstance(value, (int, float)):
            value = str(int(value))

        if isinstance(value, list):
            return [int(item) for item in value]

        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            return [int(part) for part in parts]

        raise ValueError("ADMIN_IDS должен быть строкой или списком ID")

    @field_validator("OWNER_ID", mode="before")
    @classmethod
    def parse_owner_id(cls, value: Any) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            return int(value)
        raise ValueError("OWNER_ID должен быть числом или пустым значением")

    @field_validator("LANGUAGE", mode="before")
    @classmethod
    def validate_language(cls, value: Any) -> str:
        if value is None or value == "":
            return "ru"
        language = str(value).strip().lower()
        if language not in {"ru", "en"}:
            raise ValueError("LANGUAGE должен быть ru или en")
        return language

    @property
    def db_path(self) -> str:
        """Удобный алиас в snake_case для Python-кода."""

        return self.DB_PATH

    @property
    def owner_id(self) -> int | None:
        if self.OWNER_ID is not None:
            return self.OWNER_ID
        if self.ADMIN_IDS:
            return self.ADMIN_IDS[0]
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек.

    Это предотвращает повторный парсинг .env на каждом вызове.
    """

    return Settings()
