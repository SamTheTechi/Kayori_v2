from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from typing import Any

import httpx

from adapters.audio import EdgeTtsAdapter
from adapters.runtime.webhook_runtime import WebhookRuntime
from shared_types.models import OutboundMessage


@dataclass(slots=True)
class WebhookOutputAdapter:
    targets: list[str]
    runtime: WebhookRuntime | None = None
    tts: EdgeTtsAdapter | None = None
    bearer_token: str | None = None
    timeout_seconds: float = 10.0
    name: str = "webhook"

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
        await self._capture_runtime_response(message)

        if not self.targets:
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
        for url, result in zip(self.targets, results):
            if isinstance(result, Exception):
                print(f"[webhook-output] send failed for {url}: {result}")
                continue
            if result.status_code >= 400:
                print(
                    f"[webhook-output] target {url} returned status {result.status_code}"
                )

    async def _capture_runtime_response(self, message: OutboundMessage) -> None:
        runtime = self.runtime
        metadata = dict(message.metadata or {})
        correlation_id = str(metadata.get("webhook_correlation_id") or "").strip()
        if runtime is None or not correlation_id:
            return

        try:
            payload = await self._build_runtime_payload(message=message, metadata=metadata)
        except Exception as exc:
            runtime.fail_response(correlation_id, str(exc))
            raise

        runtime.resolve_response(correlation_id, payload)

    async def _build_runtime_payload(
        self,
        *,
        message: OutboundMessage,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "reply": str(message.content or "").strip(),
            "envelope_id": str(metadata.get("webhook_envelope_id") or ""),
        }
        if not payload["reply"]:
            raise RuntimeError("Agent returned empty reply.")
        response_kind = str(metadata.get("webhook_response_kind") or "text").strip().lower()
        if response_kind != "audio":
            return payload

        tts = self.tts
        if tts is None:
            raise RuntimeError("Webhook audio response requested without TTS adapter.")

        synthesis = await tts.synthesize(
            text=payload["reply"],
            voice=_optional_text(metadata.get("tts_voice")),
            response_format=_optional_text(metadata.get("tts_response_format")),
            speed=_optional_float(metadata.get("tts_speed")),
        )
        payload["audio_base64"] = base64.b64encode(synthesis.audio_bytes).decode("ascii")
        payload["audio_content_type"] = synthesis.content_type
        return payload


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
