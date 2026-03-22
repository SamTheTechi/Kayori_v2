from __future__ import annotations

import asyncio
from dataclasses import dataclass

from src.logger import get_logger
from src.shared_types.models import MessageSource, OutboundMessage
from src.shared_types.protocol import OutputAdapter
from src.shared_types.types import OutputSinkMode

logger = get_logger("core.outputsink")


@dataclass(slots=True)
class OutputSink:
    outputs: list[OutputAdapter]
    name: str = "multi-output-sink"
    mode: OutputSinkMode = "direct"

    async def start(self) -> None:
        for output in self.outputs:
            await output.start()

    async def stop(self) -> None:
        for output in reversed(self.outputs):
            await output.stop()

    async def send(self, message: OutboundMessage) -> None:
        if not self.outputs:
            return

        selected_outputs = self._select_outputs(message)
        if not selected_outputs:
            await logger.warning(
                "output_dropped_no_targets",
                "Dropped outbound message because no outputs were selected.",
                context={
                    "source": str(message.source),
                    "channel_id": message.channel_id,
                    "target_user_id": message.target_user_id,
                },
            )
            return

        results = await asyncio.gather(
            *(output.send(message) for output in selected_outputs),
            return_exceptions=True,
        )
        for output, result in zip(selected_outputs, results, strict=False):
            if isinstance(result, Exception):
                await logger.exception(
                    "output_send_failed",
                    "Output adapter send failed.",
                    context={
                        "adapter": output.name,
                        "source": str(message.source),
                        "channel_id": message.channel_id,
                        "target_user_id": message.target_user_id,
                    },
                    error=result,
                )

    def _select_outputs(self, message: OutboundMessage) -> list[OutputAdapter]:
        if self.mode == "multi":
            return list(self.outputs)

        source = message.source

        if source == MessageSource.DISCORD:
            source_name = "discord"
        elif source == MessageSource.TELEGRAM:
            source_name = "telegram"
        elif source == MessageSource.CONSOLE:
            source_name = "console"
        elif source == MessageSource.WEBHOOK:
            source_name = "webhook"
        else:
            source_name = None

        if source_name is None:
            return list(self.outputs)

        matched = [output for output in self.outputs if output.name == source_name]
        if matched:
            return matched

        return list(self.outputs)


__all__ = ["OutputSink"]
