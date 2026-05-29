"""Shared types, models, and protocols for Kayori."""

from shared_types.models import (
    EMOTIONS,
    FAST_EMOTIONS,
    LONG_EMOTIONS,
    MOOD_NEUTRAL,
    MessageEnvelope,
    MessageSource,
    MoodState,
    OutboundMessage,
    LifeNote,
    InteractionState,
    MessagesHistory,
    Todo,
)
from shared_types.protocol import (
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
from shared_types.tool_schemas import (
    ReminderToolArgs,
    SpotifyToolArgs,
    TodoToolArgs,
    UserDeviceToolArgs,
    WeatherToolArgs,
    WebExtractToolArgs,
    WebSearchToolArgs,
)
from shared_types.types import (
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
    "MoodState",
    "LifeNote",
    "InteractionState",
    "Todo",
    "EMOTIONS",
    "FAST_EMOTIONS",
    "LONG_EMOTIONS",
    "MOOD_NEUTRAL",

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
    "TodoToolArgs",
    "WebSearchToolArgs",
    "WebExtractToolArgs",
]
