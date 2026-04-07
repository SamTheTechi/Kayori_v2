import asyncio
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_tavily import TavilySearch
from langchain_groq import ChatGroq
from langchain_community.embeddings import FastEmbedEmbeddings

from redis.asyncio import Redis as AsyncRedis
from redis import Redis as SyncRedis

from src.adapters.audio.stt import WhisperSttAdapter
from src.adapters.http.dashboard import register_dashboard_routes
from src.adapters.http.logs import register_logs_routes
from src.adapters.http.metrics import register_metrics_routes
from src.adapters.http.ping import register_ping_routes
from src.adapters.audio.tts import EdgeTtsAdapter
from src.adapters.bus.redis_bus import RedisMessageBus
from src.adapters.input.discord_input import DiscordInputAdapter
from src.adapters.input.telegram_input import TelegramInputAdapter
from src.adapters.input.webhook_input import WebhookInputAdapter
from src.adapters.output.discord_output import DiscordOutputAdapter
from src.adapters.output.telegram_output import TelegramOutputAdapter
from src.adapters.output.webhook_output import WebhookOutputAdapter
from src.adapters.runtime.discord_runtime import DiscordRuntime
from src.adapters.runtime.telegram_runtime import TelegramRuntime
from src.adapters.runtime.webhook_runtime import WebhookRuntime
from src.adapters.state.redis import RedisStateStore
from src.adapters.memory.redis import RedisEpisodicMemory
from src.agent.chat.service import ReactAgentService
from src.agent.life.service import LifeAgentService
from src.core.mood_engine import MoodEngine
from src.core.episodic_memory import EpisodicMemoryStore
from src.core.orchestrator import AgentOrchestrator
from src.core.outputsink import OutputSink
from src.core.conversation_contraction import ConversationContractionService
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
PrimaryChatApp = Literal["discord", "telegram"]
PRIMARY_CHAT_APPS: tuple[PrimaryChatApp, ...] = ("discord", "telegram")


async def _main() -> None:
    load_dotenv()
    primary_chat_app = _resolve_primary_chat_app()
    output_sink_mode = _resolve_output_sink_mode()

    # Runtime configuration.
    discord_token = os.getenv("DISCORD_BOT_TOKEN", "")
    discord_output_user_id = os.getenv("DISCORD_USER_ID", "")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_output_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    groq_api_key = str(os.getenv("API_KEY", "")).strip()
    redis_url = str(os.getenv("REDIS_URL", "redis://localhost:6379")
                    ).strip() or "redis://localhost:6379"

    webhook_bearer_token = (
        str(os.getenv("WEBHOOK_BEARER_TOKEN", "")).strip() or "123"
    )
    webhook_host = (
        str(os.getenv("WEBHOOK_SERVER_HOST", "0.0.0.0")).strip() or "0.0.0.0"
    )
    webhook_port = int(
        str(os.getenv("WEBHOOK_SERVER_PORT", "8080")).strip() or "8080"
    )
    tts_base_url = (
        str(os.getenv("EDGE_TTS_BASE_URL", "http://localhost:5050/v1")).strip()
        or "http://localhost:5050/v1"
    )
    tts_api_key = (
        str(os.getenv("EDGE_TTS_API_KEY", "123")).strip() or "123"
    )

    webhook_output_targets = [
        item.strip()
        for item in str(os.getenv("WEBHOOK_OUTPUT_URLS", "")).split(",")
        if item.strip()
    ]
    webhook_output_token = (
        str(os.getenv("WEBHOOK_OUTPUT_BEARER_TOKEN", "")).strip() or None
    )

    if primary_chat_app == "discord" and not discord_token.strip():
        raise RuntimeError("DISCORD_BOT_TOKEN is required when PRIMARY_CHAT_APP=discord.")
    if primary_chat_app == "telegram" and not telegram_token.strip():
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required when PRIMARY_CHAT_APP=telegram.")

    discord_runtime = (
        DiscordRuntime(token=discord_token)
        if primary_chat_app == "discord"
        else None
    )
    telegram_runtime = (
        TelegramRuntime(token=telegram_token)
        if primary_chat_app == "telegram"
        else None
    )
    webhook_runtime = WebhookRuntime(
        host=webhook_host,
        port=webhook_port,
        bearer_token=webhook_bearer_token,
    )

    async_redis = AsyncRedis.from_url(redis_url)
    sync_redis = SyncRedis.from_url(redis_url)
    bus = RedisMessageBus(async_redis)
    state = RedisStateStore(async_redis)

    await _seed_life_profile_if_empty(state)

    embedding_model = FastEmbedEmbeddings(
        model_name="BAAI/bge-small-en-v1.5"
    )

    memory_backend = RedisEpisodicMemory(
        redis_client=sync_redis, embedding=embedding_model)
    episodic_memory = EpisodicMemoryStore(backend=memory_backend)

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
        primary_chat_app=primary_chat_app,
        discord_runtime=discord_runtime,
        discord_output_user_id=discord_output_user_id,
        telegram_runtime=telegram_runtime,
        telegram_output_chat_id=telegram_output_chat_id,
        webhook_runtime=webhook_runtime,
        webhook_tts=webhook_tts,
        webhook_output_targets=webhook_output_targets,
        webhook_output_token=webhook_output_token,
    )

    output_dispatcher = OutputSink(outputs=outputs, mode=output_sink_mode)

    # Agent tools.
    tools = [
        ReminderTool(output=output_dispatcher),
        LifeInfoTool(state_store=state),
        SpotifyTool(),
        TavilySearch(max_results=3, topic="general"),
    ]
    tools.extend(CalendarTools())

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
        tools=[TavilySearch(max_results=3, topic="general")],
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
        primary_chat_app=primary_chat_app,
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
    register_dashboard_routes(webhook_runtime)
    register_ping_routes(webhook_runtime)
    register_logs_routes(webhook_runtime)
    register_metrics_routes(webhook_runtime, state)
    await webhook_runtime.start()
    await scheduler.start()

    try:
        await scheduler.push(
            Trigger(
                trigger_type=TriggerType.PRECISE,
                source=MessageSource.LIFE,
                interval_seconds=20,
                repeat=True
            )
        )
        await scheduler.push(
            Trigger(
                trigger_type=TriggerType.FUZZY,
                source=MessageSource.PROACTIVE,
                interval_seconds=60 * 60 * 4,
                fuzzy_seconds=60 * 60 * 2,
                repeat=True
            )
        )

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
    primary_chat_app: PrimaryChatApp,
    discord_runtime: DiscordRuntime | None,
    discord_output_user_id: str,
    telegram_runtime: TelegramRuntime | None,
    telegram_output_chat_id: str,
    webhook_runtime: WebhookRuntime,
    webhook_tts: EdgeTtsAdapter,
    webhook_output_targets: list[str],
    webhook_output_token: str | None,
) -> list[OutputAdapter]:
    return [
        _build_primary_output(
            primary_chat_app=primary_chat_app,
            discord_runtime=discord_runtime,
            discord_output_user_id=discord_output_user_id,
            telegram_runtime=telegram_runtime,
            telegram_output_chat_id=telegram_output_chat_id,
        ),
        WebhookOutputAdapter(
            targets=webhook_output_targets,
            runtime=webhook_runtime,
            tts=webhook_tts,
            bearer_token=webhook_output_token,
        ),
    ]


def _build_inputs(
    *,
    primary_chat_app: PrimaryChatApp,
    bus: MessageBus,
    discord_runtime: DiscordRuntime | None,
    telegram_runtime: TelegramRuntime | None,
    webhook_runtime: WebhookRuntime,
    groq_api_key: str,
) -> list[InputAdapter]:
    return [
        _build_primary_input(
            primary_chat_app=primary_chat_app,
            bus=bus,
            discord_runtime=discord_runtime,
            telegram_runtime=telegram_runtime,
        ),
        WebhookInputAdapter(
            runtime=webhook_runtime,
            bus=bus,
            stt=WhisperSttAdapter(api_key=groq_api_key),
        ),
    ]


def _build_primary_output(
    *,
    primary_chat_app: PrimaryChatApp,
    discord_runtime: DiscordRuntime | None,
    discord_output_user_id: str,
    telegram_runtime: TelegramRuntime | None,
    telegram_output_chat_id: str,
) -> OutputAdapter:
    if primary_chat_app == "discord":
        if discord_runtime is None:
            raise RuntimeError("Discord runtime is required for Discord output.")
        return DiscordOutputAdapter(
            runtime=discord_runtime,
            default_channel_id=None,
            default_user_id=discord_output_user_id,
        )

    if telegram_runtime is None:
        raise RuntimeError("Telegram runtime is required for Telegram output.")
    return TelegramOutputAdapter(
        runtime=telegram_runtime,
        default_chat_id=telegram_output_chat_id,
    )


def _build_primary_input(
    *,
    primary_chat_app: PrimaryChatApp,
    bus: MessageBus,
    discord_runtime: DiscordRuntime | None,
    telegram_runtime: TelegramRuntime | None,
) -> InputAdapter:
    if primary_chat_app == "discord":
        if discord_runtime is None:
            raise RuntimeError("Discord runtime is required for Discord input.")
        return DiscordInputAdapter(runtime=discord_runtime, bus=bus)

    if telegram_runtime is None:
        raise RuntimeError("Telegram runtime is required for Telegram input.")
    return TelegramInputAdapter(
        runtime=telegram_runtime,
        bus=bus,
        allowed_chat_ids=None,
    )


def _resolve_primary_chat_app() -> PrimaryChatApp:
    value = str(os.getenv("PRIMARY_CHAT_APP", "discord")).strip().lower()
    if value not in PRIMARY_CHAT_APPS:
        raise RuntimeError(
            "PRIMARY_CHAT_APP must be either 'discord' or 'telegram'."
        )
    return value


def _resolve_output_sink_mode() -> Literal["direct", "multi"]:
    value = str(os.getenv("OUTPUT_SINK_MODE", "direct")).strip().lower()
    if value not in {"direct", "multi"}:
        raise RuntimeError("OUTPUT_SINK_MODE must be either 'direct' or 'multi'.")
    return value  # type: ignore[return-value]


def main() -> None:
    asyncio.run(_main())


async def _seed_life_profile_if_empty(state: RedisStateStore) -> None:
    profile_path = str(os.getenv("LIFE_PROFILE_FILE", "")).strip()
    if not profile_path:
        return

    try:
        profile_text = Path(profile_path).read_text(encoding="utf-8").strip()
    except Exception:
        return

    if not profile_text:
        return

    if await state.get_life_profile():
        return

    await state.replace_life_profile(profile_text)


if __name__ == "__main__":
    main()
