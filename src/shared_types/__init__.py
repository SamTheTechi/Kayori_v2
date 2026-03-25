"""Shared types, models, and protocols for Kayori."""

from src.shared_types.models import (
    EMOTIONS,
    MOOD_NEUTRAL,
    MessageEnvelope,
    MessageSource,
    MoodState,
    OutboundMessage,
)
from src.shared_types.thread_identity import resolve_thread_id
from src.shared_types.protocol import (
    EpisodicMemoryBackend,
    EpisodicMemoryBackendRecord,
    EpisodicMemorySearchResult,
    EpisodicMemoryStore,
    InputAdapter,
    MessageBus,
    OutputAdapter,
    SchedulerBackend,
    StateStore,
    # ToolAuditLogger,
)
from src.shared_types.tool_schemas import (
    ReminderToolArgs,
    SpotifyToolArgs,
    UserDeviceToolArgs,
    WeatherToolArgs,
)
from src.shared_types.types import (
    AgentGraphState,
    OutputSinkMode,
    Trigger,
    TriggerType,
)

__all__ = [
    # Models
    "MessageEnvelope",
    "OutboundMessage",
    "MessageSource",
    # "MessageAttachment",
    # "MoodState",
    # "LocationState",
    "EMOTIONS",
    "MOOD_NEUTRAL",
    "resolve_thread_id",

    # Protocols
    "MessageBus",
    "InputAdapter",
    "OutputAdapter",
    "StateStore",
    # "ToolAuditLogger",
    "EpisodicMemoryBackend",
    "EpisodicMemoryBackendRecord",
    "EpisodicMemorySearchResult",
    "EpisodicMemoryStore",

    # Types
    "AgentGraphState",
    "Trigger",
    "TriggerType",
    "SchedulerBackend",
    # "ToolAuditEvent",
    "OutputSinkMode",

    # Tool Args
    "WeatherToolArgs",
    "ReminderToolArgs",
    "UserDeviceToolArgs",
    "SpotifyToolArgs",
]
