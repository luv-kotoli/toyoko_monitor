from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .bark import BarkConfig, BarkLevel, BarkNotifier, DEFAULT_BARK_BASE_URL, DEFAULT_BARK_LEVEL
from .database import DEFAULT_CHECK_INTERVAL_MINUTES
from .serverchan import NotificationSnapshot, ServerChanConfig, ServerChanNotifier


logger = logging.getLogger(__name__)

DEFAULT_BARK_DEVICE_KEY = "PZDUg7ExYcsRsrUc6dceUD"
NotificationProvider = Literal["serverchan", "bark"]
NotificationConfigSource = Literal["notification", "legacy_serverchan", "default"]
MIN_CHECK_INTERVAL_MINUTES = 1
MAX_CHECK_INTERVAL_MINUTES = 1440


class ServerChanSettings(BaseModel):
    send_key: str = ""
    channel: str = "9"
    noip: int | None = 1
    title_prefix: str = "Toyoko Monitor"

    @model_validator(mode="after")
    def normalize(self) -> "ServerChanSettings":
        self.send_key = self.send_key.strip()
        self.channel = (self.channel or "9").strip() or "9"
        self.title_prefix = (self.title_prefix or "Toyoko Monitor").strip() or "Toyoko Monitor"
        return self


class BarkSettings(BaseModel):
    base_url: str = DEFAULT_BARK_BASE_URL
    device_key: str = DEFAULT_BARK_DEVICE_KEY
    title_prefix: str = "Toyoko Monitor"
    url: str = ""
    group: str = ""
    icon: str = ""
    sound: str = ""
    call: bool = False
    ciphertext: str = ""
    level: BarkLevel | None = DEFAULT_BARK_LEVEL

    @model_validator(mode="after")
    def normalize(self) -> "BarkSettings":
        self.base_url = (self.base_url or DEFAULT_BARK_BASE_URL).strip().rstrip("/") or DEFAULT_BARK_BASE_URL
        self.device_key = self.device_key.strip()
        self.title_prefix = (self.title_prefix or "Toyoko Monitor").strip() or "Toyoko Monitor"
        self.url = self.url.strip()
        self.group = self.group.strip()
        self.icon = self.icon.strip()
        self.sound = self.sound.strip()
        self.ciphertext = self.ciphertext.strip()
        self.level = self.level or DEFAULT_BARK_LEVEL
        return self


class MonitorSettings(BaseModel):
    check_interval_minutes: int = Field(
        default=DEFAULT_CHECK_INTERVAL_MINUTES,
        ge=MIN_CHECK_INTERVAL_MINUTES,
        le=MAX_CHECK_INTERVAL_MINUTES,
    )


class NotificationSettings(BaseModel):
    enabled: bool = True
    provider: NotificationProvider = "serverchan"
    serverchan: ServerChanSettings = Field(default_factory=ServerChanSettings)
    bark: BarkSettings = Field(default_factory=BarkSettings)
    monitor: MonitorSettings = Field(default_factory=MonitorSettings)

    @model_validator(mode="after")
    def validate_selected_provider(self) -> "NotificationSettings":
        if not self.enabled:
            return self
        if self.provider == "serverchan" and not self.serverchan.send_key:
            raise ValueError("已启用 Server酱 推送时，SendKey 不能为空。")
        if self.provider == "bark" and not self.bark.device_key:
            raise ValueError("已启用 Bark 推送时，Bark Key 不能为空。")
        return self


class NotificationSettingsResponse(BaseModel):
    config: NotificationSettings
    config_path: str
    source: NotificationConfigSource
    legacy_source_path: str | None = None


class MonitorSettingsResponse(BaseModel):
    monitor: MonitorSettings
    config_path: str
    source: NotificationConfigSource
    legacy_source_path: str | None = None


class NotificationTestRequest(BaseModel):
    config: NotificationSettings
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=120)
    body: str = Field(min_length=1, max_length=4000)


class NotificationTestResponse(BaseModel):
    provider: NotificationProvider
    detail: str
    response: dict[str, Any] = Field(default_factory=dict)


class NotificationService:
    def __init__(
        self,
        *,
        config_path: Path,
        legacy_serverchan_path: Path | None = None,
    ) -> None:
        self.config_path = config_path
        self.legacy_serverchan_path = legacy_serverchan_path
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def get_settings_response(self) -> NotificationSettingsResponse:
        config, source = self._load_config_with_source()
        return NotificationSettingsResponse(
            config=config,
            config_path=str(self.config_path),
            source=source,
            legacy_source_path=str(self.legacy_serverchan_path) if self.legacy_serverchan_path else None,
        )

    def get_monitor_settings_response(self) -> MonitorSettingsResponse:
        config, source = self._load_config_with_source()
        return MonitorSettingsResponse(
            monitor=config.monitor,
            config_path=str(self.config_path),
            source=source,
            legacy_source_path=str(self.legacy_serverchan_path) if self.legacy_serverchan_path else None,
        )

    def load_settings(self) -> NotificationSettings:
        config, _ = self._load_config_with_source()
        return config

    def save_settings(self, config: NotificationSettings) -> NotificationSettingsResponse:
        self._save_config(config)
        return NotificationSettingsResponse(
            config=config,
            config_path=str(self.config_path),
            source="notification",
            legacy_source_path=str(self.legacy_serverchan_path) if self.legacy_serverchan_path else None,
        )

    def save_monitor_settings(self, monitor: MonitorSettings) -> MonitorSettingsResponse:
        current_config = self.load_settings()
        next_config = NotificationSettings.model_validate(
            {
                **current_config.model_dump(mode="python"),
                "monitor": monitor.model_dump(mode="python"),
            }
        )
        self._save_config(next_config)
        return MonitorSettingsResponse(
            monitor=next_config.monitor,
            config_path=str(self.config_path),
            source="notification",
            legacy_source_path=str(self.legacy_serverchan_path) if self.legacy_serverchan_path else None,
        )

    async def send_available_targets(self, snapshots: list[NotificationSnapshot]) -> dict[str, Any]:
        if not snapshots:
            return {}

        config, _ = self._load_config_with_source()
        if not config.enabled:
            logger.info("Notification skipped: push disabled")
            return {}

        notifier = self._build_notifier(config)
        try:
            return await notifier.send_available_targets(snapshots)
        finally:
            await notifier.close()

    async def send_test_notification(self, request: NotificationTestRequest) -> NotificationTestResponse:
        effective_config = NotificationSettings.model_validate(
            {
                **request.config.model_dump(mode="python"),
                "enabled": True,
            }
        )
        notifier = self._build_notifier(effective_config)
        try:
            response = await notifier.send_test_message(
                title=request.title,
                subtitle=request.subtitle or None,
                body=request.body,
            )
        finally:
            await notifier.close()

        return NotificationTestResponse(
            provider=effective_config.provider,
            detail="测试推送已发送。",
            response=response,
        )

    def _load_config_with_source(self) -> tuple[NotificationSettings, NotificationConfigSource]:
        if self.config_path.exists():
            try:
                config = NotificationSettings.model_validate_json(self.config_path.read_text(encoding="utf-8"))
                return config, "notification"
            except Exception:
                logger.exception("Failed to parse notification config: %s", self.config_path)

        if self.legacy_serverchan_path and self.legacy_serverchan_path.exists():
            try:
                legacy = ServerChanConfig.model_validate_json(self.legacy_serverchan_path.read_text(encoding="utf-8"))
                return (
                    NotificationSettings(
                        enabled=legacy.enabled,
                        provider="serverchan",
                        serverchan=ServerChanSettings(
                            send_key=legacy.send_key,
                            channel=legacy.channel,
                            noip=legacy.noip,
                            title_prefix=legacy.title_prefix,
                        ),
                    ),
                    "legacy_serverchan",
                )
            except Exception:
                logger.exception("Failed to parse legacy ServerChan config: %s", self.legacy_serverchan_path)

        return NotificationSettings(provider="bark"), "default"

    def _save_config(self, config: NotificationSettings) -> None:
        self.config_path.write_text(
            json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Notification config saved: %s", self.config_path)

    def _build_notifier(self, config: NotificationSettings):
        if not config.enabled:
            raise ValueError("当前推送已关闭，无法发送测试消息。")

        if config.provider == "serverchan":
            return ServerChanNotifier(
                ServerChanConfig(
                    enabled=True,
                    send_key=config.serverchan.send_key,
                    channel=config.serverchan.channel,
                    noip=config.serverchan.noip,
                    title_prefix=config.serverchan.title_prefix,
                )
            )

        return BarkNotifier(
            BarkConfig(
                base_url=config.bark.base_url,
                device_key=config.bark.device_key,
                title_prefix=config.bark.title_prefix,
                url=config.bark.url or None,
                group=config.bark.group or None,
                icon=config.bark.icon or None,
                sound=config.bark.sound or None,
                call=config.bark.call,
                ciphertext=config.bark.ciphertext or None,
                level=config.bark.level,
            )
        )
