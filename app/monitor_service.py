from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from datetime import datetime, timedelta

from .database import MonitorRepository, utc_now
from .notifications import NotificationService
from .schemas import MonitorTarget
from .serverchan import NotificationSnapshot
from .toyoko_client import ToyokoClient


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RefreshOutcome:
    target: MonitorTarget
    checked_at: datetime
    last_status: str
    available_room_count: int
    general_price: int | None
    member_price: int | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class RefreshRequestKey:
    start_date: date
    end_date: date
    people: int
    rooms: int
    smoking: str


class MonitorService:
    def __init__(
        self,
        *,
        repository: MonitorRepository,
        client: ToyokoClient,
        notifier: NotificationService | None = None,
        refresh_loop_seconds: int = 60,
        max_concurrency: int = 3,
    ) -> None:
        self.repository = repository
        self.client = client
        self.notifier = notifier
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
                logger.info("Monitor refresh skipped: no targets to process")
                return 0
            logger.info(
                "Monitor refresh started: target_count=%s force=%s target_ids=%s",
                len(targets),
                force,
                target_ids,
            )
            target_groups = self._group_targets_by_request(targets)
            logger.info(
                "Monitor refresh deduplicated requests: unique_request_count=%s",
                len(target_groups),
            )

            semaphore = asyncio.Semaphore(self.max_concurrency)

            async def worker(
                request_key: RefreshRequestKey,
                grouped_targets: list[MonitorTarget],
            ) -> list[RefreshOutcome]:
                async with semaphore:
                    try:
                        return await self._refresh_grouped_targets(
                            request_key=request_key,
                            grouped_targets=grouped_targets,
                        )
                    except Exception as exc:
                        for target in grouped_targets:
                            self.repository.update_target_error(target.id, str(exc))
                        logger.exception(
                            "Unexpected monitor refresh failure for request hotels=%s target_ids=%s",
                            sorted({target.hotel_code for target in grouped_targets}),
                            [target.id for target in grouped_targets],
                        )
                        return []

            grouped_outcomes = await asyncio.gather(
                *(worker(request_key, grouped_targets) for request_key, grouped_targets in target_groups.items())
            )
            completed_outcomes = [outcome for outcomes in grouped_outcomes for outcome in outcomes]
            await self._notify_available_outcomes(completed_outcomes)
            logger.info(
                "Monitor refresh finished: target_count=%s unique_request_count=%s available=%s error=%s",
                len(targets),
                len(target_groups),
                sum(1 for outcome in completed_outcomes if outcome.last_status == "available"),
                sum(1 for outcome in completed_outcomes if outcome.last_status == "error"),
            )
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

    def _group_targets_by_request(
        self,
        targets: list[MonitorTarget],
    ) -> dict[RefreshRequestKey, list[MonitorTarget]]:
        grouped_targets: dict[RefreshRequestKey, list[MonitorTarget]] = {}
        for target in targets:
            request_key = RefreshRequestKey(
                start_date=target.start_date,
                end_date=target.end_date,
                people=target.people,
                rooms=target.rooms,
                smoking=target.smoking,
            )
            grouped_targets.setdefault(request_key, []).append(target)
        return grouped_targets

    async def _refresh_grouped_targets(
        self,
        *,
        request_key: RefreshRequestKey,
        grouped_targets: list[MonitorTarget],
    ) -> list[RefreshOutcome]:
        hotel_groups = self._group_targets_by_hotel(grouped_targets)
        if len(hotel_groups) <= 1:
            return await self._refresh_hotel_groups(request_key=request_key, hotel_groups=hotel_groups)

        try:
            price_availability = await self.client.fetch_hotels_price_availability(
                hotel_codes=sorted(hotel_groups),
                start_date=request_key.start_date,
                end_date=request_key.end_date,
                people=request_key.people,
                rooms=request_key.rooms,
                smoking=request_key.smoking,
            )
        except Exception:
            logger.exception(
                "Batch price prefilter failed; falling back to room_plan fetch: hotels=%s start=%s end=%s people=%s rooms=%s smoking=%s",
                sorted(hotel_groups),
                request_key.start_date,
                request_key.end_date,
                request_key.people,
                request_key.rooms,
                request_key.smoking,
            )
            return await self._refresh_hotel_groups(request_key=request_key, hotel_groups=hotel_groups)

        outcomes: list[RefreshOutcome] = []
        hotels_to_refresh: dict[str, list[MonitorTarget]] = {}
        for hotel_code, hotel_targets in hotel_groups.items():
            availability = price_availability.get(hotel_code)
            if availability is None or (
                availability.exist_enough_vacant_rooms and not availability.is_under_maintenance
            ):
                hotels_to_refresh[hotel_code] = hotel_targets
                continue

            hotel_outcomes = [
                self._build_prefilter_unavailable_outcome(target=target, checked_at=availability.checked_at)
                for target in hotel_targets
            ]
            for outcome in hotel_outcomes:
                self._persist_refresh_outcome(outcome)
            outcomes.extend(hotel_outcomes)

        logger.info(
            "Monitor price prefilter applied: hotel_count=%s detail_refresh_count=%s skipped_unavailable_count=%s start=%s end=%s people=%s rooms=%s smoking=%s",
            len(hotel_groups),
            len(hotels_to_refresh),
            len(hotel_groups) - len(hotels_to_refresh),
            request_key.start_date,
            request_key.end_date,
            request_key.people,
            request_key.rooms,
            request_key.smoking,
        )
        outcomes.extend(
            await self._refresh_hotel_groups(request_key=request_key, hotel_groups=hotels_to_refresh)
        )
        return outcomes

    @staticmethod
    def _group_targets_by_hotel(targets: list[MonitorTarget]) -> dict[str, list[MonitorTarget]]:
        hotel_groups: dict[str, list[MonitorTarget]] = {}
        for target in targets:
            hotel_groups.setdefault(target.hotel_code, []).append(target)
        return hotel_groups

    async def _refresh_hotel_groups(
        self,
        *,
        request_key: RefreshRequestKey,
        hotel_groups: dict[str, list[MonitorTarget]],
    ) -> list[RefreshOutcome]:
        if not hotel_groups:
            return []

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def worker(hotel_code: str, hotel_targets: list[MonitorTarget]) -> list[RefreshOutcome]:
            async with semaphore:
                availability = await self.client.fetch_hotel_availability(
                    hotel_code=hotel_code,
                    start_date=request_key.start_date,
                    end_date=request_key.end_date,
                    people=request_key.people,
                    rooms=request_key.rooms,
                    smoking=request_key.smoking,
                    hotel_name_hint=hotel_targets[0].hotel_name,
                )
                hotel_outcomes = [
                    self._build_refresh_outcome(target=target, availability=availability)
                    for target in hotel_targets
                ]
                for outcome in hotel_outcomes:
                    self._persist_refresh_outcome(outcome)
                return hotel_outcomes

        grouped_outcomes = await asyncio.gather(
            *(worker(hotel_code, hotel_targets) for hotel_code, hotel_targets in hotel_groups.items())
        )
        return [outcome for outcomes in grouped_outcomes for outcome in outcomes]

    @staticmethod
    def _build_prefilter_unavailable_outcome(
        *,
        target: MonitorTarget,
        checked_at: datetime,
    ) -> RefreshOutcome:
        return RefreshOutcome(
            target=target,
            checked_at=checked_at,
            last_status="unavailable",
            available_room_count=0,
            general_price=None,
            member_price=None,
            error_message=None,
        )

    def _build_refresh_outcome(self, *, target: MonitorTarget, availability) -> RefreshOutcome:
        if availability.error_message:
            return RefreshOutcome(
                target=target,
                checked_at=availability.checked_at,
                last_status="error",
                available_room_count=0,
                general_price=None,
                member_price=None,
                error_message=availability.error_message,
            )

        if not target.room_type_id:
            return RefreshOutcome(
                target=target,
                checked_at=availability.checked_at,
                last_status="available" if availability.has_vacancy else "unavailable",
                available_room_count=availability.available_room_count,
                general_price=None,
                member_price=None,
                error_message=availability.error_message,
            )

        selected_room = next(
            (room for room in availability.room_types if room.room_type_id == target.room_type_id),
            None,
        )
        if selected_room is None:
            return RefreshOutcome(
                target=target,
                checked_at=availability.checked_at,
                last_status="error",
                available_room_count=0,
                general_price=None,
                member_price=None,
                error_message="当前查询结果中未找到该房型。",
            )

        available_room_count = max(selected_room.general_vacant_room, selected_room.member_vacant_room)
        return RefreshOutcome(
            target=target,
            checked_at=availability.checked_at,
            last_status="available" if available_room_count > 0 else "unavailable",
            available_room_count=available_room_count,
            general_price=selected_room.general_price,
            member_price=selected_room.member_price,
            error_message=availability.error_message,
        )

    def _persist_refresh_outcome(self, outcome: RefreshOutcome) -> None:
        self.repository.update_target_result(
            target_id=outcome.target.id,
            checked_at=outcome.checked_at,
            last_status=outcome.last_status,
            available_room_count=outcome.available_room_count,
            general_price=outcome.general_price,
            member_price=outcome.member_price,
            error_message=outcome.error_message,
        )

    async def _notify_available_outcomes(self, outcomes: list[RefreshOutcome]) -> None:
        if self.notifier is None:
            return

        available_outcomes = [
            outcome
            for outcome in outcomes
            if outcome.last_status == "available" and outcome.available_room_count > 0
        ]
        if not available_outcomes:
            return

        try:
            hotel_codes = sorted({outcome.target.hotel_code for outcome in available_outcomes})
            hotels = await self.client.resolve_hotels(hotel_codes)
            hotel_map = {hotel.hotel_code: hotel for hotel in hotels}
            snapshots = []
            for outcome in available_outcomes:
                hotel = hotel_map.get(outcome.target.hotel_code)
                snapshots.append(
                    NotificationSnapshot(
                        hotel_code=outcome.target.hotel_code,
                        hotel_name=outcome.target.hotel_name,
                        area_label=outcome.target.area_label,
                        subarea_label=outcome.target.subarea_label,
                        address=hotel.address if hotel else None,
                        phone_number=hotel.phone_number if hotel else None,
                        room_type_name=outcome.target.room_type_name or "全部房型",
                        room_type_smoking=outcome.target.room_type_smoking,
                        start_date=outcome.target.start_date,
                        end_date=outcome.target.end_date,
                        people=outcome.target.people,
                        rooms=outcome.target.rooms,
                        smoking=outcome.target.smoking,
                        checked_at=outcome.checked_at,
                        available_room_count=outcome.available_room_count,
                        general_price=outcome.general_price,
                        member_price=outcome.member_price,
                    )
                )
            await self.notifier.send_available_targets(snapshots)
        except Exception:
            logger.exception("Failed to send push notification")
