"""Middleware-слой для Telegram-бота SurveyBot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.roles import RoleManager


class OwnerOnlyMiddleware(BaseMiddleware):
    """Разрешает доступ только владельцу."""

    def __init__(self, role_manager: RoleManager) -> None:
        self.role_manager = role_manager

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = getattr(getattr(event, "from_user", None), "id", None)
        if user_id is None:
            return await handler(event, data)

        if await self.role_manager.is_owner(int(user_id)):
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer("Команда доступна только владельцу бота.")
        elif isinstance(event, CallbackQuery):
            await event.answer(
                "Команда доступна только владельцу.",
                show_alert=True,
            )
        return None


class AdminOrOwnerMiddleware(BaseMiddleware):
    """Разрешает доступ владельцу и администраторам."""

    def __init__(self, role_manager: RoleManager) -> None:
        self.role_manager = role_manager

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = getattr(getattr(event, "from_user", None), "id", None)
        if user_id is None:
            return await handler(event, data)

        if await self.role_manager.is_admin(int(user_id)):
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer("У вас нет прав администратора для этой команды.")
        elif isinstance(event, CallbackQuery):
            await event.answer(
                "Недостаточно прав для выполнения действия.",
                show_alert=True,
            )

        return None
