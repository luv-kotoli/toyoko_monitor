from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import httpx

from .schemas import (
    AreaOption,
    HotelAvailability,
    HotelSearchResult,
    HotelSummary,
    RoomAvailability,
    SubareaOption,
)


AREA_LABELS = {
    "hokkaido": "北海道",
    "tohoku": "東北",
    "kanto": "関東",
    "tokai": "甲信越・北陸・東海",
    "kinki": "近畿",
    "cyugoku": "中国・四国",
    "kyushu": "九州・沖縄",
    "foreign": "海外",
}

PREFECTURE_LABELS = {
    1: "北海道",
    2: "青森県",
    3: "岩手県",
    4: "宮城県",
    5: "秋田県",
    6: "山形県",
    7: "福島県",
    8: "茨城県",
    9: "栃木県",
    10: "群馬県",
    11: "埼玉県",
    12: "千葉県",
    13: "東京都",
    14: "神奈川県",
    15: "新潟県",
    16: "富山県",
    17: "石川県",
    18: "福井県",
    19: "山梨県",
    20: "長野県",
    21: "岐阜県",
    22: "静岡県",
    23: "愛知県",
    24: "三重県",
    25: "滋賀県",
    26: "京都府",
    27: "大阪府",
    28: "兵庫県",
    29: "奈良県",
    30: "和歌山県",
    31: "鳥取県",
    32: "島根県",
    33: "岡山県",
    34: "広島県",
    35: "山口県",
    36: "徳島県",
    37: "香川県",
    38: "愛媛県",
    39: "高知県",
    40: "福岡県",
    41: "佐賀県",
    42: "長崎県",
    43: "熊本県",
    44: "大分県",
    45: "宮崎県",
    46: "鹿児島県",
    47: "沖縄県",
}

FOREIGN_SUBAREA_LABELS = {
    2: "韓国",
    3: "モンゴル",
    4: "フィリピン",
    5: "ドイツ",
    6: "フランス",
}

BUILD_ID_PATTERN = re.compile(r'"buildId":"([^"]+)"')


@dataclass(slots=True)
class Catalog:
    areas: list[AreaOption]
    hotels_by_area: dict[str, list[HotelSummary]]
    hotels_by_subarea: dict[tuple[str, str], list[HotelSummary]]
    hotels_by_code: dict[str, HotelSummary]


class ToyokoClient:
    base_url = "https://www.toyoko-inn.com"
    locale = "ja"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(30.0),
            headers={
                "User-Agent": "toyoko-monitor/0.2 (+local FastAPI monitor)",
                "Accept-Language": "ja,en-US;q=0.8,en;q=0.7",
            },
            follow_redirects=True,
        )
        self._build_id: str | None = None
        self._build_id_fetched_at: datetime | None = None
        self._build_id_lock = asyncio.Lock()
        self._catalog: Catalog | None = None
        self._catalog_fetched_at: datetime | None = None
        self._catalog_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._client.aclose()

    async def list_areas(self) -> list[AreaOption]:
        catalog = await self.get_catalog()
        return catalog.areas

    async def list_hotels(self, *, area_key: str, subarea_key: str | None = None) -> list[HotelSummary]:
        catalog = await self.get_catalog()
        if subarea_key and subarea_key != "all":
            return catalog.hotels_by_subarea.get((area_key, subarea_key), [])
        return catalog.hotels_by_area.get(area_key, [])

    async def resolve_hotels(self, hotel_codes: list[str]) -> list[HotelSummary]:
        catalog = await self.get_catalog()
        hotels: list[HotelSummary] = []
        for code in hotel_codes:
            hotel = catalog.hotels_by_code.get(code)
            if hotel:
                hotels.append(hotel)
        return hotels

    async def search_hotels(
        self,
        *,
        hotel_codes: list[str],
        start_date: date,
        end_date: date,
        people: int,
        rooms: int,
        smoking: str,
        max_concurrency: int = 4,
    ) -> list[HotelSearchResult]:
        hotels = await self.resolve_hotels(hotel_codes)
        if not hotels:
            return []

        semaphore = asyncio.Semaphore(max_concurrency)

        async def worker(hotel: HotelSummary) -> HotelSearchResult:
            async with semaphore:
                availability = await self.fetch_hotel_availability(
                    hotel_code=hotel.hotel_code,
                    start_date=start_date,
                    end_date=end_date,
                    people=people,
                    rooms=rooms,
                    smoking=smoking,
                    hotel_name_hint=hotel.name,
                )
                return HotelSearchResult(
                    **hotel.model_dump(),
                    checked_at=availability.checked_at,
                    can_reservation=availability.can_reservation,
                    has_vacancy=availability.has_vacancy,
                    available_room_count=availability.available_room_count,
                    room_types=availability.room_types,
                    error_message=availability.error_message,
                )

        hotel_order = {code: index for index, code in enumerate(hotel_codes)}
        results = await asyncio.gather(*(worker(hotel) for hotel in hotels))
        return sorted(
            results,
            key=lambda item: (
                item.error_message is not None,
                hotel_order.get(item.hotel_code, 10**9),
                item.name,
            ),
        )

    async def fetch_hotel_availability(
        self,
        *,
        hotel_code: str,
        start_date: date,
        end_date: date,
        people: int,
        rooms: int,
        smoking: str,
        hotel_name_hint: str | None = None,
    ) -> HotelAvailability:
        checked_at = datetime.now(timezone.utc)
        try:
            payload = await self._fetch_page_json(
                route_path="search/result/room_plan",
                params={
                    "hotel": hotel_code,
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "people": str(people),
                    "room": str(rooms),
                    "smoking": smoking,
                },
            )
            response = payload["pageProps"]["planResponse"]
        except Exception as exc:
            return HotelAvailability(
                hotel_code=hotel_code,
                hotel_name=hotel_name_hint or hotel_code,
                checked_at=checked_at,
                can_reservation=False,
                has_vacancy=False,
                room_types=[],
                error_message=str(exc),
            )

        room_types: list[RoomAvailability] = []
        for room in response.get("roomTypeList", []):
            specs = room.get("specs") or {}
            general_vacant, member_vacant, general_price, member_price = self._aggregate_room(room)
            room_types.append(
                RoomAvailability(
                    room_type_id=room.get("roomTypeId", ""),
                    room_type_name=room.get("roomTypeName", ""),
                    smoking="喫煙" if specs.get("isSmoking") else "禁煙",
                    general_price=general_price,
                    member_price=member_price,
                    general_vacant_room=general_vacant,
                    member_vacant_room=member_vacant,
                )
            )

        has_vacancy = any(
            max(room.general_vacant_room, room.member_vacant_room) > 0
            for room in room_types
        )
        available_room_count = sum(
            max(room.general_vacant_room, room.member_vacant_room)
            for room in room_types
        )

        return HotelAvailability(
            hotel_code=hotel_code,
            hotel_name=response.get("hotelTitle") or hotel_name_hint or hotel_code,
            checked_at=checked_at,
            can_reservation=bool(response.get("canReservation")),
            has_vacancy=has_vacancy,
            available_room_count=available_room_count,
            room_types=room_types,
            error_message=None,
        )

    async def get_catalog(self, force_refresh: bool = False) -> Catalog:
        if not force_refresh and self._catalog and self._catalog_fetched_at:
            if datetime.now(timezone.utc) - self._catalog_fetched_at < timedelta(hours=12):
                return self._catalog

        async with self._catalog_lock:
            if not force_refresh and self._catalog and self._catalog_fetched_at:
                if datetime.now(timezone.utc) - self._catalog_fetched_at < timedelta(hours=12):
                    return self._catalog

            payload = await self._fetch_page_json(route_path="hotel_list", params={})
            raw_areas = payload["pageProps"]["trpcState"]["json"]["queries"][0]["state"]["data"]["list"]

            areas: list[AreaOption] = []
            hotels_by_area: dict[str, list[HotelSummary]] = {}
            hotels_by_subarea: dict[tuple[str, str], list[HotelSummary]] = {}
            hotels_by_code: dict[str, HotelSummary] = {}

            for raw_area in raw_areas:
                area_key = raw_area["kubun"]
                area_label = AREA_LABELS.get(area_key, area_key)
                area_hotels: list[HotelSummary] = []
                subareas: list[SubareaOption] = []

                for subgroup in raw_area.get("list", []):
                    subarea_key = str(subgroup["prefecture_or_country"])
                    subarea_label = self._resolve_subarea_label(area_key, subgroup["prefecture_or_country"])
                    subarea_hotels: list[HotelSummary] = []

                    for hotel in subgroup.get("hotels", []):
                        entry = HotelSummary(
                            hotel_code=hotel["hotelCode"],
                            name=hotel["name"],
                            area_key=area_key,
                            area_label=area_label,
                            subarea_key=subarea_key,
                            subarea_label=subarea_label,
                            city=hotel.get("city"),
                            address=hotel.get("address"),
                            phone_number=hotel.get("phoneNumber"),
                        )
                        subarea_hotels.append(entry)
                        area_hotels.append(entry)
                        hotels_by_code[entry.hotel_code] = entry

                    hotels_by_subarea[(area_key, subarea_key)] = subarea_hotels
                    subareas.append(
                        SubareaOption(
                            key=subarea_key,
                            label=subarea_label,
                            hotel_count=len(subarea_hotels),
                        )
                    )

                hotels_by_area[area_key] = area_hotels
                areas.append(
                    AreaOption(
                        key=area_key,
                        label=area_label,
                        hotel_count=len(area_hotels),
                        subareas=subareas,
                    )
                )

            self._catalog = Catalog(
                areas=areas,
                hotels_by_area=hotels_by_area,
                hotels_by_subarea=hotels_by_subarea,
                hotels_by_code=hotels_by_code,
            )
            self._catalog_fetched_at = datetime.now(timezone.utc)
            return self._catalog

    async def _fetch_page_json(self, *, route_path: str, params: dict[str, str]) -> dict:
        for attempt in range(2):
            build_id = await self._get_build_id(force_refresh=attempt > 0)
            locale_prefix = "" if self.locale == "ja" else f"{self.locale}/"
            path = f"/_next/data/{build_id}/{locale_prefix}{route_path}.json"
            response = await self._client.get(path, params=params)
            if response.status_code == 404 and attempt == 0:
                self._build_id = None
                self._build_id_fetched_at = None
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("无法获取东横官网页面数据。")

    async def _get_build_id(self, force_refresh: bool = False) -> str:
        if not force_refresh and self._build_id and self._build_id_fetched_at:
            if datetime.now(timezone.utc) - self._build_id_fetched_at < timedelta(hours=1):
                return self._build_id

        async with self._build_id_lock:
            if not force_refresh and self._build_id and self._build_id_fetched_at:
                if datetime.now(timezone.utc) - self._build_id_fetched_at < timedelta(hours=1):
                    return self._build_id

            search_path = "/search/" if self.locale == "ja" else f"/{self.locale}/search/"
            response = await self._client.get(search_path)
            response.raise_for_status()
            match = BUILD_ID_PATTERN.search(response.text)
            if not match:
                raise RuntimeError("未能从东横官网提取 buildId。")
            self._build_id = match.group(1)
            self._build_id_fetched_at = datetime.now(timezone.utc)
            return self._build_id

    @staticmethod
    def _coerce_int(value: object) -> int | None:
        if value is None:
            return None
        return int(value)

    def _resolve_subarea_label(self, area_key: str, subarea_code: int) -> str:
        if area_key == "foreign":
            return FOREIGN_SUBAREA_LABELS.get(subarea_code, str(subarea_code))
        return PREFECTURE_LABELS.get(subarea_code, str(subarea_code))

    def _aggregate_room(self, room: dict) -> tuple[int, int, int | None, int | None]:
        room_vacant = room.get("vacant") or {}
        room_price = room.get("price") or {}
        plans = room.get("plans") or []

        general_vacant = self._coerce_int(room_vacant.get("generalVacantRoom"))
        member_vacant = self._coerce_int(room_vacant.get("membershipVacantRoom"))

        if general_vacant is None:
            general_vacant = max(
                (
                    self._coerce_int((plan.get("vacant") or {}).get("generalVacantRoom")) or 0
                    for plan in plans
                ),
                default=0,
            )
        if member_vacant is None:
            member_vacant = max(
                (
                    self._coerce_int((plan.get("vacant") or {}).get("membershipVacantRoom")) or 0
                    for plan in plans
                ),
                default=0,
            )

        general_price = self._coerce_int(room_price.get("generalPrice"))
        member_price = self._coerce_int(room_price.get("membershipPrice"))

        if general_price is None:
            general_price = self._pick_room_price(plans=plans, price_key="generalPrice", vacancy_key="generalVacantRoom")
        if member_price is None:
            member_price = self._pick_room_price(plans=plans, price_key="membershipPrice", vacancy_key="membershipVacantRoom")

        return general_vacant, member_vacant, general_price, member_price

    def _pick_room_price(self, *, plans: list[dict], price_key: str, vacancy_key: str) -> int | None:
        available_prices = [
            self._coerce_int((plan.get("price") or {}).get(price_key))
            for plan in plans
            if (self._coerce_int((plan.get("vacant") or {}).get(vacancy_key)) or 0) > 0
            and self._coerce_int((plan.get("price") or {}).get(price_key)) is not None
        ]
        if available_prices:
            return min(available_prices)

        all_prices = [
            self._coerce_int((plan.get("price") or {}).get(price_key))
            for plan in plans
            if self._coerce_int((plan.get("price") or {}).get(price_key)) is not None
        ]
        if all_prices:
            return min(all_prices)
        return None
