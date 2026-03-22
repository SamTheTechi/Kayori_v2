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
    EpisodicMemoryStore,
    # GraphMemoryStore,
    InputAdapter,
    MessageBus,
    OutputAdapter,
    SchedulerStore,
    SchedulerBackend,
    StateStore,
    # ToolAuditLogger,
    TriggerSchedulerBackend,
)
from src.shared_types.tool_schemas import (
    ReminderToolArgs,
    SpotifyToolArgs,
    UserDeviceToolArgs,
    WeatherToolArgs,
)
from src.shared_types.types import (
    AgentGraphState,
    FiredTrigger,
    MissedPolicy,
    MoodDirection,
    OutputSinkMode,
    ScheduledTask,
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
    "EpisodicMemoryStore",
    "GraphMemoryStore",
    "SchedulerStore",
    "TriggerSchedulerBackend",

    # Types
    "AgentGraphState",
    "Trigger",
    "FiredTrigger",
    "TriggerType",
    "MissedPolicy",
    "MoodDirection",
    "SchedulerBackend",
    # "ToolAuditEvent",
    "ScheduledTask",
    "OutputSinkMode",

    # Tool Args
    "WeatherToolArgs",
    "ReminderToolArgs",
    "UserDeviceToolArgs",
    "SpotifyToolArgs",
]
