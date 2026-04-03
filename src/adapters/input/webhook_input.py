from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from src.adapters.audio import WhisperSttAdapter
from src.adapters.runtime.webhook_runtime import WebhookRoute, WebhookRuntime
from src.adapters.webhook_common import with_webhook_kind
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
                path="/webhooks/text",
                methods=("POST",),
                endpoint=self._handle_text,
                require_bearer_auth=True,
                name="webhook-text",
            )
        )
        if self.stt is not None:
            self.runtime.add_route(
                WebhookRoute(
                    path="/webhooks/audio",
                    methods=("POST",),
                    endpoint=self._handle_audio,
                    require_bearer_auth=True,
                    name="webhook-audio",
                )
            )
        self._registered = True

    async def start(self) -> None:
        self.register_routes()
        self._stop_event.clear()
        await self._stop_event.wait()

    async def stop(self) -> None:
        self._stop_event.set()

    async def _handle_text(self, request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload.",
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON payload must be an object.",
            )

        content = _clean_text(payload.get("content"))
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Field 'content' must be non-empty.",
            )

        metadata = with_webhook_kind(
            payload.get("metadata"),
            kind="text",
        )
        metadata.update(
            {
                "transport": "webhook",
                "request_path": str(request.url.path),
                "remote_addr": request.client.host if request.client else None,
                "user_agent": str(request.headers.get("user-agent", "")).strip(),
            }
        )

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

    async def _handle_audio(self, request: Request) -> JSONResponse:
        stt = self.stt
        if stt is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="STT adapter is not configured.",
            )

        form = await request.form()
        upload = _extract_upload(form.get("audio") or form.get("file"))
        if upload is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing audio upload.",
            )

        audio_bytes = await upload.read()
        transcription = await stt.transcribe(
            audio_bytes=audio_bytes,
            filename=upload.filename or "audio.wav",
            mime_type=upload.content_type or "audio/wav",
            language=_clean_text(form.get("language")) or None,
            prompt=_clean_text(form.get("prompt")) or None,
        )

        metadata = with_webhook_kind(
            None,
            kind="audio",
        )
        metadata.update(
            {
                "transport": "webhook",
                "request_path": str(request.url.path),
                "remote_addr": request.client.host if request.client else None,
                "user_agent": str(request.headers.get("user-agent", "")).strip(),
                "transcript_language": transcription.language,
                "audio_filename": upload.filename,
                "audio_content_type": upload.content_type,
                "tts_voice": _clean_text(form.get("voice")) or None,
                "tts_response_format": _clean_text(form.get("response_format")) or None,
                "tts_speed": _optional_float(form.get("speed")),
            }
        )

        envelope = MessageEnvelope(
            source=MessageSource.WEBHOOK,
            content=transcription.text,
            channel_id=_clean_text(form.get("channel_id")) or "webhook-audio",
            author_id=_clean_text(form.get("author_id")) or "webhook-audio",
            message_id=_clean_text(form.get("message_id")),
            target_user_id=_clean_text(form.get("target_user_id")),
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


def _extract_upload(value: Any) -> Any | None:
    if value is None:
        return None
    if not hasattr(value, "read"):
        return None
    if not hasattr(value, "filename"):
        return None
    return value


def _optional_float(value: Any) -> float | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return float(text)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Field 'speed' must be numeric.",
        ) from exc
