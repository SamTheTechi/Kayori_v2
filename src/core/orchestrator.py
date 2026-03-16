from __future__ import annotations

from dataclasses import dataclass

from agent import ReactAgentService
from logger import get_logger
from shared_types.models import MessageEnvelope, MessageSource, OutboundMessage
from shared_types.protocol import MessageBus, OutputAdapter, StateStore

logger = get_logger("core.orchestrator")


@dataclass(slots=True)
class AgentOrchestrator:
    state_store: StateStore
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
        message = (envelope.content or "").strip()
        if not message:
            return

        mood = await self.state_store.get_mood()
        thread_id = envelope.thread_id(fallback_user_id=envelope.author_id)

        reply_text = await self.agent.respond(
            message=message,
            thread_id=thread_id,
            mood=mood,
        )

        content = (reply_text or "").strip()
        if not content:
            if (
                envelope.source == MessageSource.WEBHOOK
                and str(
                    (envelope.metadata or {}).get(
                        "webhook_correlation_id") or ""
                ).strip()
            ):
                outbound = OutboundMessage(
                    source=envelope.source,
                    content="",
                    channel_id=envelope.channel_id,
                    target_user_id=envelope.target_user_id,
                    metadata={
                        **dict(envelope.metadata or {}),
                        "webhook_envelope_id": envelope.id,
                    },
                    reply_to_message_id=envelope.message_id,
                    mention_author=bool(
                        envelope.channel_id and not envelope.target_user_id
                    ),
                )
                try:
                    await self.output.send(outbound)
                except Exception as exc:
                    await logger.exception(
                        "orchestrator_output_send_failed",
                        "Failed to send webhook empty-response acknowledgement.",
                        context={
                            "envelope_id": envelope.id,
                            "source": str(envelope.source),
                            "channel_id": envelope.channel_id,
                            "target_user_id": envelope.target_user_id,
                        },
                        error=exc,
                    )
            return None

        outbound = OutboundMessage(
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

        if outbound is None:
            return

        try:
            await self.output.send(outbound)
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
