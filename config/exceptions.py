from __future__ import annotations


class KayoriError(Exception):
    """Base for all Kayori-agent errors."""


class ConfigError(KayoriError):
    """Missing or invalid configuration."""


class MissingRequiredConfig(ConfigError):
    """A required env var or config field is missing."""


class AdapterError(KayoriError):
    """Adapter-level I/O failure."""


class BusError(AdapterError):
    """Message bus publish/consume failure."""


class StateError(AdapterError):
    """State store read/write failure."""


class ProviderError(KayoriError):
    """LLM provider call failure."""


class ProviderTimeout(ProviderError):
    """Provider call timed out."""


class ProviderUnavailable(ProviderError):
    """Provider is down, unreachable, or misconfigured."""


class ToolError(KayoriError):
    """Tool execution failure."""


class ToolNotFound(ToolError):
    """No tool registered with this name."""


class AgentError(KayoriError):
    """Agent loop failure."""


class AgentTimeout(AgentError):
    """Agent exceeded max iterations or wall-clock timeout."""
