from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .log_utils import PUSH_CONTENT_LOGGER_NAME, PUSH_RESULT_LOGGER_NAME


logger = logging.getLogger(__name__)
push_content_logger = logging.getLogger(PUSH_CONTENT_LOGGER_NAME)
push_result_logger = logging.getLogger(PUSH_RESULT_LOGGER_NAME)

SMOKING_LABELS = {
    "-all": "不限",
    "noSmoking": "禁煙指定",
    "smoking": "喫煙指定",
}


class ServerChanConfig(BaseModel):
    enabled: bool = True
    send_key: str = Field(min_length=1)
    channel: str = "9"
    noip: int | None = 1
    title_prefix: str = "Toyoko Monitor"


@dataclass(slots=True)
class NotificationSnapshot:
    hotel_code: str
    hotel_name: str
    area_label: str
    subarea_label: str
    address: str | None
    phone_number: str | None
    room_type_name: str
    room_type_smoking: str
    start_date: date
    end_date: date
    people: int
    rooms: int
    smoking: str
    checked_at: datetime
    available_room_count: int
    general_price: int | None
    member_price: int | None


class ServerChanNotifier:
    def __init__(self, config: ServerChanConfig) -> None:
        self.config = config
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            headers={
                "User-Agent": "toyoko-monitor/0.3 (+ServerChan notifier)",
                "Content-Type": "application/json;charset=utf-8",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def send_available_targets(
        self,
        snapshots: list[NotificationSnapshot],
    ) -> dict[str, Any]:
        if not snapshots:
            return {}

        payload = {
            "title": self._build_title(snapshots),
            "desp": self._build_markdown(snapshots),
            "short": self._build_short_summary(snapshots),
            "channel": self.config.channel,
        }
        if self.config.noip is not None:
            payload["noip"] = self.config.noip

        push_content_logger.info(
            "ServerChan request payload:\n%s",
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        response = await self._client.post(
            f"https://sctapi.ftqq.com/{self.config.send_key}.send",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        push_result_logger.info(
            "ServerChan send response:\n%s",
            json.dumps(data, ensure_ascii=False, indent=2),
        )
        if data.get("code") != 0:
            raise RuntimeError(f"ServerChan send failed: {data}")
        logger.info("ServerChan notification enqueued: %s", data.get("data"))
        return data

    async def get_push_status(self, *, push_id: str, read_key: str) -> dict[str, Any]:
        response = await self._client.get(
            "https://sctapi.ftqq.com/push",
            params={"id": push_id, "readkey": read_key},
        )
        response.raise_for_status()
        data = response.json()
        push_result_logger.info(
            "ServerChan push-status response:\n%s",
            json.dumps(data, ensure_ascii=False, indent=2),
        )
        if data.get("code") != 0:
            raise RuntimeError(f"ServerChan push-status lookup failed: {data}")
        return data

    def _build_title(self, snapshots: list[NotificationSnapshot]) -> str:
        latest = max(snapshot.checked_at for snapshot in snapshots).astimezone()
        return f"{self.config.title_prefix} 空房提醒 {len(snapshots)}项 {latest:%H:%M}"

    def _build_short_summary(self, snapshots: list[NotificationSnapshot]) -> str:
        names = " / ".join(snapshot.hotel_name for snapshot in snapshots[:2])
        if len(snapshots) > 2:
            names = f"{names} 等{len(snapshots)}项"
        checked_at = max(snapshot.checked_at for snapshot in snapshots).astimezone()
        return f"{checked_at:%m-%d %H:%M} 有空房: {names}"[:64]

    def _build_markdown(self, snapshots: list[NotificationSnapshot]) -> str:
        ordered = sorted(
            snapshots,
            key=lambda item: (
                item.area_label,
                item.subarea_label,
                item.hotel_name,
                item.room_type_name,
                item.room_type_smoking,
            ),
        )
        latest = max(snapshot.checked_at for snapshot in ordered).astimezone()
        lines = [
            f"## 本次刷新发现 {len(ordered)} 个可订监控项",
            "",
            f"- 刷新时间：{latest:%Y-%m-%d %H:%M:%S %Z}",
            f"- 推送通道：{self.config.channel}",
            "",
        ]

        for index, snapshot in enumerate(ordered, start=1):
            lines.extend(
                [
                    f"### {index}. {snapshot.hotel_name}",
                    f"- 地区：{snapshot.area_label} / {snapshot.subarea_label}",
                    f"- 地址：{snapshot.address or '未获取到地址'}",
                    f"- 酒店代码：{snapshot.hotel_code}",
                    f"- 房型：{snapshot.room_type_name}",
                    f"- 房型吸烟：{snapshot.room_type_smoking or '未标注'}",
                    "- 状态：有空房",
                    f"- 可订房数：{snapshot.available_room_count}",
                    f"- 官网筛选：{SMOKING_LABELS.get(snapshot.smoking, snapshot.smoking)}",
                    f"- 查询条件：{snapshot.start_date.isoformat()} 入住，{snapshot.end_date.isoformat()} 退房，{snapshot.people} 人，{snapshot.rooms} 间",
                    f"- 价格：{self._format_price(snapshot.general_price, snapshot.member_price)}",
                    f"- 查询时间：{snapshot.checked_at.astimezone():%Y-%m-%d %H:%M:%S %Z}",
                ]
            )
            if snapshot.phone_number:
                lines.append(f"- 电话：{snapshot.phone_number}")
            lines.append("")

        return "\n".join(lines).strip()

    @staticmethod
    def _format_price(general_price: int | None, member_price: int | None) -> str:
        general_text = f"普通价 ¥{general_price}" if general_price is not None else "普通价 -"
        member_text = f"会员价 ¥{member_price}" if member_price is not None else "会员价 -"
        return f"{general_text} / {member_text}"


def load_serverchan_notifier(config_path: Path) -> ServerChanNotifier | None:
    if not config_path.exists():
        logger.info("ServerChan config file not found: %s", config_path)
        return None

    config = ServerChanConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    if not config.enabled:
        logger.info("ServerChan notifications are disabled in %s", config_path)
        return None

    logger.info("ServerChan notifier enabled from %s", config_path)
    return ServerChanNotifier(config)
