from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from src.adapters.audio import WhisperSttAdapter
from src.adapters.runtime.webhook_runtime import WebhookRoute, WebhookRuntime
from src.adapters.webhook_common import decode_webhook_audio_base64, with_webhook_kind
from src.shared_types.models import MessageEnvelope, MessageSource
from src.shared_types.protocol import MessageBus


@dataclass(slots=True)
class WebhookInputAdapter:
    runtime: WebhookRuntime
    bus: MessageBus
    stt: WhisperSttAdapter | None = None
    name: str = "webhook-input"

    _registered: bool = field(default=False, init=False, repr=False)
    _stop_event: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False
    )

    def register_routes(self) -> None:
        if self._registered:
            return
        self.runtime.add_route(
            WebhookRoute(
                path="/webhooks/inbound",
                methods=("POST",),
                endpoint=self._handle_inbound,
                require_bearer_auth=True,
                name="webhook-inbound",
            )
        )
        self._registered = True

    async def start(self) -> None:
        self.register_routes()
        self._stop_event.clear()
        await self._stop_event.wait()

    async def stop(self) -> None:
        self._stop_event.set()

    async def _handle_inbound(self, request: Request) -> JSONResponse:
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
        metadata = with_webhook_kind(
            payload.get("metadata"),
            kind="audio" if _clean_text(payload.get("kind")).lower() == "audio" else "text",
        )
        metadata.update(
            {
                "transport": "webhook",
                "request_path": str(request.url.path),
                "remote_addr": request.client.host if request.client else None,
                "user_agent": str(request.headers.get("user-agent", "")).strip(),
            }
        )

        if metadata["webhook_kind"] == "audio":
            stt = self.stt
            if stt is None:
                raise RuntimeError("STT adapter is not configured.")
            filename = _clean_text(payload.get("audio_filename")) or "audio.wav"
            content_type = _clean_text(payload.get("audio_content_type")) or "audio/wav"
            transcription = await stt.transcribe(
                audio_bytes=decode_webhook_audio_base64(payload.get("audio_base64")),
                filename=filename,
                mime_type=content_type,
                language=_clean_text(payload.get("language")) or None,
                prompt=_clean_text(payload.get("prompt")) or None,
            )
            metadata.update(
                {
                    "transcript_language": transcription.language,
                    "audio_filename": filename,
                    "audio_content_type": content_type,
                    "tts_voice": _clean_text(payload.get("voice")) or None,
                    "tts_response_format": _clean_text(payload.get("response_format")) or None,
                    "tts_speed": _optional_float(payload.get("speed")),
                }
            )
            content = transcription.text
        else:
            content = _clean_text(payload.get("content"))

        envelope = MessageEnvelope(
            source=MessageSource.WEBHOOK,
            content=content,
            channel_id=_clean_text(payload.get("channel_id")) or "webhook",
            author_id=_clean_text(payload.get("author_id")) or "webhook",
            message_id=_clean_text(payload.get("message_id")),
            target_user_id=_clean_text(payload.get("target_user_id")),
            metadata=metadata,
        )
        response_payload = await self._dispatch_and_wait(envelope)
        return JSONResponse(status_code=status.HTTP_200_OK, content=response_payload)

    async def _dispatch_and_wait(self, envelope: MessageEnvelope) -> dict[str, Any]:
        self.runtime.register_pending_response(envelope.id)
        try:
            await self.bus.publish(envelope)
            return await self.runtime.wait_for_response(envelope.id)
        except TimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=str(exc),
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        except Exception:
            self.runtime.discard_response(envelope.id)
            raise
def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _optional_float(value: Any) -> float | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None
