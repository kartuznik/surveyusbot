from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class ErrorRecord:
    timestamp: str
    error_type: str
    message: str
    traceback: str


class ErrorTracker:
    def __init__(self, maxlen: int = 1000, log_path: str = "error_log.json") -> None:
        self._errors: deque[ErrorRecord] = deque(maxlen=maxlen)
        self._log_path = Path(log_path)

    def add_error(self, error_type: str, message: str, traceback: str) -> None:
        record = ErrorRecord(
            timestamp=datetime.now(tz=UTC).isoformat(),
            error_type=error_type,
            message=message,
            traceback=traceback,
        )
        self._errors.append(record)
        self._persist()

    def get_errors_count(self, period: str = "hour") -> int:
        now = datetime.now(tz=UTC)
        if period == "day":
            border = now - timedelta(days=1)
        else:
            border = now - timedelta(hours=1)
        return sum(
            1 for item in self._errors if datetime.fromisoformat(item.timestamp) >= border
        )

    def get_recent_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        items = list(self._errors)[-limit:]
        return [asdict(item) for item in reversed(items)]

    def clear_old_errors(self, older_than_hours: int = 24) -> None:
        border = datetime.now(tz=UTC) - timedelta(hours=older_than_hours)
        filtered = [item for item in self._errors if datetime.fromisoformat(item.timestamp) >= border]
        self._errors = deque(filtered, maxlen=self._errors.maxlen)
        self._persist()

    def count_since_seconds(self, seconds: int) -> int:
        border = datetime.now(tz=UTC) - timedelta(seconds=seconds)
        return sum(
            1 for item in self._errors if datetime.fromisoformat(item.timestamp) >= border
        )

    def last_error(self) -> dict[str, Any] | None:
        if not self._errors:
            return None
        return asdict(self._errors[-1])

    def _persist(self) -> None:
        payload = [asdict(item) for item in self._errors]
        self._log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


_tracker: ErrorTracker | None = None


def get_error_tracker() -> ErrorTracker:
    global _tracker
    if _tracker is None:
        _tracker = ErrorTracker()
    return _tracker
