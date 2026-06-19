import asyncio
import contextlib
import logging
import signal
import shutil
import sqlite3
import traceback
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher

from bot.commands import setup_commands, setup_menu_button
from bot.diagnostics.error_tracker import get_error_tracker
from bot.diagnostics.stability import StabilityMonitor, set_stability_monitor
from bot.handlers import (
    admin,
    broadcast,
    demo,
    health as health_handler,
    roles as roles_handler,
    stats,
    user,
)
from bot.health import BotHealthMonitor, set_monitor
from bot.roles import RoleManager, set_role_manager_instance
from config import get_settings
from database import create_demo_surveys, init_db
from middlewares import AdminOrOwnerMiddleware, OwnerOnlyMiddleware

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
    if settings.DEMO_MODE:
        await create_demo_surveys()
    await backup_database(settings.db_path)

    role_manager = RoleManager(settings.db_path)
    await role_manager.init_schema()
    await role_manager.ensure_initial_roles(settings.owner_id, settings.ADMIN_IDS)
    set_role_manager_instance(role_manager)
    roles_handler.set_role_manager(role_manager)
    admin_ids = await role_manager.get_all_admins()
    owner_id = await role_manager.get_owner_id()

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    admin_middleware = AdminOrOwnerMiddleware(role_manager)
    owner_middleware = OwnerOnlyMiddleware(role_manager)
    admin.router.message.middleware(admin_middleware)
    admin.router.callback_query.middleware(admin_middleware)
    health_handler.router.message.middleware(admin_middleware)
    stats.router.message.middleware(admin_middleware)
    stats.router.callback_query.middleware(admin_middleware)
    broadcast.router.message.middleware(admin_middleware)
    broadcast.router.callback_query.middleware(admin_middleware)
    roles_handler.router.message.middleware(owner_middleware)

    dp.include_router(admin.router)
    dp.include_router(health_handler.router)
    dp.include_router(stats.router)
    dp.include_router(broadcast.router)
    dp.include_router(roles_handler.router)
    dp.include_router(demo.router)
    dp.include_router(user.router)

    monitor = BotHealthMonitor(
        bot=bot,
        db_path=settings.db_path,
        data_dir="data",
        admin_ids=admin_ids,
    )
    set_monitor(monitor)
    health_task = asyncio.create_task(monitor.run())
    backup_task = asyncio.create_task(periodic_backup_loop(settings.db_path))
    stability_task: asyncio.Task | None = None
    if settings.ENABLE_STABILITY_MONITORING:
        stability_monitor = StabilityMonitor(
            bot=bot,
            db_path=settings.db_path,
            admin_ids=admin_ids,
            max_errors_before_heal=settings.MAX_ERRORS_BEFORE_HEAL,
            memory_limit_mb=settings.MEMORY_LIMIT_MB,
        )
        set_stability_monitor(stability_monitor)
        stability_task = asyncio.create_task(stability_monitor.run())

    await setup_commands(bot, admin_ids=admin_ids, owner_id=owner_id)
    await setup_menu_button(bot, admin_ids=admin_ids, owner_id=owner_id)
    print("Бот запущен")

    should_stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(Exception):
            loop.add_signal_handler(sig, should_stop.set)

    tracker = get_error_tracker()
    try:
        while not should_stop.is_set():
            try:
                await dp.start_polling(bot)
                break
            except (KeyboardInterrupt, SystemExit):
                should_stop.set()
                break
            except Exception as error:
                tb = traceback.format_exc()
                tracker.add_error(type(error).__name__, str(error), tb)
                logger.exception("Unhandled polling error: %s", error)
                for admin_id in admin_ids:
                    with contextlib.suppress(Exception):
                        await bot.send_message(
                            admin_id,
                            f"⚠️ Произошла ошибка в боте: {type(error).__name__}: {error}",
                        )
                if tracker.count_since_seconds(600) > 5:
                    await monitor.heal("too_many_errors_10m")
                await asyncio.sleep(2)
    finally:
        monitor.stop()
        health_task.cancel()
        backup_task.cancel()
        if stability_task is not None:
            stability_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await health_task
        with contextlib.suppress(asyncio.CancelledError):
            await backup_task
        if stability_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await stability_task


if __name__ == "__main__":
    asyncio.run(main())
