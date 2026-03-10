"""Kayori v2 - Async, adapter-based AI companion built around LangGraph."""

from agent.service import ReactAgentService
from core.orchestrator import AgentOrchestrator
from core.outputsink import OutputSink
from shared_types.models import (
    MessageEnvelope,
    MessageSource,
    MoodState,
    OutboundMessage,
)
from shared_types.protocol import (
    InputAdapter,
    MessageBus,
    OutputAdapter,
    StateStore,
)

__version__ = "0.1.0"
__all__ = [
    "AgentOrchestrator",
    "OutputSink",
    "ReactAgentService",
    "MessageEnvelope",
    "OutboundMessage",
    "MessageSource",
    "MoodState",
    "MessageBus",
    "InputAdapter",
    "OutputAdapter",
    "StateStore",
]
