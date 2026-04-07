from __future__ import annotations

from dataclasses import dataclass
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

logger = get_logger("core.orchestrator")

AGENT_WINDOW = 12
MOOD_WINDOW = 4
COMPACT_IDLE_SECONDS = 60 * 30
COMPACT_TRIGGER_ID = "compact"
LIFE_NOTE_MAX_AGE_SECONDS = 60 * 60 * 24 * 3
MAX_PENDING_LIFE_NOTES = 3


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
        del envelope
        today = datetime.now(UTC).date().isoformat()
        interaction = await self.state_store.get_interaction_state()
        if interaction.proactive_sent_day != today:
            interaction.proactive_sent_day = today
            interaction.proactive_sent_today = 0

        if (
            interaction.last_proactive_message_at
            and (
                not interaction.last_user_message_at
                or interaction.last_user_message_at <= interaction.last_proactive_message_at
            )
        ):
            interaction.ignored_proactive_count += 1

        mood = await self.state_store.get_mood()
        score = (
            float(mood.Trust)
            + float(mood.Attachment)
            + float(mood.Confidence)
        ) / 3.0
        cap = 0 if score < 0.58 else 1 if score < 0.68 else 2 if score < 0.78 else 3

        if (
            not interaction.last_route_source
            or cap <= 0
            or interaction.proactive_sent_today >= cap
            or interaction.ignored_proactive_count >= 2
        ):
            await self.state_store.set_interaction_state(interaction)
            return

        proactive_envelope = MessageEnvelope(
            source=MessageSource.PROACTIVE,
            content="",
            channel_id=interaction.last_channel_id,
            target_user_id=interaction.last_target_user_id,
            author_id=interaction.last_author_id,
            metadata={"route_source": interaction.last_route_source},
        )
        await self.state_store.set_interaction_state(interaction)
        await self._handle_chat(proactive_envelope)

    async def _handle_chat(self, envelope: MessageEnvelope) -> None:
        content = (envelope.content or "").strip()
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
            await self._record_proactive_send()
        else:
            await self.state_store.append_messages(
                [
                    HumanMessage(content=content),
                    AIMessage(content=reply_text)
                ]
            )
            await self._record_user_interaction(envelope)
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
                route_source = str(dict(envelope.metadata or {}).get(
                    "route_source") or "").strip()
                if not route_source:
                    return
                await self.output.send(
                    OutboundMessage(
                        source=MessageSource(route_source),
                        content=reply_text,
                        channel_id=envelope.channel_id,
                        target_user_id=envelope.target_user_id,
                        metadata={},
                    )
                )
            else:
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
        envelope: MessageEnvelope,
    ) -> None:
        state = await self.state_store.get_interaction_state()
        state.last_user_message_at = datetime.now(UTC).isoformat()

        state.last_route_source = envelope.source.value
        state.last_channel_id = envelope.channel_id
        state.last_target_user_id = envelope.target_user_id
        state.last_author_id = envelope.author_id
        if state.last_proactive_message_at:
            state.ignored_proactive_count = 0
        await self.state_store.set_interaction_state(state)

    async def _record_proactive_send(self) -> None:
        state = await self.state_store.get_interaction_state()
        now = datetime.now(UTC)
        state.last_proactive_message_at = now.isoformat()
        state.proactive_sent_today += 1
        state.proactive_sent_day = now.date().isoformat()
        await self.state_store.set_interaction_state(state)

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
