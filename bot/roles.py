from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import aiosqlite

Role = Literal["owner", "admin", "user"]


class RoleManager:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def _connect(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        return db

    async def init_schema(self) -> None:
        db = await self._connect()
        try:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS roles (
                    user_id INTEGER PRIMARY KEY,
                    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'user')),
                    granted_by INTEGER,
                    granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            await db.commit()
        finally:
            await db.close()

    async def get_role(self, user_id: int) -> Role:
        db = await self._connect()
        try:
            row = await (
                await db.execute("SELECT role FROM roles WHERE user_id = ?", (user_id,))
            ).fetchone()
            if row is None:
                return "user"
            return row["role"]
        finally:
            await db.close()

    async def set_role(self, user_id: int, role: Role, granted_by: int | None) -> None:
        db = await self._connect()
        try:
            await db.execute(
                """
                INSERT INTO roles (user_id, role, granted_by, granted_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    role = excluded.role,
                    granted_by = excluded.granted_by,
                    granted_at = excluded.granted_at
                """,
                (
                    user_id,
                    role,
                    granted_by,
                    datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            await db.commit()
        finally:
            await db.close()

    async def remove_role(self, user_id: int) -> None:
        db = await self._connect()
        try:
            await db.execute("DELETE FROM roles WHERE user_id = ?", (user_id,))
            await db.commit()
        finally:
            await db.close()

    async def is_owner(self, user_id: int) -> bool:
        return (await self.get_role(user_id)) == "owner"

    async def is_admin(self, user_id: int) -> bool:
        role = await self.get_role(user_id)
        return role in {"owner", "admin"}

    async def get_all_admins(self) -> list[int]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    "SELECT user_id FROM roles WHERE role IN ('owner', 'admin') ORDER BY user_id ASC"
                )
            ).fetchall()
            return [int(row["user_id"]) for row in rows]
        finally:
            await db.close()

    async def get_admin_roles(self) -> list[tuple[int, str]]:
        db = await self._connect()
        try:
            rows = await (
                await db.execute(
                    "SELECT user_id, role FROM roles WHERE role IN ('owner', 'admin') ORDER BY role DESC, user_id ASC"
                )
            ).fetchall()
            return [(int(row["user_id"]), str(row["role"])) for row in rows]
        finally:
            await db.close()

    async def get_owner_id(self) -> int | None:
        db = await self._connect()
        try:
            row = await (
                await db.execute("SELECT user_id FROM roles WHERE role = 'owner' LIMIT 1")
            ).fetchone()
            return int(row["user_id"]) if row else None
        finally:
            await db.close()

    async def ensure_initial_roles(self, owner_id: int | None, admin_ids: list[int]) -> None:
        db = await self._connect()
        try:
            row = await (
                await db.execute("SELECT value FROM app_meta WHERE key = 'roles_seeded_v1'")
            ).fetchone()
            if row is not None:
                return

            if owner_id is not None:
                await db.execute(
                    """
                    INSERT INTO roles (user_id, role, granted_by, granted_at)
                    VALUES (?, 'owner', ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        role='owner',
                        granted_by=excluded.granted_by,
                        granted_at=excluded.granted_at
                    """,
                    (
                        owner_id,
                        owner_id,
                        datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )

            for admin_id in admin_ids:
                if owner_id is not None and admin_id == owner_id:
                    continue
                await db.execute(
                    """
                    INSERT INTO roles (user_id, role, granted_by, granted_at)
                    VALUES (?, 'admin', ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        role='admin',
                        granted_by=excluded.granted_by,
                        granted_at=excluded.granted_at
                    """,
                    (
                        admin_id,
                        owner_id,
                        datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )

            await db.execute(
                "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('roles_seeded_v1', '1')"
            )
            await db.commit()
        finally:
            await db.close()


_role_manager: RoleManager | None = None


def set_role_manager_instance(role_manager: RoleManager) -> None:
    global _role_manager
    _role_manager = role_manager


def get_role_manager_instance() -> RoleManager | None:
    return _role_manager
