from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SttTranscription:
    text: str
    language: str | None = None
    duration_seconds: float | None = None
    raw_response: dict[str, Any] | None = None


@dataclass(slots=True)
class WhisperSttAdapter:
    api_key: str
    model: str = "whisper-large-v3-turbo"
    base_url: str = "https://api.groq.com/openai/v1"
    timeout_seconds: float = 60.0
    name: str = "groq-whisper-stt"

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        mime_type: str = "audio/wav",
        language: str | None = None,
        prompt: str | None = None,
        temperature: float = 0.0,
    ) -> SttTranscription:
        import httpx

        if not audio_bytes:
            raise ValueError("audio_bytes must be non-empty")

        headers = {
            "authorization": f"Bearer {self.api_key}",
        }
        data: dict[str, Any] = {
            "model": self.model,
            "temperature": str(float(temperature)),
        }
        if language:
            data["language"] = str(language).strip()
        if prompt:
            data["prompt"] = str(prompt).strip()

        files = {
            "file": (filename, audio_bytes, mime_type),
        }

        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
        ) as client:
            response = await client.post(
                "/audio/transcriptions",
                headers=headers,
                data=data,
                files=files,
            )

        if response.status_code >= 400:
            raise RuntimeError(_error_message("groq-stt", response))

        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError("groq-stt returned unreadable JSON") from exc

        text = str(payload.get("text", "")).strip()
        if not text:
            raise RuntimeError("groq-stt returned empty transcription")

        return SttTranscription(
            text=text,
            language=_optional_str(payload.get("language")),
            duration_seconds=_optional_float(
                payload.get("duration", payload.get(
                    "x_groq", {}).get("duration"))
            ),
            raw_response=payload,
        )


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


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

    return f"[{prefix}] {response.status_code}: request failed"
