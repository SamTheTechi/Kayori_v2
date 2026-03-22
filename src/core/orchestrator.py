from __future__ import annotations

from dataclasses import dataclass

from src.agent import ReactAgentService
from src.core.mood_engine import MoodEngine
from src.logger import get_logger
from src.shared_types.models import MessageEnvelope, MessageSource, OutboundMessage
from src.shared_types.thread_identity import resolve_thread_id
from src.shared_types.protocol import MessageBus, OutputAdapter, StateStore
from langchain_core.messages import HumanMessage, AIMessage

logger = get_logger("core.orchestrator")


@dataclass(slots=True)
class AgentOrchestrator:
    state_store: StateStore
    mood_engine: MoodEngine
    agent: ReactAgentService
    output: OutputAdapter
    bus: MessageBus

    async def run(self) -> None:
        while True:
            envelope: MessageEnvelope = await self.bus.consume()
            try:
                await self._handle_envelope(envelope)
            except Exception as exc:
                await logger.exception(
                    "orchestrator_envelope_failed",
                    "Failed to process inbound envelope.",
                    context={
                        "envelope_id": envelope.id,
                        "source": str(envelope.source),
                        "author_id": envelope.author_id,
                        "channel_id": envelope.channel_id,
                        "message_id": envelope.message_id,
                    },
                    error=exc,
                )

    async def _handle_envelope(self, envelope: MessageEnvelope) -> None:
        content = (envelope.content or "").strip()
        if not content:
            return

        thread_id = resolve_thread_id(
            target_user_id=envelope.target_user_id,
            channel_id=envelope.channel_id,
            author_id=envelope.author_id,
        )

        mood = await self.state_store.get_mood(thread_id)
        messages = await self.state_store.get_window(thread_id, 16)

        delta = await self.mood_engine.analyze(content)
        next_mood = self.mood_engine.apply(mood, delta)

        await self.state_store.set_mood(thread_id, next_mood)

        reply_text = await self.agent.respond(
            content=content,
            messages=messages,
            thread_id=thread_id,
            mood=next_mood,
        )

        await self.state_store.append_messages(
            thread_id,
            [
                HumanMessage(content=content),
                AIMessage(content=reply_text)
            ]
        )

        content = (reply_text or "").strip()
        if not content and envelope.source != MessageSource.WEBHOOK:
            return None

        try:
            await self.output.send(_build_outbound(envelope, content))
        except Exception as exc:
            await logger.exception(
                "orchestrator_output_send_failed",
                "Failed to send outbound response.",
                context={
                    "envelope_id": envelope.id,
                    "source": str(envelope.source),
                    "channel_id": envelope.channel_id,
                    "target_user_id": envelope.target_user_id,
                },
                error=exc,
            )

def _build_outbound(envelope: MessageEnvelope, content: str) -> OutboundMessage:
    return OutboundMessage(
        source=envelope.source,
        content=content,
        channel_id=envelope.channel_id,
        target_user_id=envelope.target_user_id,
        metadata={
            **dict(envelope.metadata or {}),
            "webhook_envelope_id": envelope.id,
        },
        reply_to_message_id=envelope.message_id,
        mention_author=bool(
            envelope.channel_id and not envelope.target_user_id),
    )
