from __future__ import annotations

from dataclasses import dataclass
import os
from datetime import UTC, datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.agent.chat.service import ReactAgentService
from src.agent.life.service import LifeAgentService
from src.adapters.webhook_common import ensure_outbound_webhook_metadata
from src.core.conversation_contraction import ConversationContractionService
from src.core.mood_engine import MoodEngine
from src.core.scheduler import AgentScheduler
from src.logger import get_logger
from src.shared_types.protocol import (
    EpisodicMemoryStore,
    MessageBus,
    OutputAdapter,
    StateStore,
)
from src.shared_types.models import LifeNote, MessageEnvelope, MessageSource, OutboundMessage
from src.shared_types.types import Trigger, TriggerType
from src.shared_types.thread_identity import resolve_thread_id

logger = get_logger("core.orchestrator")

AGENT_WINDOW = 12
MOOD_WINDOW = 4
COMPACT_IDLE_SECONDS = 60 * 30
COMPACT_TRIGGER_PREFIX = "compact:"
LIFE_NOTE_MAX_AGE_SECONDS = 60 * 60 * 24 * 3


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

    async def run(self) -> None:
        while True:
            envelope: MessageEnvelope = await self.bus.consume()
            try:
                # Resolve the conversation thread once, then route by source.
                forced_thread_id = str(
                    os.getenv("FORCE_THREAD_ID", "")).strip()
                explicit_thread_id = str(
                    dict(envelope.metadata or {}).get("thread_id") or ""
                ).strip()
                thread_id = (
                    forced_thread_id
                    or explicit_thread_id
                    or resolve_thread_id(
                        target_user_id=envelope.target_user_id,
                        channel_id=envelope.channel_id,
                        author_id=envelope.author_id,
                    )
                )

                if envelope.source == MessageSource.LIFE:
                    await self._handle_life(envelope, thread_id)
                    continue

                if envelope.source == MessageSource.COMPACT:
                    await self._handle_compact(envelope, thread_id)
                    continue

                await self._handle_chat(envelope, thread_id)

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

    async def _handle_life(self, envelope: MessageEnvelope, thread_id: str) -> None:
        await self.state_store.prune_life_notes(
            thread_id,
            max_age_seconds=LIFE_NOTE_MAX_AGE_SECONDS,
        )
        history = await self.state_store.get_history(thread_id)
        summary = _compacted_summary(history.all())
        life_profile = await self.state_store.get_life_profile(thread_id)
        episodic = await self.episodic_memory.recall(
            query=str(envelope.content or "").strip(
            ) or "recent internal continuity",
            limit=3,
            thread_id=thread_id,
        )
        note = await self.life_agent.reflect(
            content=envelope.content,
            summary=summary,
            episodic=episodic,
            life_profile=life_profile,
        )
        if note:
            await self.state_store.append_life_note(
                thread_id,
                note=_life_note(note),
            )

    # Scheduled compaction bypasses the chat-turn threshold gate.
    async def _handle_compact(self, envelope: MessageEnvelope, thread_id: str) -> None:

        await self.conversation_contraction.compact(
            thread_id=thread_id,
            state_store=self.state_store,
            episodic_memory=self.episodic_memory,
        )

    async def _handle_chat(self, envelope: MessageEnvelope, thread_id: str) -> None:
        content = (envelope.content or "").strip()
        if not content:
            return

        # Build the short-term context used for mood analysis and reply generation.
        mood = await self.state_store.get_mood(thread_id)
        messages_for_agent = await self.state_store.get_agent_context(thread_id, AGENT_WINDOW)
        messages_for_mood_analysis = await self.state_store.get_mood_context(thread_id, MOOD_WINDOW)

        # Update live mood state before generating the reply.
        delta = await self.mood_engine.analyze(
            content=content,
            messages=messages_for_mood_analysis,
            thread_id=thread_id
        )
        next_mood = self.mood_engine.apply(mood, delta)

        await self.state_store.set_mood(thread_id, next_mood)

        # Recall a small number of long-term facts relevant to this turn.
        facts = await self.episodic_memory.recall(
            query=content,
            limit=2,
            thread_id=thread_id,
        )
        print(facts)

        # LLM call
        reply_text = await self.agent.respond(
            content=content,
            messages=messages_for_agent,
            episodic=facts,
            mood=next_mood,
            envelope=envelope,
        )

        # Persist the raw turn before any later compaction happens.
        await self.state_store.append_messages(
            thread_id,
            [
                HumanMessage(content=content),
                AIMessage(content=reply_text)
            ]
        )

        # Reset the idle compact timer so history compresses only after inactivity.
        await self._reschedule_compact_trigger(thread_id)

        try:
            # Opportunistic compaction keeps history under the active threshold.
            await self.conversation_contraction.maybe_compact(
                thread_id=thread_id,
                state_store=self.state_store,
                episodic_memory=self.episodic_memory,
            )
        except Exception as exc:
            await logger.error(
                "contraction_failed",
                "Compaction failed.",
                context={"thread_id": thread_id},
                error=exc,
            )

        reply_text = (reply_text or "").strip()
        if not reply_text and envelope.source != MessageSource.WEBHOOK:
            return None

        try:
            await self.output.send(self._build_outbound(envelope, reply_text))
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

    async def _reschedule_compact_trigger(self, thread_id: str) -> None:
        # One pending trigger per thread gives "compact after inactivity" behavior.
        trigger_id = f"{COMPACT_TRIGGER_PREFIX}{thread_id}"
        await self.scheduler.remove(trigger_id)
        await self.scheduler.push(
            Trigger(
                trigger_type=TriggerType.PRECISE,
                source=MessageSource.COMPACT,
                interval_seconds=COMPACT_IDLE_SECONDS,
                metadata={"thread_id": thread_id},
                repeat=False,
                _trigger_id=trigger_id,
            )
        )

    @staticmethod
    def _build_outbound(envelope: MessageEnvelope, content: str) -> OutboundMessage:
        return OutboundMessage(
            source=envelope.source,
            content=content,
            channel_id=envelope.channel_id,
            target_user_id=envelope.target_user_id,
            metadata=ensure_outbound_webhook_metadata(
                envelope.metadata,
                envelope_id=envelope.id,
            ),
            reply_to_message_id=envelope.message_id,
            mention_author=bool(
                envelope.channel_id and not envelope.target_user_id),
        )


def _compacted_summary(messages: list[BaseMessage]) -> str:
    if not messages:
        return ""
    first = messages[0]
    if bool(getattr(first, "additional_kwargs", {}).get("kayori_compacted")):
        return str(first.content or "").strip()
    return ""


def _life_note(content: str) -> LifeNote:
    return LifeNote(
        content=" ".join(str(content or "").strip().split()),
        timestamp=datetime.now(UTC).isoformat(),
    )
