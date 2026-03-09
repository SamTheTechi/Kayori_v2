from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TtsSynthesisResult:
    audio_bytes: bytes
    content_type: str
    voice: str


@dataclass(slots=True)
class EdgeTtsAdapter:
    api_key: str = "123"
    base_url: str = "http://localhost:5050/v1"
    voice: str = "en-US-AvaNeural"
    response_format: str = "mp3"
    speed: float = 1.0
    timeout_seconds: float = 60.0
    name: str = "edge-tts"

    async def synthesize(
        self,
        *,
        text: str,
        voice: str | None = None,
        response_format: str | None = None,
        speed: float | None = None,
    ) -> TtsSynthesisResult:
        import httpx

        content = str(text or "").strip()
        if not content:
            raise ValueError("text must be non-empty")

        chosen_voice = str(voice or self.voice).strip() or self.voice
        chosen_format = str(
            response_format or self.response_format).strip() or self.response_format
        chosen_speed = float(self.speed if speed is None else speed)

        headers = {
            "authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }
        payload = {
            "input": content,
            "voice": chosen_voice,
            "response_format": chosen_format,
            "speed": chosen_speed,
        }

        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
        ) as client:
            response = await client.post(
                "/audio/speech",
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            raise RuntimeError(_error_message("edge-tts", response))

        audio_bytes = response.content
        if not audio_bytes:
            raise RuntimeError("edge-tts returned empty audio")

        return TtsSynthesisResult(
            audio_bytes=audio_bytes,
            content_type=str(response.headers.get(
                "content-type", "audio/mpeg")),
            voice=chosen_voice,
        )


def _error_message(prefix: str, response: Any) -> str:
    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message", "")).strip()
            if message:
                return f"[{prefix}] {response.status_code}: {message}"
        message = str(payload.get("message", "")).strip()
        if message:
            return f"[{prefix}] {response.status_code}: {message}"

    return f"[{prefix}] {response.status_code}: request failed"
