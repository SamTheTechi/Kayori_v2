from __future__ import annotations

import asyncio
import os
import warnings
from typing import Any

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from agent import ReactAgentService
from core.orchestrator import LangGraphOrchestrator
from adapters.safty.audit_logger import JsonlAuditLogger
from adapters.bus.in_memory import InMemoryMessageBus
from adapters.input.console_input import ConsoleInputGateway
from adapters.input.discord_input import DiscordInputAdapter
from adapters.input.telegram_input import TelegramInputAdapter
from adapters.output.console_output import ConsoleOutputAdapter
from adapters.output.discord_output import DiscordOutputAdapter
from adapters.dispatcher.ouput import MultiOutputDispatcher
from adapters.output.telegram_output import TelegramOutputAdapter
from adapters.runtime import DiscordRuntime, TelegramRuntime
from adapters.state.in_memory import InMemoryStateStore
from shared_types.models import OutboundMessage
from shared_types.protocal import InputAdapter, OutputAdapter
from shared_types.types import PipelineState
from tools import WeatherTool, ReminderTool, SpotifyTool
from langchain_tavily import TavilySearch

warnings.filterwarnings(
    "ignore",
    message=r"Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater\.",
    category=UserWarning,
)


def create_pipeline_graph(
    *,
    state_store: InMemoryStateStore,
    agent: ReactAgentService,
    output: OutputAdapter,
):
    workflow = StateGraph(PipelineState)

    async def load_state_node(state: PipelineState) -> dict[str, Any]:
        envelope = state["envelope"]
        if not (envelope.content or "").strip():
            return {"reply_text": "", "outbound": None}

        mood = await state_store.get_mood()
        thread_id = envelope.thread_id(fallback_user_id=envelope.author_id)
        return {"mood": mood, "thread_id": thread_id}

    async def call_agent_node(state: PipelineState) -> dict[str, str]:
        envelope = state["envelope"]
        user_text = (envelope.content or "").strip()
        if not user_text:
            return {"reply_text": ""}

        thread_id = state.get("thread_id") or envelope.thread_id(
            fallback_user_id=envelope.author_id
        )
        reply = await agent.respond(
            user_text=user_text,
            thread_id=thread_id,
            mood=state.get("mood"),
            envelope=envelope,
        )
        return {"reply_text": (reply or "").strip()}

    def build_outbound_node(state: PipelineState) -> dict[str, OutboundMessage | None]:
        envelope = state["envelope"]
        reply_text = (state.get("reply_text") or "").strip()
        if not reply_text:
            return {"outbound": None}

        target_user_id = None
        if envelope.is_dm:
            target_user_id = envelope.target_user_id or envelope.author_id

        outbound = OutboundMessage(
            content=reply_text,
            is_dm=envelope.is_dm,
            channel_id=envelope.channel_id,
            target_user_id=target_user_id,
            source_hint=envelope.source,
            reply_to_message_id=envelope.message_id,
            mention_author=not envelope.is_dm,
        )
        return {"outbound": outbound}

    async def send_output_node(state: PipelineState) -> dict[str, Any]:
        outbound = state.get("outbound")
        if outbound is None:
            return {}

        try:
            await output.send(outbound)
        except Exception as exc:
            print(f"[orchestrator] output send failed: {exc}")
        return {}

    workflow.add_node("load_state", load_state_node)
    workflow.add_node("call_agent", call_agent_node)
    workflow.add_node("build_outbound", build_outbound_node)
    workflow.add_node("send_output", send_output_node)

    workflow.add_edge(START, "load_state")
    workflow.add_edge("load_state", "call_agent")
    workflow.add_edge("call_agent", "build_outbound")
    workflow.add_edge("build_outbound", "send_output")
    workflow.add_edge("send_output", END)

    return workflow.compile()


async def _main() -> None:
    load_dotenv()
    enabled_inputs = ["discord"]
    enabled_outputs = ["discord"]

    discord_token = os.getenv("DISCORD_BOT_TOKEN", "")
    discord_output_user_id = os.getenv("DISCORD_TOKEN", "")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_output_chat_id = os.getenv("TELEGRAM_OUTPUT_CHAT_ID", "")

    discord_runtime = DiscordRuntime(token=discord_token)
    telegram_runtime = TelegramRuntime(token=telegram_token)

    bus = InMemoryMessageBus()
    state = InMemoryStateStore()

    # tools = [
    #     WeatherTool(state_store=state, api_key=os.getenv("WEATHER_API_KEY")),
    #     ReminderTool(bus=bus, fallback_user_id=os.getenv("REMINDER_FALLBACK_USER_ID")),
    #     UserDeviceTool(
    #         state_store=state,
    #         join_api_key=os.getenv("JOIN_API_KEY"),
    #         join_device_id=os.getenv("JOIN_DEVICE_ID"),
    #     ),
    #     SpotifyTool(
    #         enabled=str(os.getenv("ENABLE_SPOTIFY_TOOL", "false")).strip().lower()
    #         in {"1", "true", "yes", "on"}
    #     ),
    # ]

    tools = [
        WeatherTool(state_store=state, api_key=os.getenv("WEATHER_API_KEY")),
        ReminderTool(bus=bus),
        SpotifyTool(
            enabled=str(os.getenv("ENABLE_SPOTIFY_TOOL", "false")
                        ).strip().lower()
            in {"1", "true", "yes", "on"}
        ),
        TavilySearch(
            max_results=3,
            topic="general"
        ),
    ]

    audit_enabled = str(os.getenv("ENABLE_TOOL_AUDIT", "true")
                        ).strip().lower() in {"1", "true", "yes", "on"}
    audit_path = os.getenv("TOOL_AUDIT_LOG_PATH", "logs/tool_audit.jsonl")
    try:
        audit_max_lines = int(str(os.getenv("TOOL_AUDIT_MAX_LINES", "5000")).strip() or "5000")
    except Exception:
        audit_max_lines = 5000
    audit_logger = JsonlAuditLogger(
        path=audit_path,
        enabled=audit_enabled,
        max_lines=audit_max_lines,
    )

    agent = ReactAgentService.from_env(
        model_name="openai/gpt-oss-120b",
        tools=tools,
        audit_logger=audit_logger,
    )

    outputs: list[OutputAdapter] = []
    for name in enabled_outputs:
        if name == "console":
            outputs.append(ConsoleOutputAdapter())
        elif name == "discord":
            if discord_runtime is None:
                raise RuntimeError("Discord output enabled without runtime.")
            outputs.append(
                DiscordOutputAdapter(
                    runtime=discord_runtime,
                    default_channel_id=None,
                    default_user_id=discord_output_user_id,
                )
            )
        elif name == "telegram":
            if telegram_runtime is None:
                raise RuntimeError("Telegram output enabled without runtime.")
            outputs.append(
                TelegramOutputAdapter(
                    runtime=telegram_runtime,
                    default_chat_id=telegram_output_chat_id,
                )
            )

    if not outputs:
        raise RuntimeError("At least one output adapter must be enabled.")

    output_dispatcher = MultiOutputDispatcher(outputs=outputs)
    graph = create_pipeline_graph(
        state_store=state, agent=agent, output=output_dispatcher)
    orchestrator = LangGraphOrchestrator(bus=bus, graph=graph)

    inputs: list[InputAdapter] = []
    for name in enabled_inputs:
        if name == "console":
            inputs.append(ConsoleInputGateway(bus=bus))
        elif name == "discord":
            if discord_runtime is None:
                raise RuntimeError("Discord input enabled without runtime.")
            inputs.append(DiscordInputAdapter(
                runtime=discord_runtime, bus=bus))
        elif name == "telegram":
            if telegram_runtime is None:
                raise RuntimeError("Telegram input enabled without runtime.")
            inputs.append(
                TelegramInputAdapter(
                    runtime=telegram_runtime,
                    bus=bus,
                    allowed_chat_ids=None
                )
            )

    if not inputs:
        raise RuntimeError("At least one input adapter must be enabled.")

    orchestrator_task = asyncio.create_task(
        orchestrator.run(), name="orchestrator")
    input_tasks: list[asyncio.Task[None]] = []

    await output_dispatcher.start()

    try:
        for adapter in inputs:
            input_tasks.append(asyncio.create_task(
                adapter.start(), name=f"input-{adapter.name}"))

        await asyncio.gather(*input_tasks)
    finally:
        for adapter in inputs:
            try:
                await adapter.stop()
            except Exception as exc:
                print(f"[shutdown] input stop failed ({adapter.name}): {exc}")

        for task in input_tasks:
            task.cancel()
        await asyncio.gather(*input_tasks, return_exceptions=True)

        orchestrator_task.cancel()
        await asyncio.gather(orchestrator_task, return_exceptions=True)

        await output_dispatcher.stop()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
