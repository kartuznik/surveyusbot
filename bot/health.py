from __future__ import annotations

import asyncio
import logging
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
import psutil
from aiogram import Bot


class BotHealthMonitor:
    def __init__(
        self,
        bot: Bot,
        db_path: str,
        data_dir: str,
        admin_ids: list[int],
        log_path: str = "bot_health.log",
    ) -> None:
        self.bot = bot
        self.db_path = db_path
        self.data_dir = data_dir
        self.admin_ids = admin_ids
        self.started_at = datetime.now(tz=UTC)

        self.bot_online = False
        self.last_bot_check: datetime | None = None
        self.last_db_check: datetime | None = None
        self.last_resources_check: datetime | None = None
        self.last_db_ok = False
        self.last_db_error: str | None = None
        self.free_disk_bytes = 0
        self.active_users = 0
        self.last_critical_error: str | None = None
        self.last_critical_at: datetime | None = None
        self.last_heal_at: datetime | None = None
        self.base_memory_mb = self._memory_mb()
        self.current_memory_mb = self.base_memory_mb
        self.zombie_connections = 0

        self._stop_event = asyncio.Event()
        self._is_healing = False
        self._logger = self._build_logger(log_path)

    def _build_logger(self, log_path: str) -> logging.Logger:
        logger = logging.getLogger("surveybot.health")
        logger.setLevel(logging.INFO)

        absolute_path = Path(log_path)
        if not absolute_path.is_absolute():
            absolute_path = Path(__file__).resolve().parent.parent / log_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        if not logger.handlers:
            file_handler = logging.FileHandler(absolute_path, encoding="utf-8")
            file_handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(file_handler)

        return logger

    def _log(self, level: int, component: str, message: str) -> None:
        self._logger.log(level, f"[{component}] {message}")

    async def notify_admins(self, text: str) -> None:
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(chat_id=admin_id, text=text)
            except Exception as error:  # pragma: no cover
                self._log(
                    logging.ERROR,
                    "NOTIFY",
                    f"Не удалось отправить уведомление админу {admin_id}: {error}",
                )

    async def check_bot_alive(self) -> bool:
        self.last_bot_check = datetime.now(tz=UTC)
        try:
            await self.bot.get_me()
            self.bot_online = True
            self._log(logging.INFO, "BOT", "Проверка get_me успешна")
            return True
        except Exception as error:
            self.bot_online = False
            self._mark_critical(f"bot_unreachable: {error}")
            self._log(logging.ERROR, "BOT", f"Бот не отвечает: {error}")
            return False

    def _check_db_sync(self) -> tuple[bool, str | None, int]:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL;")
            integrity = connection.execute("PRAGMA integrity_check;").fetchone()
            integrity_value = integrity[0] if integrity else "unknown"
            if integrity_value != "ok":
                return False, f"integrity_check={integrity_value}", 0

            active_users_row = connection.execute(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM responses
                WHERE status = 'in_progress'
                """
            ).fetchone()
            active_users = int(active_users_row[0] if active_users_row else 0)
            return True, None, active_users
        finally:
            connection.close()

    async def check_database(self) -> bool:
        self.last_db_check = datetime.now(tz=UTC)
        retries = 3
        for attempt in range(1, retries + 1):
            try:
                ok, error_text, active_users = await asyncio.to_thread(self._check_db_sync)
                self.active_users = active_users
                self.last_db_ok = ok
                self.last_db_error = error_text
                if ok:
                    self._log(logging.INFO, "DB", "SQLite проверка и integrity_check успешны")
                    return True

                self.last_critical_error = f"database_integrity: {error_text}"
                self.last_critical_at = datetime.now(tz=UTC)
                self._log(logging.ERROR, "DB", f"Ошибка целостности БД: {error_text}")
                return False
            except sqlite3.OperationalError as error:
                message = str(error).lower()
                if "database is locked" in message:
                    self._log(
                        logging.WARNING,
                        "DB",
                        f"БД заблокирована (попытка {attempt}/{retries}), жду перед повтором",
                    )
                    if attempt < retries:
                        await asyncio.sleep(2)
                        continue
                self.last_db_ok = False
                self.last_db_error = str(error)
                self._mark_critical(f"database_error: {error}")
                self._log(logging.ERROR, "DB", f"Ошибка подключения к SQLite: {error}")
                return False
            except Exception as error:
                self.last_db_ok = False
                self.last_db_error = str(error)
                self._mark_critical(f"database_error: {error}")
                self._log(logging.ERROR, "DB", f"Неожиданная ошибка проверки БД: {error}")
                return False
        return False

    async def check_resources(self) -> bool:
        self.last_resources_check = datetime.now(tz=UTC)
        usage = shutil.disk_usage(self.data_dir)
        self.free_disk_bytes = usage.free
        self.current_memory_mb = self._memory_mb()
        min_free_bytes = 100 * 1024 * 1024
        if usage.free < min_free_bytes:
            self._mark_critical("low_disk_space")
            self._log(
                logging.WARNING,
                "RESOURCES",
                f"Свободного места меньше 100MB: {usage.free // (1024 * 1024)}MB",
            )
            return False

        if self.current_memory_mb > self.base_memory_mb * 2:
            self._mark_critical("possible_memory_leak")
            self._log(
                logging.WARNING,
                "RESOURCES",
                f"Подозрение на утечку памяти: {self.current_memory_mb:.1f}MB "
                f"(base {self.base_memory_mb:.1f}MB)",
            )

        self.zombie_connections = await self._check_zombie_connections()
        if self.zombie_connections > 0:
            self._log(
                logging.WARNING,
                "DB",
                f"Обнаружены потенциальные zombie connections: {self.zombie_connections}",
            )
            await self._cleanup_old_sessions()

        self._log(
            logging.INFO,
            "RESOURCES",
            f"Ресурсы в норме, свободно {usage.free // (1024 * 1024)}MB",
        )
        return True

    def _memory_mb(self) -> float:
        return float(psutil.Process().memory_info().rss) / (1024 * 1024)

    async def _check_zombie_connections(self) -> int:
        try:
            db = await aiosqlite.connect(self.db_path)
            await db.execute("PRAGMA wal_checkpoint(PASSIVE)")
            await db.close()
            return 0
        except Exception:
            return 1

    async def _cleanup_old_sessions(self) -> None:
        try:
            await self.bot.session.close()
            self._log(logging.INFO, "HEAL", "Выполнена очистка старых сессий")
        except Exception as error:
            self._log(logging.ERROR, "HEAL", f"Не удалось очистить сессии: {error}")

    def _mark_critical(self, reason: str) -> None:
        self.last_critical_error = reason
        self.last_critical_at = datetime.now(tz=UTC)

    async def heal(self, reason: str) -> bool:
        if self._is_healing:
            return False
        self._is_healing = True
        self.last_heal_at = datetime.now(tz=UTC)

        warning = f"WARNING: {reason}"
        self._log(logging.WARNING, "HEAL", f"Запуск авто-лечения, причина: {reason}")
        await self.notify_admins(warning)

        try:
            attempts = 3
            for attempt in range(1, attempts + 1):
                try:
                    await self.bot.session.close()
                    self._log(
                        logging.INFO,
                        "HEAL",
                        f"Сессия бота пересоздана (попытка {attempt}/{attempts})",
                    )
                except Exception as error:
                    self._log(
                        logging.ERROR,
                        "HEAL",
                        f"Ошибка при пересоздании сессии (попытка {attempt}/{attempts}): {error}",
                    )

                await asyncio.sleep(2)
                if await self.check_bot_alive():
                    self._log(logging.INFO, "HEAL", "Бот восстановлен после авто-лечения")
                    await self.notify_admins(
                        "RECOVERED: бот снова отвечает после пересоздания сессии"
                    )
                    return True

            self._log(
                logging.CRITICAL,
                "HEAL",
                "Авто-лечение не помогло, требуется перезапуск через systemd",
            )
            await self._prepare_safe_restart()
            sys.exit(1)
        finally:
            self._is_healing = False

    async def _prepare_safe_restart(self) -> None:
        db: aiosqlite.Connection | None = None
        try:
            db = await aiosqlite.connect(self.db_path)
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            await db.commit()
        except Exception as error:
            self._log(logging.ERROR, "HEAL", f"Ошибка WAL checkpoint перед рестартом: {error}")
        finally:
            if db is not None:
                try:
                    await db.close()
                except Exception as error:
                    self._log(logging.ERROR, "HEAL", f"Ошибка закрытия БД перед рестартом: {error}")

        await asyncio.sleep(2)

        pre_crash_backup = f"{self.db_path}.pre_crash"
        try:
            await asyncio.to_thread(shutil.copy2, self.db_path, pre_crash_backup)
            self._log(logging.WARNING, "HEAL", f"Создан pre-crash backup: {pre_crash_backup}")
        except Exception as error:
            self._log(logging.ERROR, "HEAL", f"Не удалось создать pre-crash backup: {error}")

    async def run(self) -> None:
        self._log(logging.INFO, "MONITOR", "Фоновый health monitor запущен")
        last_bot = 0.0
        last_db = 0.0
        last_resources = 0.0

        while not self._stop_event.is_set():
            now = asyncio.get_running_loop().time()
            critical_reason: str | None = None

            if now - last_bot >= 30:
                last_bot = now
                if not await self.check_bot_alive():
                    critical_reason = self.last_critical_error or "bot_check_failed"

            if now - last_db >= 60:
                last_db = now
                if not await self.check_database():
                    critical_reason = self.last_critical_error or "db_check_failed"

            if now - last_resources >= 300:
                last_resources = now
                if not await self.check_resources():
                    critical_reason = self.last_critical_error or "resource_check_failed"

            if critical_reason:
                healed = await self.heal(critical_reason)
                if not healed:
                    self._log(
                        logging.CRITICAL,
                        "MONITOR",
                        "Критическая проблема осталась, ожидается перезапуск systemd",
                    )

            await asyncio.sleep(1)

    def stop(self) -> None:
        self._stop_event.set()

    def get_status(self) -> dict[str, Any]:
        return {
            "bot_online": self.bot_online,
            "last_bot_check": self.last_bot_check,
            "last_db_check": self.last_db_check,
            "last_resources_check": self.last_resources_check,
            "last_db_ok": self.last_db_ok,
            "last_db_error": self.last_db_error,
            "free_disk_bytes": self.free_disk_bytes,
            "active_users": self.active_users,
            "uptime_seconds": int((datetime.now(tz=UTC) - self.started_at).total_seconds()),
            "last_critical_error": self.last_critical_error,
            "last_critical_at": self.last_critical_at,
            "last_heal_at": self.last_heal_at,
            "memory_mb": self.current_memory_mb,
            "base_memory_mb": self.base_memory_mb,
            "zombie_connections": self.zombie_connections,
        }


_monitor: BotHealthMonitor | None = None


def set_monitor(monitor: BotHealthMonitor) -> None:
    global _monitor
    _monitor = monitor


def get_monitor() -> BotHealthMonitor | None:
    return _monitor
