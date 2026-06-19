from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.roles import RoleManager

router = Router()
_role_manager: RoleManager | None = None


def set_role_manager(role_manager: RoleManager) -> None:
    global _role_manager
    _role_manager = role_manager


def _extract_user_id(message: Message) -> int | None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return None
    if not parts[1].strip().isdigit():
        return None
    return int(parts[1].strip())


@router.message(Command("setadmin"))
async def cmd_setadmin(message: Message) -> None:
    if _role_manager is None:
        await message.answer("RoleManager не инициализирован")
        return
    target_id = _extract_user_id(message)
    if target_id is None:
        await message.answer("Использование: /setadmin <user_id>")
        return

    granted_by = message.from_user.id if message.from_user else None
    await _role_manager.set_role(target_id, "admin", granted_by)
    await message.answer(f"Пользователь {target_id} назначен администратором")


@router.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message) -> None:
    if _role_manager is None:
        await message.answer("RoleManager не инициализирован")
        return
    target_id = _extract_user_id(message)
    if target_id is None:
        await message.answer("Использование: /removeadmin <user_id>")
        return

    owner_id = await _role_manager.get_owner_id()
    if owner_id is not None and target_id == owner_id:
        await message.answer("Нельзя снять роль owner через /removeadmin")
        return

    await _role_manager.remove_role(target_id)
    await message.answer(f"Права администратора у пользователя {target_id} отозваны")


@router.message(Command("admins"))
async def cmd_admins(message: Message) -> None:
    if _role_manager is None:
        await message.answer("RoleManager не инициализирован")
        return

    rows = await _role_manager.get_admin_roles()
    if not rows:
        await message.answer("Администраторы не назначены")
        return

    lines = ["Список ролей:"]
    for user_id, role in rows:
        lines.append(f"- {user_id}: {role}")
    await message.answer("\n".join(lines))


@router.message(Command("transferowner"))
async def cmd_transferowner(message: Message) -> None:
    if _role_manager is None:
        await message.answer("RoleManager не инициализирован")
        return
    target_id = _extract_user_id(message)
    if target_id is None:
        await message.answer("Использование: /transferowner <user_id>")
        return

    current_owner_id = await _role_manager.get_owner_id()
    if current_owner_id is None:
        await message.answer("Текущий owner не найден")
        return

    granted_by = message.from_user.id if message.from_user else None
    await _role_manager.set_role(target_id, "owner", granted_by)
    if target_id != current_owner_id:
        await _role_manager.set_role(current_owner_id, "admin", target_id)

    await message.answer(f"Права owner переданы пользователю {target_id}")
