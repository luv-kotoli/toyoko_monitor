from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


SmokingOption = Literal["-all", "noSmoking", "smoking"]
MonitorStatus = Literal["pending", "available", "unavailable", "error"]


class SearchCriteria(BaseModel):
    start_date: date
    end_date: date
    people: int = Field(default=1, ge=1, le=4)
    rooms: int = Field(default=1, ge=1, le=4)
    smoking: SmokingOption = "-all"

    @model_validator(mode="after")
    def validate_dates(self) -> "SearchCriteria":
        if self.end_date <= self.start_date:
            raise ValueError("退房日期必须晚于入住日期。")
        return self


class SubareaOption(BaseModel):
    key: str
    label: str
    hotel_count: int


class AreaOption(BaseModel):
    key: str
    label: str
    hotel_count: int
    subareas: list[SubareaOption] = Field(default_factory=list)


class HotelSummary(BaseModel):
    hotel_code: str
    name: str
    area_key: str
    area_label: str
    subarea_key: str
    subarea_label: str
    city: str | None = None
    address: str | None = None
    phone_number: str | None = None


class RoomAvailability(BaseModel):
    room_type_id: str
    room_type_name: str
    smoking: str
    general_price: int | None = None
    member_price: int | None = None
    general_vacant_room: int = 0
    member_vacant_room: int = 0


class HotelAvailability(BaseModel):
    hotel_code: str
    hotel_name: str
    checked_at: datetime
    can_reservation: bool
    has_vacancy: bool
    available_room_count: int = 0
    room_types: list[RoomAvailability] = Field(default_factory=list)
    error_message: str | None = None


class HotelSearchResult(HotelSummary):
    checked_at: datetime
    can_reservation: bool
    has_vacancy: bool
    available_room_count: int = 0
    room_types: list[RoomAvailability] = Field(default_factory=list)
    error_message: str | None = None


class HotelSearchRequest(SearchCriteria):
    hotel_codes: list[str] = Field(min_length=1)


class MonitorSelection(BaseModel):
    hotel_code: str
    room_type_id: str
    room_type_name: str
    room_type_smoking: str


class CreateMonitorTargetsRequest(SearchCriteria):
    targets: list[MonitorSelection] = Field(min_length=1)


class MonitorTarget(BaseModel):
    id: int
    hotel_code: str
    hotel_name: str
    area_key: str
    area_label: str
    subarea_key: str
    subarea_label: str
    room_type_id: str
    room_type_name: str
    room_type_smoking: str
    start_date: date
    end_date: date
    people: int
    rooms: int
    smoking: SmokingOption
    check_interval_minutes: int
    enabled: bool
    last_checked_at: datetime | None = None
    last_status: MonitorStatus = "pending"
    available_room_count: int | None = None
    general_price: int | None = None
    member_price: int | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class RefreshResponse(BaseModel):
    refreshed_count: int
