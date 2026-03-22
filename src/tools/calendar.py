from __future__ import annotations

from typing import Any

from langchain_google_community import CalendarToolkit
from langchain_google_community.calendar.create_event import CalendarCreateEvent
from langchain_google_community.calendar.current_datetime import GetCurrentDatetime
from langchain_google_community.calendar.get_calendars_info import GetCalendarsInfo
from langchain_google_community.calendar.search_events import CalendarSearchEvents
from langchain_google_community.calendar.utils import build_calendar_service
from langchain_google_community.gmail.utils import get_google_credentials

_calendar_needed = [
    CalendarCreateEvent,
    CalendarSearchEvents,
    GetCalendarsInfo,
    GetCurrentDatetime,
]

_cached_credentials: Any | None = None


def _get_credentials() -> Any | None:
    global _cached_credentials
    if _cached_credentials is None:
        try:
            _cached_credentials = get_google_credentials(
                token_file="calender.token.json",
                scopes=[
                    "https://www.googleapis.com/auth/calendar",
                ],
                client_secrets_file="credentials.json",
            )
        except Exception:
            return None
    return _cached_credentials


def CalendarTools() -> list:
    credentials = _get_credentials()
    if credentials is None:
        return []
    try:
        api_resource = build_calendar_service(
            credentials=credentials
        )
    except Exception:
        return []

    try:
        toolkit = CalendarToolkit(api_resource=api_resource)
        return _select_tools(toolkit.get_tools(), _calendar_needed)
    except Exception:
        return []


def _select_tools(tools: list[Any], needed: list[type[Any]]) -> list[Any]:
    selected: list[Any] = []
    for needed_type in needed:
        for tool in tools:
            if isinstance(tool, needed_type):
                selected.append(tool)
                break
    return selected
