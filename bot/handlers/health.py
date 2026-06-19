from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.diagnostics.error_tracker import get_error_tracker
from bot.diagnostics.stability import get_stability_monitor
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


def _status_icon(level: str) -> str:
    if level == "critical":
        return "❌"
    if level == "warning":
        return "⚠️"
    return "✅"


def _recently(value: datetime | None, seconds: int) -> bool:
    if value is None:
        return False
    return (datetime.now(tz=UTC) - value).total_seconds() <= seconds


@router.message(Command("health"))
async def cmd_health(message: Message) -> None:
    monitor = get_monitor()
    if monitor is None:
        await message.answer("Health monitor не инициализирован")
        return

    state = monitor.get_status()
    text = render_health_text(state, get_settings().LANGUAGE)
    await message.answer(text)


@router.message(Command("diagnostics"))
async def cmd_diagnostics(message: Message) -> None:
    monitor = get_monitor()
    if monitor is None:
        await message.answer("Health monitor не инициализирован")
        return
    state = monitor.get_status()
    tracker = get_error_tracker()
    stability = get_stability_monitor()
    snapshot = stability.get_snapshot() if stability else None
    memory_mb = state.get("memory_mb", 0.0)
    db_ms = snapshot.db_response_ms if snapshot else 0.0
    active_connections = stability.active_connections if stability else 0
    errors_hour = tracker.get_errors_count("hour")
    errors_day = tracker.get_errors_count("day")
    last_error = tracker.last_error()
    last_error_line = (
        f"{last_error.get('error_type')}: {last_error.get('message')}\n{last_error.get('timestamp')}"
        if last_error
        else "нет"
    )
    text = (
        "🩺 Диагностика стабильности\n\n"
        f"• Статус бота: {'онлайн' if state['bot_online'] else 'офлайн'}\n"
        f"• Ошибок за час/день: {errors_hour}/{errors_day}\n"
        f"• Память: {memory_mb:.1f} MB\n"
        f"• Средний ответ БД: {db_ms:.2f} ms\n"
        f"• Активные соединения: {active_connections}\n"
        f"• Uptime: {_fmt_uptime(state['uptime_seconds'])}\n"
        f"• Последняя ошибка:\n{last_error_line}"
    )
    await message.answer(text)


def render_health_text(state: dict, language: str) -> str:
    status = _with_fallback(ONLINE if state["bot_online"] else OFFLINE, language)
    db_error = state["last_db_error"] or state["last_critical_error"] or "unknown"
    is_corrupted = "integrity" in str(db_error).lower() or "corrupt" in str(db_error).lower()
    db_status = _with_fallback(OK, language) if state["last_db_ok"] else (
        _with_fallback({"ru": "повреждена", "en": "corrupted"}, language)
        if is_corrupted
        else f"error: {db_error}"
    )
    free_mb = state["free_disk_bytes"] // (1024 * 1024)
    if not state["bot_online"]:
        bot_level = "critical"
    elif _recently(state.get("last_critical_at"), 900):
        bot_level = "warning"
    else:
        bot_level = "ok"
    db_level = "ok" if state["last_db_ok"] else "critical"
    if free_mb < 100:
        disk_level = "critical"
    elif free_mb < 1024:
        disk_level = "warning"
    else:
        disk_level = "ok"
    last_critical_has_value = bool(state["last_critical_error"])
    last_critical = state["last_critical_error"] or _with_fallback({"ru": "нет", "en": "none"}, language)
    last_critical_level = "warning" if last_critical_has_value and _recently(state.get("last_critical_at"), 3600) else "ok"
    db_check_level = "ok" if state["last_db_check"] is not None else "warning"
    users_level = "ok"
    uptime_level = "ok"
    heal_level = "ok" if state["last_heal_at"] is None else "warning"

    return (
        f"{_with_fallback(HEALTH_TITLE, language)}\n\n"
        f"{_status_icon(bot_level)} {_with_fallback(BOT_STATUS, language)}: {status}\n"
        f"{_status_icon(db_check_level)} {_with_fallback(DB_LAST_CHECK, language)}: {_fmt_dt(state['last_db_check'])}\n"
        f"{_status_icon(db_level)} {_with_fallback(DB_STATUS, language)}: {db_status}\n"
        f"{_status_icon(disk_level)} {_with_fallback(DISK_FREE, language)}: {free_mb} MB\n"
        f"{_status_icon(users_level)} {_with_fallback(ACTIVE_USERS, language)}: {state['active_users']}\n"
        f"{_status_icon(uptime_level)} {_with_fallback(UPTIME, language)}: {_fmt_uptime(state['uptime_seconds'])}\n"
        f"{_status_icon(heal_level)} {_with_fallback(LAST_HEAL, language)}: {_fmt_dt(state['last_heal_at'])}\n"
        f"{_status_icon(last_critical_level)} {_with_fallback(LAST_CRITICAL, language)}: {last_critical}"
    )
