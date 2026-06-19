import asyncio
import contextlib
import logging
import shutil
import sqlite3
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher

from bot.commands import setup_commands, setup_menu_button
from bot.handlers import admin, health as health_handler, user
from bot.health import BotHealthMonitor, set_monitor
from config import get_settings
from database import init_db
from middlewares import AdminMiddleware

logger = logging.getLogger("surveybot.startup")


def _check_integrity_sync(db_path: str) -> str:
    connection = sqlite3.connect(db_path, timeout=5)
    try:
        row = connection.execute("PRAGMA integrity_check;").fetchone()
        return row[0] if row else "unknown"
    finally:
        connection.close()


async def backup_database(db_path: str) -> None:
    backup_path = f"{db_path}.backup"
    db = await aiosqlite.connect(db_path)
    try:
        await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        await db.commit()
    finally:
        await db.close()

    await asyncio.to_thread(shutil.copy2, db_path, backup_path)
    logger.info("SQLite backup updated: %s", backup_path)


async def _restore_database_from_backup(db_path: str, backup_path: str) -> None:
    await asyncio.to_thread(shutil.copy2, backup_path, db_path)
    for sidecar in (f"{db_path}-wal", f"{db_path}-shm"):
        sidecar_path = Path(sidecar)
        if sidecar_path.exists():
            sidecar_path.unlink()


async def ensure_database_integrity_or_restore(db_path: str) -> None:
    db_file = Path(db_path)
    backup_path = f"{db_path}.backup"

    if not db_file.exists():
        return

    integrity = await asyncio.to_thread(_check_integrity_sync, db_path)
    if integrity == "ok":
        return

    logger.error("Обнаружено повреждение БД: %s", integrity)
    if not Path(backup_path).exists():
        raise RuntimeError("БД повреждена, но backup не найден")

    logger.warning("Восстанавливаю БД из backup: %s", backup_path)
    await _restore_database_from_backup(db_path, backup_path)
    restored_integrity = await asyncio.to_thread(_check_integrity_sync, db_path)
    if restored_integrity != "ok":
        raise RuntimeError(f"Восстановленная БД все еще повреждена: {restored_integrity}")


async def periodic_backup_loop(db_path: str) -> None:
    while True:
        await asyncio.sleep(300)
        try:
            await backup_database(db_path)
        except Exception as error:
            logger.exception("Ошибка периодического backup БД: %s", error)


async def main():
    settings = get_settings()
    await ensure_database_integrity_or_restore(settings.db_path)
    await init_db()
    await backup_database(settings.db_path)

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    admin_middleware = AdminMiddleware()
    admin.router.message.middleware(admin_middleware)
    admin.router.callback_query.middleware(admin_middleware)
    health_handler.router.message.middleware(admin_middleware)

    dp.include_router(admin.router)
    dp.include_router(health_handler.router)
    dp.include_router(user.router)

    monitor = BotHealthMonitor(
        bot=bot,
        db_path=settings.db_path,
        data_dir="data",
        admin_ids=settings.ADMIN_IDS,
    )
    set_monitor(monitor)
    health_task = asyncio.create_task(monitor.run())
    backup_task = asyncio.create_task(periodic_backup_loop(settings.db_path))

    await setup_commands(bot)
    await setup_menu_button(bot, settings.ADMIN_IDS)
    print("Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        monitor.stop()
        health_task.cancel()
        backup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await health_task
        with contextlib.suppress(asyncio.CancelledError):
            await backup_task


if __name__ == "__main__":
    asyncio.run(main())
