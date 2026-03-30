from __future__ import annotations

import base64
from typing import Any

WEBHOOK_ENVELOPE_ID = "webhook_envelope_id"
WEBHOOK_KIND = "webhook_kind"


def webhook_envelope_id(metadata: dict[str, Any] | None) -> str:
    return str((metadata or {}).get(WEBHOOK_ENVELOPE_ID) or "").strip()


def webhook_kind(metadata: dict[str, Any] | None) -> str:
    return str((metadata or {}).get(WEBHOOK_KIND) or "text").strip().lower()


def ensure_outbound_webhook_metadata(
    metadata: dict[str, Any] | None,
    *,
    envelope_id: str,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    if envelope_id:
        payload[WEBHOOK_ENVELOPE_ID] = envelope_id
    return payload


def with_webhook_kind(
    metadata: dict[str, Any] | None,
    *,
    kind: str,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload[WEBHOOK_KIND] = str(kind or "text").strip().lower()
    return payload


def decode_webhook_audio_base64(value: Any) -> bytes:
    return base64.b64decode(str(value or ""))
