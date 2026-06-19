"""Middleware-слой для Telegram-бота SurveyBot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import get_settings


class AdminMiddleware(BaseMiddleware):
    """Проверяет, что пользователь входит в список администраторов.

    Логика:
    - Если обновление не содержит пользователя, пропускаем обработку.
    - Если пользователь админ, передаем управление дальше.
    - Если пользователь не админ, отправляем уведомление и блокируем хендлер.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        settings = get_settings()
        admin_ids = set(settings.ADMIN_IDS)

        user_id = getattr(getattr(event, "from_user", None), "id", None)

        # Если event без from_user (редкий технический случай), не блокируем.
        if user_id is None:
            return await handler(event, data)

        if user_id in admin_ids:
            return await handler(event, data)

        # Мягко сообщаем о запрете доступа, не вызывая целевой хендлер.
        if isinstance(event, Message):
            await event.answer("У вас нет прав администратора для этой команды.")
        elif isinstance(event, CallbackQuery):
            await event.answer(
                "Недостаточно прав для выполнения действия.",
                show_alert=True,
            )

        return None
