from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from adapters.audio import WhisperSttAdapter
from adapters.runtime.webhook_runtime import WebhookRoute, WebhookRuntime
from shared_types.models import MessageEnvelope, MessageSource
from shared_types.protocol import MessageBus


@dataclass(slots=True)
class WebhookInputAdapter:
    runtime: WebhookRuntime
    bus: MessageBus
    stt: WhisperSttAdapter | None = None
    name: str = "webhook-input"

    _registered: bool = field(default=False, init=False, repr=False)
    _stop_event: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False)

    def register_routes(self) -> None:
        if self._registered:
            return
        self.runtime.add_route(
            WebhookRoute(
                path="/webhooks/text",
                methods=("POST",),
                endpoint=self._handle_inbound,
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

    async def _handle_inbound(self, request: Request) -> JSONResponse:
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

        content = str(payload.get("content", "")).strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Field 'content' must be non-empty.",
            )

        metadata = dict(payload.get("metadata") or {})
        metadata.update(
            {
                "transport": "webhook",
                "webhook_response_kind": "text",
                "request_path": str(request.url.path),
                "remote_addr": request.client.host if request.client else None,
                "user_agent": str(request.headers.get("user-agent", "")).strip(),
            }
        )
        correlation_id = self.runtime.create_pending_response()
        metadata["webhook_correlation_id"] = correlation_id

        envelope = MessageEnvelope(
            source=MessageSource.WEBHOOK,
            content=content,
            channel_id=_clean_text(payload.get("channel_id")) or "webhook",
            author_id=_clean_text(payload.get("author_id")) or "webhook",
            message_id=_clean_text(payload.get("message_id")),
            target_user_id=_clean_text(payload.get("target_user_id")),
            metadata=metadata,
        )
        envelope.metadata["webhook_envelope_id"] = envelope.id
        try:
            await self.bus.publish(envelope)
            response_payload = await self.runtime.wait_for_response(correlation_id)
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
            self.runtime.discard_response(correlation_id)
            raise

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

        envelope = MessageEnvelope(
            source=MessageSource.WEBHOOK,
            content=transcription.text,
            channel_id=_clean_text(form.get("channel_id")) or "webhook-audio",
            author_id=_clean_text(form.get("author_id")) or "webhook-audio",
            message_id=_clean_text(form.get("message_id")),
            target_user_id=_clean_text(form.get("target_user_id")),
            metadata={
                "transport": "webhook-audio",
                "webhook_response_kind": "audio",
                "request_path": str(request.url.path),
                "remote_addr": request.client.host if request.client else None,
                "user_agent": str(request.headers.get("user-agent", "")).strip(),
                "transcript_language": transcription.language,
                "audio_filename": upload.filename,
                "audio_content_type": upload.content_type,
                "tts_voice": _clean_text(form.get("voice")) or None,
                "tts_response_format": _clean_text(form.get("response_format")) or None,
                "tts_speed": _optional_float(form.get("speed")),
            },
        )
        correlation_id = self.runtime.create_pending_response()
        envelope.metadata["webhook_correlation_id"] = correlation_id
        envelope.metadata["webhook_envelope_id"] = envelope.id
        try:
            await self.bus.publish(envelope)
            response_payload = await self.runtime.wait_for_response(correlation_id)
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
            self.runtime.discard_response(correlation_id)
            raise

        return JSONResponse(status_code=status.HTTP_200_OK, content=response_payload)


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
