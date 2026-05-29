from __future__ import annotations

import asyncio
import io
import wave
from dataclasses import dataclass, field
from datetime import UTC, datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from agent.chat.service import ReactAgentService
from agent.life.service import LifeAgentService
from gateway.audio.stt import WhisperSttAdapter
from gateway.audio.tts import EdgeTtsAdapter
from gateway.webhook_common import ensure_outbound_webhook_metadata
from agent.memory import ConversationContractionService
from agent.orchestration.mood_engine import MoodEngine
from gateway.scheduler.service import AgentScheduler
from config.logging import get_logger
from shared_types.protocol import (
    EpisodicMemoryStore,
    MessageBus,
    OutputAdapter,
    StateStore,
)
from shared_types.helpers import maybe_float, maybe_str
from shared_types.models import AudioPayload, LifeNote, MessageEnvelope, MessageSource, OutboundMessage
from shared_types.types import Trigger, TriggerType

logger = get_logger("core.orchestrator")

AGENT_WINDOW = 12
MOOD_WINDOW = 4
COMPACT_IDLE_SECONDS = 60 * 30
COMPACT_TRIGGER_ID = "compact"
LIFE_NOTE_MAX_AGE_SECONDS = 60 * 60 * 24 * 3
MAX_PENDING_LIFE_NOTES = 3
MESSAGE_COALESCE_WINDOW_SECONDS = 0.5
COALESCE_ALLOWED_SOURCES = {
    MessageSource.DISCORD,
    MessageSource.TELEGRAM,
    MessageSource.CONSOLE,
}


@dataclass(slots=True)
class AgentOrchestrator:
    agent: ReactAgentService
    life_agent: LifeAgentService
    bus: MessageBus
    state_store: StateStore
    mood_engine: MoodEngine
    episodic_memory: EpisodicMemoryStore
    scheduler: AgentScheduler
    conversation_contraction: ConversationContractionService
    output: OutputAdapter
    stt: WhisperSttAdapter | None = None
    tts: EdgeTtsAdapter | None = None
    _pending_envelope: MessageEnvelope | None = field(
        default=None, init=False, repr=False)

    async def run(self) -> None:
        while True:
            envelope = await self._consume_envelope()
            try:
                if envelope.source == MessageSource.LIFE:
                    await self._handle_life(envelope)
                    continue

                if envelope.source == MessageSource.COMPACT:
                    await self._handle_compact(envelope)
                    continue

                if envelope.source == MessageSource.PROACTIVE:
                    await self._handle_proactive(envelope)
                    continue

                await self._handle_chat(envelope)

            except Exception as exc:
                await logger.error(
                    "orchestrator_failed",
                    "Envelope handling failed.",
                    context={
                        "envelope_id": envelope.id,
                        "source": str(envelope.source),
                        "author_id": envelope.author_id,
                        "channel_id": envelope.channel_id,
                        "message_id": envelope.message_id,
                    },
                    error=exc,
                )

    async def _consume_envelope(self) -> MessageEnvelope:
        envelope = self._pending_envelope
        if envelope is None:
            envelope = await self.bus.consume()
        else:
            self._pending_envelope = None
        if not _can_start_coalescing(envelope):
            return envelope

        merged_count = 1

        while True:
            try:
                candidate = await asyncio.wait_for(
                    self.bus.consume(),
                    timeout=MESSAGE_COALESCE_WINDOW_SECONDS,
                )
            except asyncio.TimeoutError:
                break

            if not _can_coalesce_pair(envelope, candidate):
                self._pending_envelope = candidate
                break

            envelope = _merge_envelopes(envelope, candidate)
            merged_count += 1

        if merged_count > 1:
            await logger.info(
                "messages_coalesced",
                "Coalesced adjacent inbound envelopes before processing.",
                context={
                    "source": str(envelope.source),
                    "channel_id": envelope.channel_id,
                    "author_id": envelope.author_id,
                    "voice_mode": envelope.voice_mode,
                    "merged_count": merged_count,
                },
            )
        return envelope

    async def _handle_life(self, envelope: MessageEnvelope) -> None:
        await self.state_store.prune_life_notes(
            max_age_seconds=LIFE_NOTE_MAX_AGE_SECONDS,
        )
        recent_life_notes = await self.state_store.get_life_notes()
        if len(recent_life_notes) >= MAX_PENDING_LIFE_NOTES:
            return

        history = await self.state_store.get_history()
        summary = _compacted_summary(history.all())

        life_profile = await self.state_store.get_life_profile()
        content = str(envelope.content or "").strip()
        episodic = await self.episodic_memory.recall(
            query=content or "recent internal continuity",
            limit=3,
        )
        if not summary and not life_profile and not episodic:
            return

        note = await self.life_agent.reflect(
            content=content,
            summary=summary,
            episodic=episodic,
            life_profile=life_profile,
            recent_notes=[note.content for note in recent_life_notes[-3:]],
        )
        if note:
            await self.state_store.append_life_note(
                note=_life_note(note),
            )

    async def _handle_compact(self, envelope: MessageEnvelope) -> None:
        del envelope
        await self.conversation_contraction.compact(
            state_store=self.state_store,
            episodic_memory=self.episodic_memory,
        )

    async def _handle_proactive(self, envelope: MessageEnvelope) -> None:
        interaction = await self.state_store.get_interaction_state()

        time_since_last = _format_time_since_last(
            interaction.last_user_message_at)
        now = datetime.now(UTC)
        today = now.date().isoformat()

        if interaction.sent_day != today:
            interaction.sent_day = today
            interaction.sent_today = 0

        if interaction.last_proactive_message_at and (
            not interaction.last_user_message_at
            # or interaction.last_user_message_at <= interaction.last_proactive_message_at
        ):
            await self.state_store.set_interaction_state(interaction)
            return

        mood = await self.state_store.get_mood()
        score = (
            float(mood.Trust)
            + float(mood.Attachment)
            + float(mood.Confidence)
        ) / 3.0
        # cap = 0 if score < 0.58 else 1 if score < 0.68 else 2 if score < 0.78 else 3
        cap = 100

        if cap <= 0 or interaction.sent_today >= cap:
            await self.state_store.set_interaction_state(interaction)
            return

        proactive_envelope = MessageEnvelope(
            source=MessageSource.PROACTIVE,
            content="",
            channel_id=interaction.route_channel_id,
            target_user_id=interaction.route_target_user_id,
            author_id=None,
            metadata={
                "route_source": interaction.route_source or "",
                "time_since_last": time_since_last,
            },
        )

        interaction.sent_today += 1
        await self.state_store.set_interaction_state(interaction)
        await self._handle_chat(proactive_envelope)

    async def _handle_chat(self, envelope: MessageEnvelope) -> None:
        content = await self._normalize_inbound_content(envelope)

        if not content and envelope.source != MessageSource.PROACTIVE:
            return

        mood = await self.state_store.get_mood()
        messages_for_agent = await self.state_store.get_agent_context(AGENT_WINDOW)

        next_mood = mood
        if envelope.source != MessageSource.PROACTIVE:
            messages_for_mood_analysis = await self.state_store.get_mood_context(MOOD_WINDOW)
            delta = await self.mood_engine.analyze(
                content=content,
                messages=messages_for_mood_analysis,
            )
            next_mood = self.mood_engine.apply(mood, delta)
            await self.state_store.set_mood(next_mood)

        facts = await self.episodic_memory.recall(
            query=content,
            limit=2,
        )
        reply_text = await self.agent.respond(
            content=content,
            messages=messages_for_agent,
            episodic=facts,
            mood=next_mood,
            envelope=envelope,
        )

        if envelope.source == MessageSource.PROACTIVE:
            await self.state_store.append_messages(
                [AIMessage(content=reply_text)]
            )
            await self._record_user_interaction(proactive=True)
        else:
            await self.state_store.append_messages(
                [
                    HumanMessage(content=content),
                    AIMessage(content=reply_text)
                ]
            )
            await self._record_user_interaction()
        await self._reschedule_compact_trigger()

        try:
            await self.conversation_contraction.maybe_compact(
                state_store=self.state_store,
                episodic_memory=self.episodic_memory,
            )
        except Exception as exc:
            await logger.error(
                "contraction_failed",
                "Compaction failed.",
                error=exc,
            )

        reply_text = (reply_text or "").strip()
        if not reply_text and envelope.source not in {MessageSource.WEBHOOK, MessageSource.PROACTIVE}:
            return None

        try:
            if envelope.source == MessageSource.PROACTIVE:
                interaction = await self.state_store.get_interaction_state()
                await self.output.send(
                    await self._build_outbound(
                        MessageEnvelope(
                            source=MessageSource(
                                interaction.route_source or ""),
                            content=envelope.content,
                            channel_id=envelope.channel_id,
                            author_id=envelope.author_id,
                            message_id=envelope.message_id,
                            target_user_id=envelope.target_user_id,
                            metadata={},
                        ),
                        reply_text
                    )
                )
            else:
                await self.output.send(await self._build_outbound(envelope, reply_text))
        except Exception as exc:
            await logger.error(
                "output_failed",
                "Outbound send failed.",
                context={
                    "envelope_id": envelope.id,
                    "source": str(envelope.source),
                    "channel_id": envelope.channel_id,
                    "target_user_id": envelope.target_user_id,
                },
                error=exc,
            )

    async def _reschedule_compact_trigger(self) -> None:
        trigger_id = COMPACT_TRIGGER_ID
        await self.scheduler.remove(trigger_id)
        await self.scheduler.push(
            Trigger(
                trigger_type=TriggerType.PRECISE,
                source=MessageSource.COMPACT,
                interval_seconds=COMPACT_IDLE_SECONDS,
                repeat=False,
                _trigger_id=trigger_id,
            )
        )

    async def _record_user_interaction(
        self,
        proactive: bool = False,
    ) -> None:
        state = await self.state_store.get_interaction_state()
        now = datetime.now(UTC).isoformat()
        if proactive:
            state.last_proactive_message_at = now
        else:
            state.last_user_message_at = now
        await self.state_store.set_interaction_state(state)

    async def _build_outbound(self, envelope: MessageEnvelope, content: str) -> OutboundMessage:
        outbound = OutboundMessage(
            source=envelope.source,
            content=content,
            channel_id=envelope.channel_id,
            target_user_id=envelope.target_user_id,
            voice_mode=bool(envelope.voice_mode),
            metadata=ensure_outbound_webhook_metadata(
                envelope.metadata,
                envelope_id=envelope.id,
            ),
            reply_to_message_id=envelope.message_id,
            mention_author=bool(
                envelope.channel_id and not envelope.target_user_id),
        )
        if not self._should_synthesize_audio_reply(envelope, outbound):
            return outbound

        tts = self.tts
        if tts is None:
            return outbound

        synthesis = await tts.synthesize(
            text=str(outbound.content or "").strip(),
            voice=maybe_str(outbound.metadata.get("tts_voice")),
            response_format=maybe_str(
                outbound.metadata.get("tts_response_format")),
            speed=maybe_float(outbound.metadata.get("tts_speed")),
        )
        outbound.audio = AudioPayload.from_bytes(
            synthesis.audio_bytes,
            mime_type=synthesis.content_type,
            filename=_default_audio_filename(synthesis.content_type),
        )
        return outbound

    async def _normalize_inbound_content(self, envelope: MessageEnvelope) -> str:
        content = str(envelope.content or "").strip()
        if content:
            return content

        audio_bytes = envelope.audio_bytes()
        if not audio_bytes:
            return ""

        stt = self.stt
        if stt is None:
            raise RuntimeError(
                "Inbound audio received without configured STT adapter.")

        await logger.info(
            "inbound_audio_stt_started",
            "Starting STT for inbound audio envelope.",
            context={
                "source": str(envelope.source),
                "channel_id": envelope.channel_id,
                "author_id": envelope.author_id,
                "mime_type": (envelope.audio.mime_type if envelope.audio else None),
                "size_bytes": len(audio_bytes),
            },
        )
        transcription = await stt.transcribe(
            audio_bytes=audio_bytes,
            filename=(
                envelope.audio.filename if envelope.audio else None) or "audio.wav",
            mime_type=(
                envelope.audio.mime_type if envelope.audio else None) or "audio/wav",
            language=maybe_str(envelope.metadata.get("language")),
            prompt=maybe_str(envelope.metadata.get("stt_prompt")),
        )

        await logger.info(
            "inbound_audio_stt_completed",
            "Completed STT for inbound audio envelope.",
            context={
                "source": str(envelope.source),
                "channel_id": envelope.channel_id,
                "author_id": envelope.author_id,
                "text_length": len(str(transcription.text or "").strip()),
                "language": transcription.language,
                "duration_seconds": transcription.duration_seconds,
            },
        )
        if envelope.audio is not None and envelope.audio.duration_seconds is None:
            envelope.audio.duration_seconds = transcription.duration_seconds
        if transcription.language and "transcript_language" not in envelope.metadata:
            envelope.metadata["transcript_language"] = transcription.language
        envelope.content = transcription.text
        return str(envelope.content or "").strip()

    @staticmethod
    def _should_synthesize_audio_reply(
        envelope: MessageEnvelope,
        outbound: OutboundMessage,
    ) -> bool:
        return bool(
            envelope.voice_mode
            and str(outbound.content or "").strip()
        )


def _compacted_summary(messages: list[BaseMessage]) -> str:
    first = messages[0] if messages else None
    if not first or not getattr(first, "additional_kwargs", {}).get("kayori_compacted"):
        return ""
    return str(first.content or "").strip()


def _format_time_since_last(last_user_message_at: str | None) -> str:
    if not last_user_message_at:
        return "a while"
    try:
        delta = datetime.now(
            UTC) - datetime.fromisoformat(last_user_message_at)
        hours = delta.total_seconds() / 3600
    except Exception:
        return "a while"
    if hours < 1:
        return "a few minutes ago"
    if hours < 2:
        return "about an hour ago"
    if hours < 6:
        return "a few hours ago"
    if hours < 24:
        return f"about {int(hours)} hours ago"
    return f"{int(hours / 24)} days ago"


def _life_note(content: str) -> LifeNote:
    return LifeNote(content=" ".join(str(content or "").strip().split()), timestamp=datetime.now(UTC).isoformat())



def _default_audio_filename(content_type: str) -> str:
    mime = str(content_type or "").strip().lower()
    for suffixes, filename in (
        (("/mpeg", "/mp3"), "reply.mp3"),
        (("/wav", "/wave"), "reply.wav"),
        (("/ogg",), "reply.ogg"),
    ):
        if mime.endswith(suffixes):
            return filename
    return "reply.audio"


def _can_start_coalescing(envelope: MessageEnvelope) -> bool:
    return bool(
        envelope.source in COALESCE_ALLOWED_SOURCES
        and (envelope.audio is not None or str(envelope.content or "").strip())
    )


def _can_coalesce_pair(left: MessageEnvelope, right: MessageEnvelope) -> bool:
    if not _can_start_coalescing(left) or not _can_start_coalescing(right):
        return False
    if (
        left.source,
        left.channel_id,
        left.author_id,
        left.target_user_id,
        bool(left.voice_mode),
        _route_tag(left),
        left.audio is not None,
    ) != (
        right.source,
        right.channel_id,
        right.author_id,
        right.target_user_id,
        bool(right.voice_mode),
        _route_tag(right),
        right.audio is not None,
    ):
        return False
    if left.audio is not None and right.audio is not None:
        return _can_merge_audio_payloads(left.audio, right.audio)
    return True


def _merge_envelopes(
    left: MessageEnvelope,
    right: MessageEnvelope,
) -> MessageEnvelope | None:
    if not _can_coalesce_pair(left, right):
        return None
    return MessageEnvelope(
        source=left.source,
        content=_merge_text_content(left.content, right.content),
        channel_id=left.channel_id,
        author_id=left.author_id,
        message_id=right.message_id or left.message_id,
        target_user_id=left.target_user_id,
        audio=_merge_audio_payload(left.audio, right.audio),
        voice_mode=left.voice_mode,
        metadata=dict(left.metadata or {}),
        id=left.id,
    )


def _merge_text_content(left: str | None, right: str | None) -> str | None:
    return " ".join(part for part in (str(left or "").strip(), str(right or "").strip()) if part) or None


def _route_tag(envelope: MessageEnvelope) -> str:
    return str((envelope.metadata or {}).get("transport") or "").strip().lower()


def _can_merge_audio_payloads(
    left: AudioPayload,
    right: AudioPayload,
) -> bool:
    left_mime = str(left.mime_type or "").strip().lower()
    return bool(left_mime and left_mime == str(right.mime_type or "").strip().lower() and "wav" in left_mime)


def _merge_audio_payload(
    left: AudioPayload | None,
    right: AudioPayload | None,
) -> AudioPayload | None:
    if left is None or right is None:
        return left or right
    if not _can_merge_audio_payloads(left, right):
        return None

    left_bytes = left.bytes()
    right_bytes = right.bytes()
    if not left_bytes or not right_bytes:
        return None

    merged_bytes = _merge_wav_audio(left_bytes, right_bytes)
    if not merged_bytes:
        return None

    return AudioPayload.from_bytes(
        merged_bytes,
        mime_type=left.mime_type,
        filename=left.filename or right.filename or "merged.wav",
        duration_seconds=(
            round(float(left.duration_seconds or 0.0) +
                  float(right.duration_seconds or 0.0), 3)
            if left.duration_seconds is not None or right.duration_seconds is not None
            else None
        ),
    )


def _merge_wav_audio(left_bytes: bytes, right_bytes: bytes) -> bytes | None:
    with wave.open(io.BytesIO(left_bytes), "rb") as left_wav:
        with wave.open(io.BytesIO(right_bytes), "rb") as right_wav:
            params = (
                left_wav.getnchannels(),
                left_wav.getsampwidth(),
                left_wav.getframerate(),
            )
            if params != (
                right_wav.getnchannels(),
                right_wav.getsampwidth(),
                right_wav.getframerate(),
            ):
                return None
            frames = left_wav.readframes(left_wav.getnframes(
            )) + right_wav.readframes(right_wav.getnframes())

    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(params[0])
        wav_file.setsampwidth(params[1])
        wav_file.setframerate(params[2])
        wav_file.writeframes(frames)
    return output.getvalue()
