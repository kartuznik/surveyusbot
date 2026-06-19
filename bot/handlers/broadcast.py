from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramForbiddenError

from bot.states import BroadcastStates
from database import get_all_users

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
    await state.clear()
    await state.set_state(BroadcastStates.waiting_content)
    await message.answer(
        "Отправьте текст сообщения для рассылки (поддерживается HTML-форматирование). "
        "Также можно отправить фото/документ с подписью."
    )


@router.message(BroadcastStates.waiting_content)
async def capture_broadcast_content(message: Message, state: FSMContext) -> None:
    if message.text:
        await state.update_data(kind="text", text=message.text)
        await message.answer(
            "Предпросмотр:\n\n" + message.text,
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
    users = await get_all_users()
    total = len(users)
    sent = 0
    failed = 0
    await callback.answer("Запускаю рассылку...")
    if callback.message:
        await callback.message.answer(f"Начинаю рассылку по {total} пользователям...")

    for user_id in users:
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
                continue
            sent += 1
        except TelegramForbiddenError:
            failed += 1
            logger.warning("User %s blocked bot during broadcast", user_id)
        except Exception as error:  # pragma: no cover
            failed += 1
            logger.exception("Broadcast failed for user %s: %s", user_id, error)
        await asyncio.sleep(0.5)

    await state.clear()
    if callback.message:
        await callback.message.answer(
            f"✅ Рассылка завершена. Отправлено: {sent} из {total}, ошибок: {failed}"
        )
