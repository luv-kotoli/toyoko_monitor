from __future__ import annotations

import asyncio
from datetime import timedelta

from .database import MonitorRepository, utc_now
from .schemas import MonitorTarget
from .toyoko_client import ToyokoClient


class MonitorService:
    def __init__(
        self,
        *,
        repository: MonitorRepository,
        client: ToyokoClient,
        refresh_loop_seconds: int = 60,
        max_concurrency: int = 3,
    ) -> None:
        self.repository = repository
        self.client = client
        self.refresh_loop_seconds = refresh_loop_seconds
        self.max_concurrency = max_concurrency
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._refresh_lock = asyncio.Lock()

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def refresh_due_targets(
        self,
        *,
        force: bool = False,
        target_ids: list[int] | None = None,
    ) -> int:
        async with self._refresh_lock:
            targets = self._resolve_targets(force=force, target_ids=target_ids)
            if not targets:
                return 0

            semaphore = asyncio.Semaphore(self.max_concurrency)

            async def worker(target: MonitorTarget) -> None:
                async with semaphore:
                    try:
                        availability = await self.client.fetch_hotel_availability(
                            hotel_code=target.hotel_code,
                            start_date=target.start_date,
                            end_date=target.end_date,
                            people=target.people,
                            rooms=target.rooms,
                            smoking=target.smoking,
                            hotel_name_hint=target.hotel_name,
                        )
                        self._update_target_from_availability(target=target, availability=availability)
                    except Exception as exc:
                        self.repository.update_target_error(target.id, str(exc))

            await asyncio.gather(*(worker(target) for target in targets))
            return len(targets)

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            await self.refresh_due_targets(force=False)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.refresh_loop_seconds)
            except TimeoutError:
                continue

    def _resolve_targets(
        self,
        *,
        force: bool,
        target_ids: list[int] | None,
    ) -> list[MonitorTarget]:
        if target_ids is not None:
            return self.repository.get_targets_by_ids(target_ids)

        targets = [target for target in self.repository.list_targets() if target.enabled]
        if force:
            return targets

        now = utc_now()
        due_targets: list[MonitorTarget] = []
        for target in targets:
            if target.last_checked_at is None:
                due_targets.append(target)
                continue
            if target.last_checked_at <= now - timedelta(minutes=target.check_interval_minutes):
                due_targets.append(target)
        return due_targets

    def _update_target_from_availability(self, *, target: MonitorTarget, availability) -> None:
        if not target.room_type_id:
            self.repository.update_target_result(
                target_id=target.id,
                checked_at=availability.checked_at,
                last_status="available" if availability.has_vacancy else "unavailable",
                available_room_count=availability.available_room_count,
                general_price=None,
                member_price=None,
                error_message=availability.error_message,
            )
            return

        selected_room = next(
            (room for room in availability.room_types if room.room_type_id == target.room_type_id),
            None,
        )
        if selected_room is None:
            self.repository.update_target_error(target.id, "当前查询结果中未找到该房型。")
            return

        available_room_count = max(selected_room.general_vacant_room, selected_room.member_vacant_room)
        self.repository.update_target_result(
            target_id=target.id,
            checked_at=availability.checked_at,
            last_status="available" if available_room_count > 0 else "unavailable",
            available_room_count=available_room_count,
            general_price=selected_room.general_price,
            member_price=selected_room.member_price,
            error_message=availability.error_message,
        )
