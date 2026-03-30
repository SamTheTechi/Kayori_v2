from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.adapters.audio import EdgeTtsAdapter
from src.adapters.runtime.webhook_runtime import WebhookRuntime
from src.adapters.webhook_common import (
    webhook_envelope_id,
    webhook_kind,
)
from src.logger import get_logger
from src.shared_types.models import OutboundMessage, MessageSource

logger = get_logger("output.webhook")


@dataclass(slots=True)
class WebhookOutputAdapter:
    targets: list[str]
    runtime: WebhookRuntime | None = None
    tts: EdgeTtsAdapter | None = None
    bearer_token: str | None = None
    timeout_seconds: float = 10.0
    name: str = "webhook"
    route_source: MessageSource = MessageSource.WEBHOOK

    _client: httpx.AsyncClient | None = field(
        default=None, init=False, repr=False)

    async def start(self) -> None:
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(timeout=self.timeout_seconds)

    async def stop(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            await client.aclose()

    async def send(self, message: OutboundMessage) -> None:
        runtime = self.runtime
        metadata = dict(message.metadata or {})
        response_id = webhook_envelope_id(metadata)
        if runtime is not None and response_id:
            payload = {
                "reply": str(message.content or "").strip(),
                "envelope_id": response_id,
            }
            if payload["reply"] and webhook_kind(metadata) == "audio":
                tts = self.tts
                if tts is None:
                    runtime.fail_response(
                        response_id,
                        "Webhook audio response requested without TTS adapter.",
                    )
                    raise RuntimeError(
                        "Webhook audio response requested without TTS adapter."
                    )
                synthesis = await tts.synthesize(
                    text=payload["reply"],
                    voice=_optional_text(metadata.get("tts_voice")),
                    response_format=_optional_text(metadata.get("tts_response_format")),
                    speed=_optional_float(metadata.get("tts_speed")),
                )
                payload["audio_base64"] = base64.b64encode(
                    synthesis.audio_bytes
                ).decode("ascii")
                payload["audio_content_type"] = synthesis.content_type
            runtime.resolve_response(response_id, payload)

        if not str(message.content or "").strip() or not self.targets:
            return

        await self.start()
        client = self._client
        if client is None:
            raise RuntimeError("Webhook output HTTP client is not available.")

        headers = {"content-type": "application/json"}
        token = str(self.bearer_token or "").strip()
        if token:
            headers["authorization"] = f"Bearer {token}"

        payload = message.to_dict()
        results = await asyncio.gather(
            *(client.post(url, json=payload, headers=headers) for url in self.targets),
            return_exceptions=True,
        )
        for url, result in zip(self.targets, results, strict=False):
            if isinstance(result, Exception):
                await logger.error(
                    "webhook_send_failed",
                    "Webhook send failed.",
                    context={"target_url": url},
                    error=result,
                )
                continue
            if result.status_code >= 400:
                await logger.warning(
                    "webhook_target_error",
                    "Webhook target returned an error.",
                    context={"target_url": url, "status_code": result.status_code},
                )


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
