from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .schemas import MonitorTarget, RoomAvailability


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
                SELECT *
                FROM monitor_targets
                ORDER BY hotel_name ASC, room_type_name ASC, start_date ASC, end_date ASC
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
                SELECT *
                FROM monitor_targets
                WHERE id IN ({placeholders})
                ORDER BY hotel_name ASC, room_type_name ASC
                """,
                list(target_ids),
            ).fetchall()
        return [self._row_to_target(row) for row in rows]

    def upsert_targets(self, targets: Iterable[dict[str, object]]) -> None:
        now = utc_now().isoformat()
        with self._connect() as connection:
            for target in targets:
                connection.execute(
                    """
                    INSERT INTO monitor_targets (
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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(hotel_code, room_type_id, start_date, end_date, people, rooms, smoking)
                    DO UPDATE SET
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
                        target.get("check_interval_minutes", 60),
                        now,
                        now,
                    ),
                )

    def delete_target(self, target_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM monitor_targets WHERE id = ?",
                (target_id,),
            )
            return cursor.rowcount > 0

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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _needs_migration(self, connection: sqlite3.Connection) -> bool:
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
            "subarea_key",
            "subarea_label",
            "room_type_id",
            "room_type_name",
            "room_type_smoking",
            "general_price",
            "member_price",
        }
        return not required_columns.issubset(columns)

    def _migrate_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute("ALTER TABLE monitor_targets RENAME TO monitor_targets_legacy")
        self._create_schema(connection)
        connection.execute(
            """
            INSERT INTO monitor_targets (
                id,
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
                hotel_code,
                hotel_name,
                area_key,
                area_label,
                '',
                '',
                '',
                '全部房型',
                '',
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
                lowest_general_price,
                lowest_member_price,
                error_message,
                created_at,
                updated_at
            FROM monitor_targets_legacy
            """
        )
        connection.execute("DROP TABLE monitor_targets_legacy")

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS monitor_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                check_interval_minutes INTEGER NOT NULL DEFAULT 60,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_checked_at TEXT,
                last_status TEXT NOT NULL DEFAULT 'pending',
                available_room_count INTEGER,
                general_price INTEGER,
                member_price INTEGER,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(hotel_code, room_type_id, start_date, end_date, people, rooms, smoking)
            );
            """
        )

    def _row_to_target(self, row: sqlite3.Row) -> MonitorTarget:
        return MonitorTarget(
            id=row["id"],
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
