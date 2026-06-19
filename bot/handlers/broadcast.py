from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from bot.states import BroadcastStates
from config import get_settings
from database import get_all_users, get_all_users_with_meta, set_broadcast_audit

router = Router()
logger = logging.getLogger("surveybot.broadcast")

CONFIRM_CALLBACK = "broadcast_confirm_send"
CANCEL_CALLBACK = "broadcast_confirm_cancel"


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить всем", callback_data=CONFIRM_CALLBACK),
                InlineKeyboardButton(text="❌ Отмена", callback_data=CANCEL_CALLBACK),
            ]
        ]
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    is_dry = "--dry-run" in (message.text or "")
    await state.clear()
    await state.update_data(dry_run=is_dry)
    await state.set_state(BroadcastStates.waiting_content)
    await message.answer(
        "Отправьте текст сообщения для рассылки (поддерживается HTML-форматирование). "
        "Также можно отправить фото/документ с подписью."
    )


@router.message(Command("broadcast_dry"))
async def cmd_broadcast_dry(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(dry_run=True)
    await state.set_state(BroadcastStates.waiting_content)
    await message.answer(
        "🔍 Dry-run режим.\n"
        "Отправьте сообщение для проверки. Реальная отправка выполняться не будет."
    )


@router.message(BroadcastStates.waiting_content)
async def capture_broadcast_content(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    dry_run = bool(data.get("dry_run"))
    if message.text:
        await state.update_data(kind="text", text=message.text)
        await message.answer(
            ("🔍 Dry-run предпросмотр:\n\n" if dry_run else "Предпросмотр:\n\n") + message.text,
            parse_mode="HTML",
            reply_markup=_confirm_keyboard(),
        )
    elif message.photo:
        photo = message.photo[-1]
        caption = message.caption or ""
        await state.update_data(kind="photo", file_id=photo.file_id, caption=caption)
        await message.answer_photo(
            photo=photo.file_id,
            caption=caption or "Предпросмотр фото (без подписи)",
            parse_mode="HTML",
            reply_markup=_confirm_keyboard(),
        )
    elif message.document:
        caption = message.caption or ""
        await state.update_data(
            kind="document",
            file_id=message.document.file_id,
            filename=message.document.file_name or "file",
            caption=caption,
        )
        await message.answer_document(
            document=message.document.file_id,
            caption=caption or "Предпросмотр документа (без подписи)",
            parse_mode="HTML",
            reply_markup=_confirm_keyboard(),
        )
    else:
        await message.answer("Неподдерживаемый формат. Отправьте текст, фото или документ.")
        return
    await state.set_state(BroadcastStates.waiting_confirmation)


@router.callback_query(F.data == CANCEL_CALLBACK, BroadcastStates.waiting_confirmation)
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Рассылка отменена")
    if callback.message:
        await callback.message.answer("❌ Рассылка отменена.")


@router.callback_query(F.data == CONFIRM_CALLBACK, BroadcastStates.waiting_confirmation)
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("dry_run"):
        await _execute_dry_run(callback, state)
        return

    users = await get_all_users()
    total = len(users)
    sent = 0
    failed = 0
    rate_limit_hits = 0
    total_rate_wait = 0.0
    streak_429 = 0
    base_delay = max(float(get_settings().BROADCAST_DELAY), 0.1)
    dynamic_delay = base_delay
    started = time.monotonic()
    await callback.answer("Запускаю рассылку...")
    if callback.message:
        await callback.message.answer(f"Начинаю рассылку по {total} пользователям...")

    for user_id in users:
        while True:
            try:
                kind = data.get("kind")
                if kind == "text":
                    await callback.bot.send_message(
                        chat_id=user_id,
                        text=data.get("text", ""),
                        parse_mode="HTML",
                        disable_web_page_preview=False,
                    )
                elif kind == "photo":
                    await callback.bot.send_photo(
                        chat_id=user_id,
                        photo=data.get("file_id", ""),
                        caption=data.get("caption", None),
                        parse_mode="HTML",
                    )
                elif kind == "document":
                    await callback.bot.send_document(
                        chat_id=user_id,
                        document=data.get("file_id", ""),
                        caption=data.get("caption", None),
                        parse_mode="HTML",
                    )
                else:
                    failed += 1
                    break
                sent += 1
                streak_429 = 0
                await set_broadcast_audit(user_id=int(user_id), status="sent")
                break
            except TelegramRetryAfter as retry_error:
                rate_limit_hits += 1
                streak_429 += 1
                wait_seconds = float(retry_error.retry_after)
                total_rate_wait += wait_seconds
                logger.warning("⚠️ Rate limit exceeded. Waiting %s seconds...", wait_seconds)
                await asyncio.sleep(wait_seconds)
                if streak_429 >= 3:
                    dynamic_delay = min(max(dynamic_delay * 2, 1.0), 2.0)
                continue
            except TelegramForbiddenError:
                failed += 1
                await set_broadcast_audit(
                    user_id=int(user_id),
                    status="forbidden",
                    error="blocked_by_user",
                )
                logger.warning("User %s blocked bot during broadcast", user_id)
                break
            except Exception as error:  # pragma: no cover
                failed += 1
                await set_broadcast_audit(
                    user_id=int(user_id),
                    status="error",
                    error=str(error)[:500],
                )
                logger.exception("Broadcast failed for user %s: %s", user_id, error)
                break
        await asyncio.sleep(dynamic_delay)

    await state.clear()
    elapsed = int(time.monotonic() - started)
    if callback.message:
        await callback.message.answer(
            "✅ Рассылка завершена. "
            f"Отправлено: {sent} из {total}, ошибок: {failed}\n"
            f"Rate-limit сработал: {rate_limit_hits} раз, ожидание: {int(total_rate_wait)} сек.\n"
            f"Общее время: {elapsed} сек."
        )

async def _execute_dry_run(callback: CallbackQuery, state: FSMContext) -> None:
    users = await get_all_users_with_meta()
    total = len(users)
    month_border = datetime.now(tz=UTC).timestamp() - 30 * 24 * 60 * 60
    active_month = 0
    blocked = 0
    lines = ["🔍 Dry-run список получателей:"]
    for item in users:
        user_id = int(item.get("user_id", 0))
        username = item.get("username") or "-"
        last_activity = item.get("last_activity") or "-"
        if item.get("last_broadcast_status") == "forbidden":
            blocked += 1
        if last_activity and last_activity != "-":
            try:
                last_ts = datetime.fromisoformat(str(last_activity).replace("Z", "")).timestamp()
                if last_ts >= month_border:
                    active_month += 1
            except Exception:
                pass
        lines.append(f"- {user_id} | @{username} | last: {last_activity}")

    preview = "\n".join(lines[:120])
    await callback.answer("Dry-run выполнен")
    if callback.message:
        await callback.message.answer(preview)
        await callback.message.answer(
            "🔍 Dry-run завершён. "
            f"Будет отправлено: {total} пользователям. "
            f"Из них: {active_month} активных за последний месяц, {blocked} заблокировали бота"
        )
    await state.clear()
