from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import MonitorRepository
from .monitor_service import MonitorService
from .schemas import (
    AreaOption,
    CreateMonitorTargetsRequest,
    HotelSearchRequest,
    HotelSearchResult,
    HotelSummary,
    MonitorTarget,
    RefreshResponse,
)
from .toyoko_client import ToyokoClient


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR.parent / "data"
DB_PATH = DATA_DIR / "toyoko_monitor.db"

repository = MonitorRepository(DB_PATH)
client = ToyokoClient()
monitor_service = MonitorService(repository=repository, client=client)


@asynccontextmanager
async def lifespan(_: FastAPI):
    repository.initialize()
    monitor_service.start()
    try:
        yield
    finally:
        await monitor_service.stop()
        await client.close()


app = FastAPI(title="Toyoko Monitor", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/areas", response_model=list[AreaOption])
async def list_areas() -> list[AreaOption]:
    return await client.list_areas()


@app.get("/api/hotels", response_model=list[HotelSummary])
async def list_hotels(
    area_key: str,
    subarea_key: str = Query(default="all"),
) -> list[HotelSummary]:
    hotels = await client.list_hotels(area_key=area_key, subarea_key=subarea_key)
    if not hotels:
        raise HTTPException(status_code=404, detail="未找到对应地区的酒店列表。")
    return hotels


@app.post("/api/search", response_model=list[HotelSearchResult])
async def search_hotels(request: HotelSearchRequest) -> list[HotelSearchResult]:
    results = await client.search_hotels(
        hotel_codes=request.hotel_codes,
        start_date=request.start_date,
        end_date=request.end_date,
        people=request.people,
        rooms=request.rooms,
        smoking=request.smoking,
    )
    if not results:
        raise HTTPException(status_code=404, detail="未找到要查询的酒店。")
    return results


@app.get("/api/monitor-targets", response_model=list[MonitorTarget])
async def list_monitor_targets() -> list[MonitorTarget]:
    return repository.list_targets()


@app.post("/api/monitor-targets", response_model=list[MonitorTarget])
async def create_monitor_targets(request: CreateMonitorTargetsRequest) -> list[MonitorTarget]:
    hotel_codes = [target.hotel_code for target in request.targets]
    hotels = await client.resolve_hotels(hotel_codes)
    hotel_map = {hotel.hotel_code: hotel for hotel in hotels}
    if not hotels:
        raise HTTPException(status_code=404, detail="未找到要加入监控的酒店。")

    repository.upsert_targets(
        {
            "hotel_code": target.hotel_code,
            "hotel_name": hotel_map[target.hotel_code].name,
            "area_key": hotel_map[target.hotel_code].area_key,
            "area_label": hotel_map[target.hotel_code].area_label,
            "subarea_key": hotel_map[target.hotel_code].subarea_key,
            "subarea_label": hotel_map[target.hotel_code].subarea_label,
            "room_type_id": target.room_type_id,
            "room_type_name": target.room_type_name,
            "room_type_smoking": target.room_type_smoking,
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "people": request.people,
            "rooms": request.rooms,
            "smoking": request.smoking,
            "check_interval_minutes": 60,
        }
        for target in request.targets
        if target.hotel_code in hotel_map
    )

    refreshed_target_ids = [
        target.id
        for target in repository.list_targets()
        if target.hotel_code in hotel_map
        and target.start_date == request.start_date
        and target.end_date == request.end_date
        and target.people == request.people
        and target.rooms == request.rooms
        and target.smoking == request.smoking
        and any(
            selection.hotel_code == target.hotel_code and selection.room_type_id == target.room_type_id
            for selection in request.targets
        )
    ]
    await monitor_service.refresh_due_targets(force=True, target_ids=refreshed_target_ids)
    return repository.list_targets()


@app.delete("/api/monitor-targets/{target_id}", status_code=204)
async def delete_monitor_target(target_id: int) -> Response:
    deleted = repository.delete_target(target_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="未找到监控项。")
    return Response(status_code=204)


@app.post("/api/monitor/run", response_model=RefreshResponse)
async def refresh_monitor_targets() -> RefreshResponse:
    refreshed_count = await monitor_service.refresh_due_targets(force=True)
    return RefreshResponse(refreshed_count=refreshed_count)
