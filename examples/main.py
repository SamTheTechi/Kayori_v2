import asyncio
import os

from dotenv import load_dotenv
from langchain_tavily import TavilySearch

from adapters.audio import EdgeTtsAdapter, WhisperSttAdapter
from adapters.bus.in_memory import InMemoryMessageBus
from adapters.input.console_input import ConsoleInputGateway
from adapters.input.discord_input import DiscordInputAdapter
from adapters.input.telegram_input import TelegramInputAdapter
from adapters.input.webhook_input import WebhookInputAdapter
from adapters.output.console_output import ConsoleOutputAdapter
from adapters.output.discord_output import DiscordOutputAdapter
from adapters.output.telegram_output import TelegramOutputAdapter
from adapters.output.webhook_output import WebhookOutputAdapter
from adapters.runtime import DiscordRuntime, TelegramRuntime, WebhookRuntime
from adapters.safety.audit_logger import JsonlAuditLogger
from adapters.state.in_memory import InMemoryStateStore
from agent import ReactAgentService
from core import AgentOrchestrator, OutputSink
from shared_types.protocol import InputAdapter, OutputAdapter
from tools import ReminderTool, SpotifyTool, WeatherTool


async def _main() -> None:
    load_dotenv()
    enabled_inputs = ["discord", "webhook"]
    enabled_outputs = ["discord", "webhook"]

    discord_token = os.getenv("DISCORD_BOT_TOKEN", "")
    discord_output_user_id = os.getenv("DISCORD_USER_ID", "")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_output_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    groq_api_key = str(os.getenv("API_KEY", "")).strip()

    webhook_bearer_token = "123"
    tts_base_url = "http://localhost:5050/v1"
    tts_api_key = "123"
    webhook_output_targets = [
        item.strip()
        for item in str(os.getenv("WEBHOOK_OUTPUT_URLS", "")).split(",")
        if item.strip()
    ]
    webhook_output_token = (
        str(os.getenv("WEBHOOK_OUTPUT_BEARER_TOKEN", "")).strip() or None
    )

    discord_runtime = DiscordRuntime(token=discord_token)
    telegram_runtime = TelegramRuntime(token=telegram_token)
    webhook_runtime = WebhookRuntime(
        host="127.0.0.1",
        port=8080,
        bearer_token=webhook_bearer_token,
    )

    bus = InMemoryMessageBus()
    state = InMemoryStateStore()
    webhook_tts = EdgeTtsAdapter(
        api_key=tts_api_key,
        base_url=tts_base_url,
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
        elif name == "webhook":
            outputs.append(
                WebhookOutputAdapter(
                    targets=webhook_output_targets,
                    runtime=webhook_runtime,
                    tts=webhook_tts,
                    bearer_token=webhook_output_token,
                )
            )

    if not outputs:
        raise RuntimeError("At least one output adapter must be enabled.")

    output_dispatcher = OutputSink(outputs=outputs, mode="direct")

    tools = [
        WeatherTool(state_store=state, api_key=os.getenv("WEATHER_API_KEY")),
        ReminderTool(
            output=output_dispatcher,
        ),
        SpotifyTool(),
        TavilySearch(max_results=3, topic="general"),
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
        bus=bus, state_store=state, agent=agent, output=output_dispatcher
    )

    inputs: list[InputAdapter] = []
    for name in enabled_inputs:
        if name == "console":
            inputs.append(ConsoleInputGateway(bus=bus))
        elif name == "discord":
            if discord_runtime is None:
                raise RuntimeError("Discord input enabled without runtime.")
            inputs.append(DiscordInputAdapter(runtime=discord_runtime, bus=bus))
        elif name == "telegram":
            if telegram_runtime is None:
                raise RuntimeError("Telegram input enabled without runtime.")
            inputs.append(
                TelegramInputAdapter(
                    runtime=telegram_runtime, bus=bus, allowed_chat_ids=None
                )
            )
        elif name == "webhook":
            if webhook_runtime is None:
                raise RuntimeError("Webhook input enabled without runtime.")
            inputs.append(
                WebhookInputAdapter(
                    runtime=webhook_runtime,
                    bus=bus,
                    stt=WhisperSttAdapter(api_key=groq_api_key),
                )
            )

    if not inputs:
        raise RuntimeError("At least one input adapter must be enabled.")

    orchestrator_task = asyncio.create_task(orchestrator.run(), name="orchestrator")
    input_tasks: list[asyncio.Task[None]] = []

    for adapter in inputs:
        if isinstance(adapter, WebhookInputAdapter):
            adapter.register_routes()

    await output_dispatcher.start()
    if webhook_runtime is not None:
        await webhook_runtime.start()

    try:
        for adapter in inputs:
            input_tasks.append(
                asyncio.create_task(adapter.start(), name=f"input-{adapter.name}")
            )

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

        if webhook_runtime is not None:
            await webhook_runtime.stop()

        await output_dispatcher.stop()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
