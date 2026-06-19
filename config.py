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
    DB_PATH: str = Field(
        default="data/surveybot.db",
        description="Путь к SQLite-файлу (общий для бота и Flask)",
    )
    ADMIN_WEB_PASSWORD: str = Field(
        default="admin",
        description="Простой пароль для входа в Flask-админку",
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек.

    Это предотвращает повторный парсинг .env на каждом вызове.
    """

    return Settings()
