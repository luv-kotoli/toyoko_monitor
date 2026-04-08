from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, model_validator

from .log_utils import PUSH_CONTENT_LOGGER_NAME, PUSH_RESULT_LOGGER_NAME
from .serverchan import NotificationSnapshot


logger = logging.getLogger(__name__)
push_content_logger = logging.getLogger(PUSH_CONTENT_LOGGER_NAME)
push_result_logger = logging.getLogger(PUSH_RESULT_LOGGER_NAME)

BarkLevel = Literal["active", "timeSensitive", "passive", "critical"]
DEFAULT_BARK_BASE_URL = "https://api.day.app"
DEFAULT_BARK_LEVEL: BarkLevel = "timeSensitive"


class BarkConfig(BaseModel):
    base_url: str = DEFAULT_BARK_BASE_URL
    device_key: str = Field(min_length=1)
    title_prefix: str = "Toyoko Monitor"
    url: str | None = None
    group: str | None = None
    icon: str | None = None
    sound: str | None = None
    call: bool = False
    ciphertext: str | None = None
    level: BarkLevel | None = DEFAULT_BARK_LEVEL

    @model_validator(mode="after")
    def normalize(self) -> "BarkConfig":
        self.base_url = (self.base_url or DEFAULT_BARK_BASE_URL).strip().rstrip("/") or DEFAULT_BARK_BASE_URL
        self.device_key = self.device_key.strip()
        self.title_prefix = (self.title_prefix or "Toyoko Monitor").strip() or "Toyoko Monitor"
        self.url = self._normalize_optional(self.url)
        self.group = self._normalize_optional(self.group)
        self.icon = self._normalize_optional(self.icon)
        self.sound = self._normalize_optional(self.sound)
        self.ciphertext = self._normalize_optional(self.ciphertext)
        self.level = self.level or DEFAULT_BARK_LEVEL
        return self

    @staticmethod
    def _normalize_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class BarkNotifier:
    def __init__(self, config: BarkConfig) -> None:
        self.config = config
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            headers={
                "User-Agent": "toyoko-monitor/0.4 (+Bark notifier)",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def send_available_targets(self, snapshots: list[NotificationSnapshot]) -> dict[str, Any]:
        if not snapshots:
            return {}

        ordered = self._order_snapshots(snapshots)
        latest = max(snapshot.checked_at for snapshot in ordered).astimezone()
        title = self._build_title(ordered)
        subtitle = self._build_subtitle(ordered, latest=latest)
        body = self._build_body(ordered, latest=latest)
        return await self.send_test_message(title=title, subtitle=subtitle, body=body)

    async def send_test_message(
        self,
        *,
        title: str,
        subtitle: str | None,
        body: str,
    ) -> dict[str, Any]:
        payload = {
            "title": title,
            "body": body,
        }
        if subtitle:
            payload["subtitle"] = subtitle

        url, params = self._build_request_target()
        push_content_logger.info(
            "Bark request payload:\n%s",
            json.dumps({"url": url, "params": params, "data": payload}, ensure_ascii=False, indent=2),
        )
        response = await self._client.post(url, params=params, data=payload)
        response.raise_for_status()
        response_data = self._parse_response_data(response)
        push_result_logger.info(
            "Bark send response:\n%s",
            json.dumps(response_data, ensure_ascii=False, indent=2),
        )
        logger.info("Bark notification sent: provider_response=%s", response_data)
        return response_data

    def _build_request_target(self) -> tuple[str, dict[str, str]]:
        level = self.config.level or DEFAULT_BARK_LEVEL
        params = {"badge": "1"}

        if self.config.url:
            params["url"] = self.config.url
        if self.config.group:
            params["group"] = self.config.group
        if self.config.icon:
            params["icon"] = self.config.icon
        if self.config.ciphertext:
            params["ciphertext"] = self.config.ciphertext

        if level == "critical":
            params["level"] = "critical"
            params["call"] = "1"
        elif self.config.call:
            params["level"] = level
            params["call"] = "1"
        else:
            params["level"] = level
            if self.config.sound:
                params["sound"] = self.config.sound

        return f"{self.config.base_url}/{self.config.device_key}", params

    @staticmethod
    def _order_snapshots(snapshots: list[NotificationSnapshot]) -> list[NotificationSnapshot]:
        return sorted(
            snapshots,
            key=lambda item: (
                item.area_label,
                item.subarea_label,
                item.hotel_name,
                item.room_type_name,
                item.room_type_smoking,
            ),
        )

    @staticmethod
    def _build_title(snapshots: list[NotificationSnapshot]) -> str:
        return snapshots[0].hotel_name[:120]

    def _build_subtitle(self, snapshots: list[NotificationSnapshot], *, latest: datetime) -> str:
        names = " / ".join(snapshot.hotel_name for snapshot in snapshots[:2])
        if len(snapshots) > 2:
            names = f"{names} 等{len(snapshots)}项"
        return f"{latest:%m-%d %H:%M} 有空房: {names}"[:120]

    def _build_body(self, snapshots: list[NotificationSnapshot], *, latest: datetime) -> str:
        lines = [
            f"刷新时间: {latest:%Y-%m-%d %H:%M:%S %Z}",
            "",
        ]
        for index, snapshot in enumerate(snapshots, start=1):
            lines.extend(
                [
                    f"{index}. {snapshot.hotel_name}",
                    f"地区: {snapshot.area_label} / {snapshot.subarea_label}",
                    f"房型: {snapshot.room_type_name}",
                    f"可订房数: {snapshot.available_room_count}",
                    f"日期: {snapshot.start_date.isoformat()} -> {snapshot.end_date.isoformat()}",
                    f"价格: {self._format_price(snapshot.general_price, snapshot.member_price)}",
                    "",
                ]
            )
        return "\n".join(lines).strip()

    @staticmethod
    def _format_price(general_price: int | None, member_price: int | None) -> str:
        general_text = f"普通价 ¥{general_price}" if general_price is not None else "普通价 -"
        member_text = f"会员价 ¥{member_price}" if member_price is not None else "会员价 -"
        return f"{general_text} / {member_text}"

    @staticmethod
    def _parse_response_data(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            data = {"message": response.text}

        if isinstance(data, dict):
            return data
        return {"data": data}
