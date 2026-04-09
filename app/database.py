from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .schemas import MonitorTarget


LEGACY_DEFAULT_GROUP_NAME = "5.23-5.25大阪"
DEFAULT_CHECK_INTERVAL_MINUTES = 15


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MonitorRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        with self._connect() as connection:
            if self._needs_migration(connection):
                self._migrate_schema(connection)
            else:
                self._create_schema(connection)

    def list_targets(self) -> list[MonitorTarget]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    monitor_targets.*,
                    monitor_groups.name AS group_name
                FROM monitor_targets
                JOIN monitor_groups ON monitor_groups.id = monitor_targets.group_id
                ORDER BY
                    monitor_groups.id DESC,
                    hotel_name ASC,
                    room_type_name ASC,
                    start_date ASC,
                    end_date ASC
                """
            ).fetchall()
        return [self._row_to_target(row) for row in rows]

    def get_targets_by_ids(self, target_ids: Sequence[int]) -> list[MonitorTarget]:
        if not target_ids:
            return []

        placeholders = ",".join("?" for _ in target_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    monitor_targets.*,
                    monitor_groups.name AS group_name
                FROM monitor_targets
                JOIN monitor_groups ON monitor_groups.id = monitor_targets.group_id
                WHERE monitor_targets.id IN ({placeholders})
                ORDER BY monitor_groups.id DESC, hotel_name ASC, room_type_name ASC
                """,
                list(target_ids),
            ).fetchall()
        return [self._row_to_target(row) for row in rows]

    def get_targets_by_group_id(self, group_id: int) -> list[MonitorTarget]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    monitor_targets.*,
                    monitor_groups.name AS group_name
                FROM monitor_targets
                JOIN monitor_groups ON monitor_groups.id = monitor_targets.group_id
                WHERE monitor_targets.group_id = ?
                ORDER BY hotel_name ASC, room_type_name ASC
                """,
                (group_id,),
            ).fetchall()
        return [self._row_to_target(row) for row in rows]

    def create_group(self, name: str) -> int:
        with self._connect() as connection:
            return self._create_group_row(connection, name=name)

    def rename_group(self, group_id: int, name: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE monitor_groups
                SET
                    name = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (name, utc_now().isoformat(), group_id),
            )
            return cursor.rowcount > 0

    def set_group_enabled(self, group_id: int, enabled: bool) -> bool:
        now = utc_now().isoformat()
        with self._connect() as connection:
            group_exists = connection.execute(
                "SELECT 1 FROM monitor_groups WHERE id = ?",
                (group_id,),
            ).fetchone()
            if not group_exists:
                return False
            connection.execute(
                """
                UPDATE monitor_targets
                SET
                    enabled = ?,
                    updated_at = ?
                WHERE group_id = ?
                """,
                (1 if enabled else 0, now, group_id),
            )
            connection.execute(
                """
                UPDATE monitor_groups
                SET
                    updated_at = ?
                WHERE id = ?
                """,
                (now, group_id),
            )
            return True

    def delete_group(self, group_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM monitor_groups WHERE id = ?",
                (group_id,),
            )
            return cursor.rowcount > 0

    def upsert_targets(self, targets: Iterable[dict[str, object]]) -> None:
        now = utc_now().isoformat()
        with self._connect() as connection:
            for target in targets:
                connection.execute(
                    """
                    INSERT INTO monitor_targets (
                        group_id,
                        hotel_code,
                        hotel_name,
                        area_key,
                        area_label,
                        subarea_key,
                        subarea_label,
                        room_type_id,
                        room_type_name,
                        room_type_smoking,
                        start_date,
                        end_date,
                        people,
                        rooms,
                        smoking,
                        check_interval_minutes,
                        enabled,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(hotel_code, room_type_id, start_date, end_date, people, rooms, smoking)
                    DO UPDATE SET
                        group_id = excluded.group_id,
                        hotel_name = excluded.hotel_name,
                        area_key = excluded.area_key,
                        area_label = excluded.area_label,
                        subarea_key = excluded.subarea_key,
                        subarea_label = excluded.subarea_label,
                        room_type_name = excluded.room_type_name,
                        room_type_smoking = excluded.room_type_smoking,
                        check_interval_minutes = excluded.check_interval_minutes,
                        enabled = 1,
                        updated_at = excluded.updated_at
                    """,
                    (
                        target["group_id"],
                        target["hotel_code"],
                        target["hotel_name"],
                        target["area_key"],
                        target["area_label"],
                        target["subarea_key"],
                        target["subarea_label"],
                        target["room_type_id"],
                        target["room_type_name"],
                        target["room_type_smoking"],
                        target["start_date"],
                        target["end_date"],
                        target["people"],
                        target["rooms"],
                        target["smoking"],
                        target.get("check_interval_minutes", DEFAULT_CHECK_INTERVAL_MINUTES),
                        now,
                        now,
                    ),
                )

    def delete_target(self, target_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT group_id FROM monitor_targets WHERE id = ?",
                (target_id,),
            ).fetchone()
            if not row:
                return False
            cursor = connection.execute(
                "DELETE FROM monitor_targets WHERE id = ?",
                (target_id,),
            )
            if cursor.rowcount > 0:
                self._delete_group_if_empty(connection, row["group_id"])
                return True
            return False

    def update_target_result(
        self,
        *,
        target_id: int,
        checked_at: datetime,
        last_status: str,
        available_room_count: int,
        general_price: int | None,
        member_price: int | None,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE monitor_targets
                SET
                    last_checked_at = ?,
                    last_status = ?,
                    available_room_count = ?,
                    general_price = ?,
                    member_price = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    checked_at.isoformat(),
                    last_status,
                    available_room_count,
                    general_price,
                    member_price,
                    error_message,
                    utc_now().isoformat(),
                    target_id,
                ),
            )

    def update_target_error(self, target_id: int, error_message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE monitor_targets
                SET
                    last_checked_at = ?,
                    last_status = 'error',
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    utc_now().isoformat(),
                    error_message,
                    utc_now().isoformat(),
                    target_id,
                ),
            )

    def set_all_check_interval_minutes(self, check_interval_minutes: int) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE monitor_targets
                SET
                    check_interval_minutes = ?,
                    updated_at = ?
                WHERE check_interval_minutes != ?
                """,
                (
                    check_interval_minutes,
                    utc_now().isoformat(),
                    check_interval_minutes,
                ),
            )
            return cursor.rowcount

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _needs_migration(self, connection: sqlite3.Connection) -> bool:
        legacy_table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'monitor_targets_legacy'
            """
        ).fetchone()
        if legacy_table_exists:
            return True

        table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'monitor_targets'
            """
        ).fetchone()
        if not table_exists:
            return False

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(monitor_targets)").fetchall()
        }
        required_columns = {
            "group_id",
            "subarea_key",
            "subarea_label",
            "room_type_id",
            "room_type_name",
            "room_type_smoking",
            "general_price",
            "member_price",
        }
        group_table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'monitor_groups'
            """
        ).fetchone()
        return not required_columns.issubset(columns) or not group_table_exists

    def _migrate_schema(self, connection: sqlite3.Connection) -> None:
        legacy_table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'monitor_targets_legacy'
            """
        ).fetchone()
        if not legacy_table_exists:
            connection.execute("ALTER TABLE monitor_targets RENAME TO monitor_targets_legacy")

        self._create_schema(connection)
        connection.execute("DELETE FROM monitor_targets")
        connection.execute("DELETE FROM monitor_groups")
        default_group_id = self._create_group_row(connection, name=LEGACY_DEFAULT_GROUP_NAME)

        legacy_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(monitor_targets_legacy)").fetchall()
        }
        general_price_column = "general_price" if "general_price" in legacy_columns else "lowest_general_price"
        member_price_column = "member_price" if "member_price" in legacy_columns else "lowest_member_price"
        subarea_key_expr = "subarea_key" if "subarea_key" in legacy_columns else "''"
        subarea_label_expr = "subarea_label" if "subarea_label" in legacy_columns else "''"
        room_type_id_expr = "room_type_id" if "room_type_id" in legacy_columns else "''"
        room_type_name_expr = "room_type_name" if "room_type_name" in legacy_columns else "'全部房型'"
        room_type_smoking_expr = "room_type_smoking" if "room_type_smoking" in legacy_columns else "''"

        connection.execute(
            f"""
            INSERT INTO monitor_targets (
                id,
                group_id,
                hotel_code,
                hotel_name,
                area_key,
                area_label,
                subarea_key,
                subarea_label,
                room_type_id,
                room_type_name,
                room_type_smoking,
                start_date,
                end_date,
                people,
                rooms,
                smoking,
                check_interval_minutes,
                enabled,
                last_checked_at,
                last_status,
                available_room_count,
                general_price,
                member_price,
                error_message,
                created_at,
                updated_at
            )
            SELECT
                id,
                ?,
                hotel_code,
                hotel_name,
                area_key,
                area_label,
                {subarea_key_expr},
                {subarea_label_expr},
                {room_type_id_expr},
                {room_type_name_expr},
                {room_type_smoking_expr},
                start_date,
                end_date,
                people,
                rooms,
                smoking,
                check_interval_minutes,
                enabled,
                last_checked_at,
                last_status,
                available_room_count,
                {general_price_column},
                {member_price_column},
                error_message,
                created_at,
                updated_at
            FROM monitor_targets_legacy
            """,
            (default_group_id,),
        )
        connection.execute("DROP TABLE monitor_targets_legacy")

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS monitor_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS monitor_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                hotel_code TEXT NOT NULL,
                hotel_name TEXT NOT NULL,
                area_key TEXT NOT NULL,
                area_label TEXT NOT NULL,
                subarea_key TEXT NOT NULL DEFAULT '',
                subarea_label TEXT NOT NULL DEFAULT '',
                room_type_id TEXT NOT NULL DEFAULT '',
                room_type_name TEXT NOT NULL DEFAULT '全部房型',
                room_type_smoking TEXT NOT NULL DEFAULT '',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                people INTEGER NOT NULL,
                rooms INTEGER NOT NULL,
                smoking TEXT NOT NULL,
                check_interval_minutes INTEGER NOT NULL DEFAULT 15,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_checked_at TEXT,
                last_status TEXT NOT NULL DEFAULT 'pending',
                available_room_count INTEGER,
                general_price INTEGER,
                member_price INTEGER,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(hotel_code, room_type_id, start_date, end_date, people, rooms, smoking),
                FOREIGN KEY(group_id) REFERENCES monitor_groups(id) ON DELETE CASCADE
            );
            """
        )

    def _row_to_target(self, row: sqlite3.Row) -> MonitorTarget:
        return MonitorTarget(
            id=row["id"],
            group_id=row["group_id"],
            group_name=row["group_name"],
            hotel_code=row["hotel_code"],
            hotel_name=row["hotel_name"],
            area_key=row["area_key"],
            area_label=row["area_label"],
            subarea_key=row["subarea_key"],
            subarea_label=row["subarea_label"],
            room_type_id=row["room_type_id"],
            room_type_name=row["room_type_name"],
            room_type_smoking=row["room_type_smoking"],
            start_date=date.fromisoformat(row["start_date"]),
            end_date=date.fromisoformat(row["end_date"]),
            people=row["people"],
            rooms=row["rooms"],
            smoking=row["smoking"],
            check_interval_minutes=row["check_interval_minutes"],
            enabled=bool(row["enabled"]),
            last_checked_at=datetime.fromisoformat(row["last_checked_at"]) if row["last_checked_at"] else None,
            last_status=row["last_status"],
            available_room_count=row["available_room_count"],
            general_price=row["general_price"],
            member_price=row["member_price"],
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _create_group_row(self, connection: sqlite3.Connection, *, name: str) -> int:
        now = utc_now().isoformat()
        cursor = connection.execute(
            """
            INSERT INTO monitor_groups (name, created_at, updated_at)
            VALUES (?, ?, ?)
            """,
            (name, now, now),
        )
        return int(cursor.lastrowid)

    def _delete_group_if_empty(self, connection: sqlite3.Connection, group_id: int) -> None:
        remaining = connection.execute(
            "SELECT 1 FROM monitor_targets WHERE group_id = ? LIMIT 1",
            (group_id,),
        ).fetchone()
        if remaining:
            return
        connection.execute("DELETE FROM monitor_groups WHERE id = ?", (group_id,))
