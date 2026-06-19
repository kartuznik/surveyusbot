from __future__ import annotations

from pathlib import Path

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    MenuButtonCommands,
)

USER_COMMANDS: list[tuple[str, str]] = [
    ("start", "Запустить бота"),
    ("help", "Помощь"),
    ("demo", "Демо-анкеты"),
]

ADMIN_COMMANDS: list[tuple[str, str]] = [
    ("start", "Запустить бота"),
    ("help", "Помощь"),
    ("create_survey", "Создать анкету"),
    ("list_surveys", "Мои анкеты"),
    ("health", "Состояние системы (System Health)"),
    ("stats", "Статистика"),
    ("broadcast", "Рассылка"),
]

OWNER_COMMANDS: list[tuple[str, str]] = [
    *ADMIN_COMMANDS,
    ("setadmin", "Назначить админа"),
    ("removeadmin", "Снять права админа"),
    ("admins", "Список админов"),
    ("transferowner", "Передать права владельца"),
]


async def setup_commands(bot: Bot, admin_ids: list[int], owner_id: int | None) -> None:
    commands = [BotCommand(command=cmd, description=desc) for cmd, desc in USER_COMMANDS]
    admin_commands = [BotCommand(command=cmd, description=desc) for cmd, desc in ADMIN_COMMANDS]
    owner_commands = [BotCommand(command=cmd, description=desc) for cmd, desc in OWNER_COMMANDS]
    await bot.set_my_commands(
        commands=commands,
        scope=BotCommandScopeDefault(),
    )
    await bot.set_my_commands(
        commands=admin_commands,
        scope=BotCommandScopeAllChatAdministrators(),
    )
    for admin_id in set(admin_ids):
        await bot.set_my_commands(
            commands=admin_commands,
            scope=BotCommandScopeChat(chat_id=admin_id),
        )
    if owner_id is not None:
        await bot.set_my_commands(
            commands=owner_commands,
            scope=BotCommandScopeChat(chat_id=owner_id),
        )
    print(f"Registered {len(commands)} user commands", flush=True)
    print(f"Registered {len(admin_commands)} admin commands", flush=True)
    print(f"Registered {len(owner_commands)} owner commands", flush=True)


async def setup_menu_button(bot: Bot, admin_ids: list[int], owner_id: int | None) -> None:
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    for admin_id in admin_ids:
        await bot.set_chat_menu_button(
            chat_id=admin_id,
            menu_button=MenuButtonCommands(),
        )
    if owner_id is not None:
        await bot.set_chat_menu_button(
            chat_id=owner_id,
            menu_button=MenuButtonCommands(),
        )
    print(
        f"Registered menu button for {len(set(admin_ids))} admins and owner",
        flush=True,
    )


def build_commands_text() -> str:
    lines: list[str] = ["# Commands for BotFather", ""]
    lines.append("# Users")
    for cmd, desc in USER_COMMANDS:
        lines.append(f"{cmd} - {desc}")
    lines.append("")
    lines.append("# Admins")
    for cmd, desc in ADMIN_COMMANDS:
        lines.append(f"{cmd} - {desc}")
    lines.append("")
    lines.append("# Owner")
    for cmd, desc in OWNER_COMMANDS:
        lines.append(f"{cmd} - {desc}")
    return "\n".join(lines).strip() + "\n"


def export_commands_file(path: str | Path = "commands.txt") -> Path:
    output_path = Path(path)
    output_path.write_text(build_commands_text(), encoding="utf-8")
    return output_path
