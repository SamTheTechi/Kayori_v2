from __future__ import annotations

from typing import Sequence

from langchain_core.tools import BaseTool

CALENDAR_SETUP_ERROR = (
    "Google Calendar tools are unavailable. Configure Google credentials for "
    "langchain_google_community CalendarToolkit before enabling them."
)


def get_calendar_tools() -> list[BaseTool]:
    """Build Google Calendar tools lazily.

    Keeping toolkit creation inside this function avoids import-time side effects
    and lets callers decide whether calendar integration should be enabled.
    """
    try:
        from langchain_google_community import CalendarToolkit
    except Exception as exc:
        raise RuntimeError(CALENDAR_SETUP_ERROR) from exc

    try:
        toolkit = CalendarToolkit()
        tools = list(toolkit.get_tools())
    except Exception as exc:
        raise RuntimeError(CALENDAR_SETUP_ERROR) from exc

    if not tools:
        raise RuntimeError(
            "Google Calendar toolkit did not provide any tools.")
    return tools


def get_calendar_tool_names() -> Sequence[str]:
    return tuple(tool.name for tool in get_calendar_tools())


__all__ = [
    "CALENDAR_SETUP_ERROR",
    "get_calendar_tool_names",
    "get_calendar_tools",
]
