from shared_types.protocal import MessageBus
from typing import Any


class LangGraphOrchestrator:
    def __init__(
        self,
        *,
        bus: MessageBus,
        graph: Any,
    ) -> None:
        self._bus = bus
        self._graph = graph

    async def run(self) -> None:
        while True:
            envelope = await self._bus.consume()
            try:
                await self._graph.ainvoke({"envelope": envelope})
            except Exception as exc:
                print(f"[orchestrator] graph invoke failed for envelope={
                      envelope.id}: {exc}")
