from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from langchain_groq import ChatGroq

from redis.asyncio import Redis as AsyncRedis
from redis import Redis as SyncRedis

from gateway.audio.stt import WhisperSttAdapter
from gateway.audio.tts import EdgeTtsAdapter
from gateway.bus.redis_bus import RedisMessageBus
from gateway.http.dashboard import register_dashboard_routes
from gateway.http.logs import register_logs_routes
from gateway.http.metrics import register_metrics_routes
from gateway.platforms.discord import DiscordInputAdapter, DiscordOutputAdapter, DiscordRuntime
from gateway.platforms.telegram import TelegramInputAdapter, TelegramOutputAdapter, TelegramRuntime
from gateway.platforms.webhook import WebhookInputAdapter, WebhookOutputAdapter, WebhookRuntime
from gateway.memory.redis import RedisEpisodicMemory
from gateway.scheduler.redis import RedisSchedulerBackend
from gateway.state.redis import RedisStateStore
from agent.chat.service import ReactAgentService
from agent.life.service import LifeAgentService
from config.settings import KayoriConfig
from config.exceptions import ConfigError
from config.logging import get_logger
from agent.orchestration import (
    AgentOrchestrator,
    MoodEngine,
    OutputSink,
)
from agent.memory import (
    ConversationContractionService,
    EpisodicMemoryStore,
)
from gateway.scheduler.service import AgentScheduler
from shared_types import MessageSource, Trigger, TriggerType
from tools import registry as tool_registry

logger = get_logger("main")


async def _main() -> None:
    load_dotenv()
    config = KayoriConfig.from_env()
    config.raise_if_invalid()

    if config.primary_chat_app == "discord":
        discord_runtime = DiscordRuntime(token=config.discord_token)
        telegram_runtime = None
    else:
        discord_runtime = None
        telegram_runtime = TelegramRuntime(token=config.telegram_token)

    webhook_runtime = WebhookRuntime(
        host=config.webhook_host,
        port=config.webhook_port,
        bearer_token=config.webhook_bearer_token,
    )

    async_redis = AsyncRedis.from_url(config.redis_url)
    sync_redis = SyncRedis.from_url(config.redis_url)
    bus = RedisMessageBus(async_redis)
    state = RedisStateStore(async_redis)

    from langchain_community.embeddings import FastEmbedEmbeddings

    embedding_model = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    memory_backend = RedisEpisodicMemory(redis_client=sync_redis, embedding=embedding_model)
    episodic_memory = EpisodicMemoryStore(backend=memory_backend)

    scheduler_backend = RedisSchedulerBackend(redis_client=async_redis)
    scheduler = AgentScheduler(backend=scheduler_backend, bus=bus)

    stt_adapter = WhisperSttAdapter(api_key=config.groq_api_key)
    webhook_tts = EdgeTtsAdapter(api_key=config.tts_api_key, base_url=config.tts_base_url)

    # ── Output adapters ──
    outputs: list = []
    if config.primary_chat_app == "discord":
        outputs.append(
            DiscordOutputAdapter(
                runtime=discord_runtime,  # type: ignore[arg-type]
                default_channel_id=None,
                default_user_id=config.discord_user_id,
            )
        )
    else:
        outputs.append(
            TelegramOutputAdapter(
                runtime=telegram_runtime,  # type: ignore[arg-type]
                default_chat_id=config.telegram_chat_id,
            )
        )
    outputs.append(
        WebhookOutputAdapter(
            targets=config.webhook_output_targets,
            runtime=webhook_runtime,
            bearer_token=config.webhook_output_token or None,
        )
    )
    output_dispatcher = OutputSink(outputs=outputs, mode=config.output_sink_mode)

    # ── Tools ──
    tool_registry.discover()
    tools = tool_registry.get_tools(
        output=output_dispatcher,
        state_store=state,
        api_key=config.groq_api_key,
    )
    # ── Models ──
    chat_model = ChatGroq(
        model=config.groq_chat_model,
        temperature=0.6,
        api_key=config.groq_api_key,
    )
    life_model = ChatGroq(
        model=config.groq_life_model,
        temperature=0.7,
        api_key=config.groq_api_key,
    )

    # ── Services ──
    agent = ReactAgentService(model=chat_model, tools=tools)
    life_agent = LifeAgentService(model=life_model, tools=tools)
    mood_engine = MoodEngine(model=life_model)
    conversation_contraction = ConversationContractionService(model=life_model)

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
        stt=stt_adapter,
        tts=webhook_tts,
    )

    # ── Input adapters ──
    inputs: list = []
    if config.primary_chat_app == "discord":
        inputs.append(DiscordInputAdapter(runtime=discord_runtime, bus=bus))  # type: ignore[arg-type]
    else:
        inputs.append(
            TelegramInputAdapter(runtime=telegram_runtime, bus=bus, allowed_chat_ids=None)  # type: ignore[arg-type]
        )
    inputs.append(WebhookInputAdapter(runtime=webhook_runtime, bus=bus))

    for adapter in inputs:
        if hasattr(adapter, "register_routes"):
            adapter.register_routes()

    # ── Start ──
    orchestrator_task = asyncio.create_task(orchestrator.run(), name="orchestrator")
    input_tasks: list[asyncio.Task[None]] = []

    await output_dispatcher.start()
    await _seed_life_profile(state, config.life_profile_file)
    await _seed_proactive_route(state, config)
    register_dashboard_routes(webhook_runtime)
    register_logs_routes(webhook_runtime)
    register_metrics_routes(webhook_runtime, state)

    await webhook_runtime.start()
    await scheduler.start()

    try:
        await scheduler.push(
            Trigger(
                trigger_type=TriggerType.PRECISE,
                source=MessageSource.LIFE,
                interval_seconds=60 * 60 * 12,
                repeat=True,
            )
        )
        await scheduler.push(
            Trigger(
                trigger_type=TriggerType.PRECISE,
                source=MessageSource.PROACTIVE,
                interval_seconds=10,
                repeat=True,
            )
        )

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
                await logger.error("input_stop_failed", "Input stop failed.",
                                   context={"adapter": adapter.name}, error=exc)

        for task in input_tasks:
            task.cancel()
        await asyncio.gather(*input_tasks, return_exceptions=True)

        orchestrator_task.cancel()
        await asyncio.gather(orchestrator_task, return_exceptions=True)
        await scheduler.stop()
        await webhook_runtime.stop()
        await output_dispatcher.stop()


async def _seed_life_profile(state, profile_path: str) -> None:
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


async def _seed_proactive_route(state, config: KayoriConfig) -> None:
    interaction = await state.get_interaction_state()
    if interaction.route_source:
        return
    if config.primary_chat_app == "discord":
        interaction.route_source = "discord"
        interaction.route_target_user_id = config.discord_user_id or None
    else:
        interaction.route_source = "telegram"
        interaction.route_target_user_id = config.telegram_chat_id or None
    interaction.route_channel_id = None
    await state.set_interaction_state(interaction)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
