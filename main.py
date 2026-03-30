import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_tavily import TavilySearch
from langchain_groq import ChatGroq
from langchain_community.embeddings import FastEmbedEmbeddings

from redis.asyncio import Redis as AsyncRedis
from redis import Redis as SyncRedis

from src.adapters.audio.stt import WhisperSttAdapter
from src.adapters.http.logs import register_logs_routes
from src.adapters.http.metrics import register_metrics_routes
from src.adapters.http.ping import register_ping_routes
from src.adapters.audio.tts import EdgeTtsAdapter
# from src.adapters.bus.in_memory import InMemoryMessageBus
from src.adapters.bus.redis_bus import RedisMessageBus
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
# from src.adapters.state.in_memory import InMemoryStateStore
from src.adapters.state.redis import RedisStateStore
# from src.adapters.memory.in_memory import InMemoryEpisodicMemory
from src.adapters.memory.redis import RedisEpisodicMemory
from src.agent.chat.service import ReactAgentService
from src.agent.life.service import LifeAgentService
from src.core.mood_engine import MoodEngine
from src.core.episodic_memory import EpisodicMemoryStore
from src.core.orchestrator import AgentOrchestrator
from src.core.outputsink import OutputSink
from src.core.conversation_contraction import ConversationContractionService
# from src.adapters.scheduler.in_memory import InMemorySchedulerBackend
from src.adapters.scheduler.redis import RedisSchedulerBackend
from src.core.scheduler import AgentScheduler
from src.logger import get_logger
from src.shared_types.models import MessageSource
from src.shared_types.protocol import InputAdapter, OutputAdapter, MessageBus
from src.shared_types.types import Trigger, TriggerType
from src.tools.calendar import CalendarTools
from src.tools.life_info import LifeInfoTool
from src.tools.reminder import ReminderTool
from src.tools.spotify import SpotifyTool


logger = get_logger("examples.main")


async def _main() -> None:
    load_dotenv()

    enabled_inputs = ["discord", "webhook"]
    enabled_outputs = ["discord", "webhook"]

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

    async_redis = AsyncRedis.from_url("redis://localhost:6379")
    sync_redis = SyncRedis.from_url("redis://localhost:6379")
    bus = RedisMessageBus(async_redis)
    state = RedisStateStore(async_redis)

    # bus = InMemoryMessageBus()
    # state = InMemoryStateStore()

    await _seed_life_profile_if_empty(state)

    embedding_model = FastEmbedEmbeddings(
        model_name="BAAI/bge-small-en-v1.5"
    )

    # memory_backend = InMemoryEpisodicMemory(embedding=embedding_model)
    memory_backend = RedisEpisodicMemory(
        redis_client=sync_redis, embedding=embedding_model)
    episodic_memory = EpisodicMemoryStore(backend=memory_backend)

    # scheduler_backend = InMemorySchedulerBackend()
    scheduler_backend = RedisSchedulerBackend(redis_client=async_redis)
    scheduler = AgentScheduler(
        backend=scheduler_backend,
        bus=bus
    )

    webhook_tts = EdgeTtsAdapter(
        api_key=tts_api_key,
        base_url=tts_base_url
    )

    # Output adapters.
    outputs = _build_outputs(
        enabled_outputs=enabled_outputs,
        discord_runtime=discord_runtime,
        discord_output_user_id=discord_output_user_id,
        telegram_runtime=telegram_runtime,
        telegram_output_chat_id=telegram_output_chat_id,
        webhook_runtime=webhook_runtime,
        webhook_tts=webhook_tts,
        webhook_output_targets=webhook_output_targets,
        webhook_output_token=webhook_output_token,
    )

    output_dispatcher = OutputSink(outputs=outputs, mode="direct")

    # Agent tools.
    tools = [
        # WeatherTool(state_store=state, api_key=os.getenv("WEATHER_API_KEY")),
        ReminderTool(output=output_dispatcher),
        LifeInfoTool(state_store=state),
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
    life_agent = LifeAgentService(
        model=chat_model2,
    )

    mood_engine = MoodEngine(
        model=chat_model2,
    )

    conversation_contraction = ConversationContractionService(
        model=chat_model2,
    )

    orchestrator = AgentOrchestrator(
        agent=agent,
        life_agent=life_agent,
        bus=bus,
        state_store=state,
        mood_engine=mood_engine,
        episodic_memory=episodic_memory,
        conversation_contraction=conversation_contraction,
        scheduler=scheduler,
        output=output_dispatcher,
    )

    # Input adapters.
    inputs = _build_inputs(
        enabled_inputs=enabled_inputs,
        bus=bus,
        discord_runtime=discord_runtime,
        telegram_runtime=telegram_runtime,
        webhook_runtime=webhook_runtime,
        groq_api_key=groq_api_key,
    )

    for adapter in inputs:
        if isinstance(adapter, WebhookInputAdapter):
            adapter.register_routes()

    orchestrator_task = asyncio.create_task(
        orchestrator.run(),
        name="orchestrator"
    )
    input_tasks: list[asyncio.Task[None]] = []

    await output_dispatcher.start()
    register_ping_routes(webhook_runtime)
    register_logs_routes(webhook_runtime)
    register_metrics_routes(webhook_runtime, state)
    await webhook_runtime.start()
    await scheduler.start()

    try:
        # await scheduler.push(
        #     Trigger(
        #         trigger_type=TriggerType.PRECISE,
        #         source=MessageSource.LIFE,
        #         content="Send a warm one-minute check-in message to the user.",
        #         interval_seconds=10,
        #         repeat=True
        #     )
        # )
        #
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
                await logger.error(
                    "input_stop_failed",
                    "Input stop failed.",
                    context={"adapter": adapter.name},
                    error=exc,
                )

        for task in input_tasks:
            task.cancel()

        await asyncio.gather(*input_tasks, return_exceptions=True)
        # await redis_client.shutdown()
        orchestrator_task.cancel()
        await asyncio.gather(orchestrator_task, return_exceptions=True)
        await scheduler.stop()
        await webhook_runtime.stop()
        await output_dispatcher.stop()


def _build_outputs(
    *,
    enabled_outputs: list[str],
    discord_runtime: DiscordRuntime,
    discord_output_user_id: str,
    telegram_runtime: TelegramRuntime,
    telegram_output_chat_id: str,
    webhook_runtime: WebhookRuntime,
    webhook_tts: EdgeTtsAdapter,
    webhook_output_targets: list[str],
    webhook_output_token: str | None,
) -> list[OutputAdapter]:
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

    return outputs


def _build_inputs(
    *,
    enabled_inputs: list[str],
    bus: MessageBus,
    discord_runtime: DiscordRuntime,
    telegram_runtime: TelegramRuntime,
    webhook_runtime: WebhookRuntime,
    groq_api_key: str,
) -> list[InputAdapter]:
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

    return inputs


def main() -> None:
    asyncio.run(_main())


async def _seed_life_profile_if_empty(state: RedisStateStore) -> None:
    profile_path = str(os.getenv("LIFE_PROFILE_FILE", "")).strip()
    if not profile_path:
        return

    profile_text = _read_profile_file(profile_path)
    if not profile_text:
        return

    thread_id = str(os.getenv("FORCE_THREAD_ID", "")).strip() or "global"
    existing_profile = await state.get_life_profile(thread_id)
    if existing_profile:
        return

    await state.replace_life_profile(thread_id, profile_text)


def _read_profile_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except Exception:
        return ""


if __name__ == "__main__":
    main()
