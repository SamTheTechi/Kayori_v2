from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from config.exceptions import MissingRequiredConfig

PrimaryChatApp = Literal["discord", "telegram"]
OutputSinkMode = Literal["direct", "multi"]


@dataclass(slots=True)
class KayoriConfig:
    # ── App mode ──
    primary_chat_app: PrimaryChatApp = "discord"
    output_sink_mode: OutputSinkMode = "direct"

    # ── Platform credentials ──
    discord_token: str = ""
    discord_user_id: str = ""
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # ── LLM ──
    groq_api_key: str = ""
    groq_chat_model: str = "openai/gpt-oss-120b"
    groq_life_model: str = "openai/gpt-oss-20b"

    # ── Infrastructure ──
    redis_url: str = "redis://localhost:6379"
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080
    webhook_bearer_token: str = "123"

    # ── Audio ──
    tts_base_url: str = "http://localhost:5050/v1"
    tts_api_key: str = "123"

    # ── Webhook delivery ──
    webhook_output_urls: list[str] = field(default_factory=list)
    webhook_output_token: str = ""

    # ── Life profile ──
    life_profile_file: str = ""

    # ── Derived / computed after load ──
    webhook_output_targets: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> KayoriConfig:
        raw = cls._read_env()

        primary = cls._resolve_primary(raw)

        return cls(
            primary_chat_app=primary,
            output_sink_mode=cls._resolve_sink_mode(raw),

            discord_token=raw.get("DISCORD_BOT_TOKEN", ""),
            discord_user_id=raw.get("DISCORD_USER_ID", ""),
            telegram_token=raw.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=raw.get("TELEGRAM_CHAT_ID", ""),

            groq_api_key=raw.get("API_KEY", ""),
            groq_chat_model=raw.get("GROQ_CHAT_MODEL", "openai/gpt-oss-120b"),
            groq_life_model=raw.get("GROQ_LIFE_MODEL", "openai/gpt-oss-20b"),

            redis_url=raw.get("REDIS_URL", "redis://localhost:6379"),
            webhook_host=raw.get("WEBHOOK_SERVER_HOST", "0.0.0.0"),
            webhook_port=int(raw.get("WEBHOOK_SERVER_PORT", "8080")),
            webhook_bearer_token=raw.get("WEBHOOK_BEARER_TOKEN", "123"),

            tts_base_url=raw.get("EDGE_TTS_BASE_URL", "http://localhost:5050/v1"),
            tts_api_key=raw.get("EDGE_TTS_API_KEY", "123"),

            webhook_output_urls=[
                item.strip()
                for item in raw.get("WEBHOOK_OUTPUT_URLS", "").split(",")
                if item.strip()
            ],
            webhook_output_token=raw.get("WEBHOOK_OUTPUT_BEARER_TOKEN", ""),

            life_profile_file=raw.get("LIFE_PROFILE_FILE", ""),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.primary_chat_app == "discord" and not self.discord_token:
            errors.append("DISCORD_BOT_TOKEN is required when PRIMARY_CHAT_APP=discord")
        if self.primary_chat_app == "telegram" and not self.telegram_token:
            errors.append("TELEGRAM_BOT_TOKEN is required when PRIMARY_CHAT_APP=telegram")
        if not self.groq_api_key:
            errors.append("API_KEY (Groq) is required")
        return errors

    def raise_if_invalid(self) -> None:
        errors = self.validate()
        if errors:
            raise MissingRequiredConfig("; ".join(errors))

    @staticmethod
    def _read_env() -> dict[str, str]:
        return {k: (v or "").strip() for k, v in os.environ.items()}

    @staticmethod
    def _resolve_primary(raw: dict[str, str]) -> PrimaryChatApp:
        value = raw.get("PRIMARY_CHAT_APP", "discord").lower()
        if value not in ("discord", "telegram"):
            raise MissingRequiredConfig(
                f"PRIMARY_CHAT_APP must be 'discord' or 'telegram', got {value!r}"
            )
        return value  # type: ignore[return-value]

    @staticmethod
    def _resolve_sink_mode(raw: dict[str, str]) -> OutputSinkMode:
        value = raw.get("OUTPUT_SINK_MODE", "direct").lower()
        if value not in ("direct", "multi"):
            raise MissingRequiredConfig(
                f"OUTPUT_SINK_MODE must be 'direct' or 'multi', got {value!r}"
            )
        return value  # type: ignore[return-value]
