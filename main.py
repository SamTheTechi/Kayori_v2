import os
import asyncio
from dotenv import load_dotenv

from agent import ReactAgentService

from core.orchestrator import AgentOrchestrator
from core.ouputsink import OutputSink

from adapters.safty.audit_logger import JsonlAuditLogger
from adapters.bus.in_memory import InMemoryMessageBus
from adapters.input.console_input import ConsoleInputGateway
from adapters.input.discord_input import DiscordInputAdapter
from adapters.input.telegram_input import TelegramInputAdapter
from adapters.output.console_output import ConsoleOutputAdapter
from adapters.output.discord_output import DiscordOutputAdapter
from adapters.output.telegram_output import TelegramOutputAdapter

from adapters.runtime import DiscordRuntime, TelegramRuntime
from adapters.state.in_memory import InMemoryStateStore

from shared_types.protocal import InputAdapter, OutputAdapter
from shared_types.types import OutputSinkMode

from tools import WeatherTool, ReminderTool, SpotifyTool
from langchain_tavily import TavilySearch


async def _main() -> None:
    load_dotenv()
    enabled_inputs = ["discord"]
    enabled_outputs = ["discord"]

    discord_token = os.getenv("DISCORD_BOT_TOKEN", "")
    discord_output_user_id = os.getenv("DISCORD_USER_ID", "")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_output_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    discord_runtime = DiscordRuntime(token=discord_token)
    telegram_runtime = TelegramRuntime(token=telegram_token)

    bus = InMemoryMessageBus()
    state = InMemoryStateStore()

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

    output_dispatcher = OutputSink(
        outputs=outputs,
        mode="direct"
    )

    tools = [
        WeatherTool(state_store=state, api_key=os.getenv("WEATHER_API_KEY")),
        ReminderTool(
            output=output_dispatcher,
            fallback_user_id=os.getenv("REMINDER_FALLBACK_USER_ID"),
        ),
        SpotifyTool(),
        TavilySearch(
            max_results=3,
            topic="general"
        ),
    ]

    audit_path = os.getenv("TOOL_AUDIT_LOG_PATH", "logs/tool_audit.jsonl")
    audit_logger = JsonlAuditLogger(
        path=audit_path,
        enabled=True,
    )

    agent = ReactAgentService.from_env(
        model_name="openai/gpt-oss-120b",
        tools=tools,
        audit_logger=audit_logger,
    )

    orchestrator = AgentOrchestrator(
        bus=bus,
        state_store=state,
        agent=agent,
        output=output_dispatcher
    )

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
