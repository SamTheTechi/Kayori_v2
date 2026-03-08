from __future__ import annotations

import asyncio
from dataclasses import dataclass

from shared_types.models import OutboundMessage, MessageSource
from shared_types.types import OutputSinkMode
from shared_types.protocal import OutputAdapter


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
            print(
                f"[output-dispatcher] dropped message with no outputs for source={
                    message.source}"
            )
            return

        results = await asyncio.gather(
            *(output.send(message) for output in selected_outputs),
            return_exceptions=True,
        )
        for output, result in zip(selected_outputs, results):
            if isinstance(result, Exception):
                print(
                    f"[output-dispatcher] send failed on {output.name}: {result}")

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
        else:
            source_name = None

        if source_name is None:
            return list(self.outputs)

        matched = [
            output for output in self.outputs if output.name == source_name]
        if matched:
            return matched

        return list(self.outputs)


__all__ = ["OutputSink"]
