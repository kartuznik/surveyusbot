from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.health import get_monitor
from bot.locales import (
    ACTIVE_USERS,
    BOT_STATUS,
    DB_LAST_CHECK,
    DB_STATUS,
    DISK_FREE,
    HEALTH_TITLE,
    LAST_CRITICAL,
    LAST_HEAL,
    N_A,
    OFFLINE,
    OK,
    ONLINE,
    UPTIME,
)
from config import get_settings

router = Router()


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        settings = get_settings()
        language = settings.LANGUAGE
        return _with_fallback(N_A, language)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_uptime(seconds: int) -> str:
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"


def _with_fallback(mapping: dict[str, str], language: str) -> str:
    primary = mapping.get(language, mapping["ru"])
    fallback_lang = "en" if language == "ru" else "ru"
    fallback = mapping.get(fallback_lang, primary)
    return f"{primary} ({fallback})"


@router.message(Command("health"))
async def cmd_health(message: Message) -> None:
    monitor = get_monitor()
    if monitor is None:
        await message.answer("Health monitor не инициализирован")
        return

    state = monitor.get_status()
    text = render_health_text(state, get_settings().LANGUAGE)
    await message.answer(text)


def render_health_text(state: dict, language: str) -> str:
    status = _with_fallback(ONLINE if state["bot_online"] else OFFLINE, language)
    db_status = (
        _with_fallback(OK, language)
        if state["last_db_ok"]
        else f"error: {state['last_db_error'] or 'unknown'}"
    )
    free_mb = state["free_disk_bytes"] // (1024 * 1024)
    last_critical = state["last_critical_error"] or _with_fallback(
        {"ru": "нет", "en": "none"},
        language,
    )

    return (
        f"{_with_fallback(HEALTH_TITLE, language)}\n\n"
        f"• {_with_fallback(BOT_STATUS, language)}: {status}\n"
        f"• {_with_fallback(DB_LAST_CHECK, language)}: {_fmt_dt(state['last_db_check'])}\n"
        f"• {_with_fallback(DB_STATUS, language)}: {db_status}\n"
        f"• {_with_fallback(DISK_FREE, language)}: {free_mb} MB\n"
        f"• {_with_fallback(ACTIVE_USERS, language)}: {state['active_users']}\n"
        f"• {_with_fallback(UPTIME, language)}: {_fmt_uptime(state['uptime_seconds'])}\n"
        f"• {_with_fallback(LAST_HEAL, language)}: {_fmt_dt(state['last_heal_at'])}\n"
        f"• {_with_fallback(LAST_CRITICAL, language)}: {last_critical}"
    )
