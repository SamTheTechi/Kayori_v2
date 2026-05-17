from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

from src.adapters.runtime.webhook_runtime import WebhookRuntime
from src.adapters.webhook_common import (
    webhook_envelope_id,
)
from src.logger import get_logger
from src.shared_types.models import OutboundMessage, MessageSource
from src.shared_types.protocol import OutputAdapter

logger = get_logger("output.webhook")


@dataclass(slots=True)
class WebhookOutputAdapter(OutputAdapter):
    targets: list[str]
    runtime: WebhookRuntime | None = None
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
                "voice_mode": bool(message.voice_mode),
            }
            if message.audio is not None:
                payload["audio_base64"] = message.audio.base64_data
                payload["audio_content_type"] = message.audio.mime_type or "audio/mpeg"
                payload["audio_filename"] = message.audio.filename
                payload["audio_duration_seconds"] = message.audio.duration_seconds
            runtime.resolve_response(response_id, payload)

        has_text = bool(str(message.content or "").strip())
        has_audio = message.audio is not None
        if (not has_text and not has_audio) or not self.targets:
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
            *(client.post(url, json=payload, headers=headers)
              for url in self.targets),
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
                    context={"target_url": url,
                             "status_code": result.status_code},
                )
