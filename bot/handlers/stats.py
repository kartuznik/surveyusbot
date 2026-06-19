from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.stats_charts import generate_stats_charts
from database import (
    get_average_completion_time,
    get_daily_activity,
    get_responses_count,
    get_surveys_count,
    get_top_surveys,
    get_users_count,
)

router = Router()

_cache: dict[str, tuple[datetime, str, list[dict], list[dict]]] = {}
_CACHE_KEY = "stats_text_v1"
_CACHE_SECONDS = 300
_SHOW_CHARTS_CALLBACK = "stats_show_charts"


def _button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Показать графики", callback_data=_SHOW_CHARTS_CALLBACK)]
        ]
    )


def _format_duration(seconds: int) -> str:
    minutes, secs = divmod(max(seconds, 0), 60)
    return f"{minutes} мин {secs} сек"


async def _build_stats_payload() -> tuple[str, list[dict], list[dict]]:
    now = datetime.now(tz=UTC)
    cached = _cache.get(_CACHE_KEY)
    if cached:
        created_at, text, top_surveys, daily_activity = cached
        if (now - created_at).total_seconds() <= _CACHE_SECONDS:
            return text, top_surveys, daily_activity

    total_users = await get_users_count("all")
    users_today = await get_users_count("today")
    users_week = await get_users_count("week")
    users_month = await get_users_count("month")
    surveys_count = await get_surveys_count()
    responses_count = await get_responses_count()
    average_time = await get_average_completion_time()
    top_surveys = await get_top_surveys(limit=5)
    daily_activity = await get_daily_activity(days=30)

    top_survey_title = "нет данных"
    top_survey_responses = 0
    if top_surveys:
        top_survey_title = str(top_surveys[0]["title"])
        top_survey_responses = int(top_surveys[0]["responses_count"])

    text = (
        "📊 Статистика (Statistics)\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"📈 Новых за сегодня: {users_today} / за неделю: {users_week} / за месяц: {users_month}\n"
        f"📝 Анкет создано: {surveys_count}\n"
        f"✅ Анкет пройдено: {responses_count}\n"
        f"⏱️ Среднее время прохождения: {_format_duration(int(average_time.total_seconds()))}\n"
        f"🏆 Топ анкета: \"{top_survey_title}\" ({top_survey_responses} ответов)"
    )

    _cache[_CACHE_KEY] = (now, text, top_surveys, daily_activity)
    return text, top_surveys, daily_activity


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    text, _, _ = await _build_stats_payload()
    await message.answer(text, reply_markup=_button())


@router.callback_query(F.data == _SHOW_CHARTS_CALLBACK)
async def callback_stats_charts(callback: CallbackQuery) -> None:
    text, top_surveys, daily_activity = await _build_stats_payload()
    await callback.answer("Генерирую графики...")
    chart_paths = generate_stats_charts(daily_activity=daily_activity, top_surveys=top_surveys)

    captions = [
        "Bar chart: Новые пользователи за последние 30 дней",
        "Line chart: Прохождения анкет по дням (30 дней)",
        "Pie chart: Топ-5 анкет по прохождениям",
    ]
    for path, caption in zip(chart_paths, captions, strict=False):
        await callback.bot.send_photo(
            chat_id=callback.from_user.id,
            photo=FSInputFile(str(path)),
            caption=caption,
        )
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass

    if callback.message:
        await callback.message.answer("✅ Графики отправлены.")
