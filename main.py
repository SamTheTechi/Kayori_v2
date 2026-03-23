import asyncio
import os

from dotenv import load_dotenv
from langchain_tavily import TavilySearch
from langchain_groq import ChatGroq

# from redis.asyncio import Redis

from src.adapters.audio.stt import WhisperSttAdapter
from src.adapters.audio.tts import EdgeTtsAdapter
from src.adapters.bus.in_memory import InMemoryMessageBus
from src.adapters.input.console_input import ConsoleInputGateway
from src.adapters.input.discord_input import DiscordInputAdapter
from src.adapters.input.telegram_input import TelegramInputAdapter
from src.adapters.input.webhook_input import WebhookInputAdapter
from src.adapters.output.console_output import ConsoleOutputAdapter
from src.adapters.output.discord_output import DiscordOutputAdapter
from src.adapters.output.telegram_output import TelegramOutputAdapter
from src.adapters.output.webhook_output import WebhookOutputAdapter
from src.adapters.runtime.discord_runtime import DiscordRuntime
from src.adapters.runtime.telegram_runtime import TelegramRuntime
from src.adapters.runtime.webhook_runtime import WebhookRuntime
from src.adapters.state.in_memory import InMemoryStateStore
from src.agent.service import ReactAgentService
from src.core.mood_engine import MoodEngine
from src.core.orchestrator import AgentOrchestrator
from src.core.outputsink import OutputSink
from src.logger import get_logger
from src.shared_types.protocol import InputAdapter, OutputAdapter
from src.tools.calendar import CalendarTools
from src.tools.reminder import ReminderTool
from src.tools.spotify import SpotifyTool


logger = get_logger("examples.main")


async def _main() -> None:
    load_dotenv()

    enabled_inputs = ["telegram", "webhook"]
    enabled_outputs = ["telegram", "webhook"]

    # Runtime configuration.
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
        host="0.0.0.0",
        port=8080,
        bearer_token=webhook_bearer_token,
    )

    bus = InMemoryMessageBus()
    state = InMemoryStateStore()

    # redis_client = Redis.from_url()
    # bus = RedisMessageBus(redis_client),
    # state = RedisStateStore(redis_client),

    webhook_tts = EdgeTtsAdapter(api_key=tts_api_key, base_url=tts_base_url)

    # Output adapters.
    outputs: list[OutputAdapter] = []
    for name in enabled_outputs:
        if name == "console":
            outputs.append(ConsoleOutputAdapter())
        elif name == "discord":
            outputs.append(
                DiscordOutputAdapter(
                    runtime=discord_runtime,
                    default_channel_id=None,
                    default_user_id=discord_output_user_id,
                )
            )
        elif name == "telegram":
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

    # Agent tools.
    tools = [
        # WeatherTool(state_store=state, api_key=os.getenv("WEATHER_API_KEY")),
        ReminderTool(output=output_dispatcher),
        SpotifyTool(),
        TavilySearch(max_results=3, topic="general"),
    ]
    tools.extend(CalendarTools())
    # tools.extend(GmailTools())

    chat_model = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.6,
        api_key=groq_api_key
    )
    chat_model2 = ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.7,
        api_key=groq_api_key
    )

    agent = ReactAgentService(
        model=chat_model,
        tools=tools
    )

    mood_engine = MoodEngine(
        model=chat_model2,
    )

    orchestrator = AgentOrchestrator(
        bus=bus,
        state_store=state,
        agent=agent,
        mood_engine=mood_engine,
        output=output_dispatcher,
    )

    # scheduler = AgentScheduler.with_memory(
    #     bus=bus,
    #     state_store=state
    # )

    # Input adapters.
    inputs: list[InputAdapter] = []
    for name in enabled_inputs:
        if name == "console":
            inputs.append(ConsoleInputGateway(bus=bus))
        elif name == "discord":
            inputs.append(DiscordInputAdapter(
                runtime=discord_runtime, bus=bus))
        elif name == "telegram":
            inputs.append(
                TelegramInputAdapter(
                    runtime=telegram_runtime,
                    bus=bus,
                    allowed_chat_ids=None,
                )
            )
        elif name == "webhook":
            inputs.append(
                WebhookInputAdapter(
                    runtime=webhook_runtime,
                    bus=bus,
                    stt=WhisperSttAdapter(api_key=groq_api_key),
                )
            )

    if not inputs:
        raise RuntimeError("At least one input adapter must be enabled.")

    for adapter in inputs:
        if isinstance(adapter, WebhookInputAdapter):
            adapter.register_routes()

    orchestrator_task = asyncio.create_task(
        orchestrator.run(),
        name="orchestrator"
    )
    input_tasks: list[asyncio.Task[None]] = []

    await output_dispatcher.start()
    await webhook_runtime.start()
    # await scheduler.start()

    try:
        # now = time.time()
        # local_now = datetime.now().astimezone()
        # second_of_day = (
        #     local_now.hour * 3600 + local_now.minute * 60 + local_now.second
        # )
        #
        # # One trigger per scheduler mode for quick manual testing.
        # demo_triggers = [
        #     Trigger(
        #         trigger_type=TriggerType.PRECISE,
        #         fire_at=now + 5,
        #         payload={
        #             "message": "Scheduler demo ping.",
        #             "metadata": {"kind": "scheduler_demo_precise"},
        #         },
        #     ),
        #     Trigger(
        #         trigger_type=TriggerType.FUZZY,
        #         window_start_ts=now + 7,
        #         window_end_ts=now + 12,
        #         payload={
        #             "message": "Fuzzy demo ping.",
        #             "metadata": {"kind": "scheduler_demo_fuzzy"},
        #         },
        #     ),
        #     Trigger(
        #         trigger_type=TriggerType.MOOD,
        #         mood_key="Calmness",
        #         mood_threshold=0.4,
        #         mood_direction="gte",
        #         check_interval_sec=3,
        #         payload={
        #             "message": "Mood demo ping.",
        #             "metadata": {"kind": "scheduler_demo_mood"},
        #         },
        #     ),
        #     Trigger(
        #         trigger_type=TriggerType.CURIOSITY,
        #         allowed_window_start_sec=second_of_day + 9,
        #         allowed_window_end_sec=second_of_day + 15,
        #         target_slots_per_day=1,
        #         payload={
        #             "message": "Curiosity demo ping.",
        #             "metadata": {"kind": "scheduler_demo_curiosity"},
        #         },
        #     ),
        # ]
        #
        # for trigger in demo_triggers:
        #     await scheduler.push(trigger)

        for adapter in inputs:
            input_tasks.append(
                asyncio.create_task(
                    adapter.start(), name=f"input-{adapter.name}")
            )

        await asyncio.gather(*input_tasks)
    finally:
        for adapter in inputs:
            try:
                await adapter.stop()
            except Exception as exc:
                await logger.exception(
                    "input_stop_failed",
                    "Input adapter stop failed during shutdown.",
                    context={"adapter": adapter.name},
                    error=exc,
                )

        for task in input_tasks:
            task.cancel()
        await asyncio.gather(*input_tasks, return_exceptions=True)
        # await redis_client.shutdown()
        orchestrator_task.cancel()
        await asyncio.gather(orchestrator_task, return_exceptions=True)
        # await scheduler.stop()
        await webhook_runtime.stop()
        await output_dispatcher.stop()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
