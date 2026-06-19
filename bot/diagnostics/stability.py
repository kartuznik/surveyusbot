from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import psutil
from aiogram import Bot

from bot.diagnostics.error_tracker import get_error_tracker

logger = logging.getLogger("surveybot.stability")


@dataclass
class StabilitySnapshot:
    memory_mb: float
    db_response_ms: float
    errors_hour: int
    errors_day: int
    last_error: dict | None
    updated_at: datetime


class StabilityMonitor:
    def __init__(
        self,
        bot: Bot,
        db_path: str,
        admin_ids: list[int],
        max_errors_before_heal: int = 10,
        memory_limit_mb: int = 500,
    ) -> None:
        self.bot = bot
        self.db_path = db_path
        self.admin_ids = admin_ids
        self.max_errors_before_heal = max_errors_before_heal
        self.memory_limit_mb = memory_limit_mb
        self.process = psutil.Process()
        self.base_memory_mb = self._memory_mb()
        self.avg_db_response_ms = 0.0
        self.active_connections = 0
        self._snapshot = StabilitySnapshot(
            memory_mb=self.base_memory_mb,
            db_response_ms=0.0,
            errors_hour=0,
            errors_day=0,
            last_error=None,
            updated_at=datetime.now(tz=UTC),
        )
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        while not self._stop_event.is_set():
            await self.collect()
            await self._check_thresholds()
            await asyncio.sleep(30)

    def stop(self) -> None:
        self._stop_event.set()

    async def collect(self) -> None:
        tracker = get_error_tracker()
        tracker.clear_old_errors(24)
        errors_hour = tracker.get_errors_count("hour")
        errors_day = tracker.get_errors_count("day")
        memory_mb = self._memory_mb()
        db_ms = await self._probe_db_response_ms()
        if self.avg_db_response_ms == 0:
            self.avg_db_response_ms = db_ms
        else:
            self.avg_db_response_ms = (self.avg_db_response_ms * 0.7) + (db_ms * 0.3)
        self._snapshot = StabilitySnapshot(
            memory_mb=memory_mb,
            db_response_ms=self.avg_db_response_ms,
            errors_hour=errors_hour,
            errors_day=errors_day,
            last_error=tracker.last_error(),
            updated_at=datetime.now(tz=UTC),
        )

    async def _check_thresholds(self) -> None:
        snap = self._snapshot
        if snap.errors_hour > self.max_errors_before_heal:
            await self.notify_admins(
                f"⚠️ Stability warning: ошибок за час {snap.errors_hour} (> {self.max_errors_before_heal})"
            )
        if snap.memory_mb > self.memory_limit_mb:
            await self.notify_admins(
                f"⚠️ Stability warning: память {snap.memory_mb:.1f}MB (> {self.memory_limit_mb}MB)"
            )

    async def notify_admins(self, text: str) -> None:
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(admin_id, text)
            except Exception as error:
                logger.warning("Failed to send stability alert to %s: %s", admin_id, error)

    def get_snapshot(self) -> StabilitySnapshot:
        return self._snapshot

    def _memory_mb(self) -> float:
        return float(self.process.memory_info().rss) / (1024 * 1024)

    async def _probe_db_response_ms(self) -> float:
        started = time.perf_counter()
        await asyncio.to_thread(self._probe_db_response_sync)
        return (time.perf_counter() - started) * 1000

    def _probe_db_response_sync(self) -> None:
        connection = sqlite3.connect(self.db_path, timeout=5)
        try:
            self.active_connections = 1
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()
            self.active_connections = 0


_monitor: StabilityMonitor | None = None


def set_stability_monitor(monitor: StabilityMonitor) -> None:
    global _monitor
    _monitor = monitor


def get_stability_monitor() -> StabilityMonitor | None:
    return _monitor
