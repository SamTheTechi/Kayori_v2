from __future__ import annotations

from typing import Any

from langchain_google_community import CalendarToolkit, GmailToolkit
from langchain_google_community.calendar.create_event import CalendarCreateEvent
from langchain_google_community.calendar.current_datetime import GetCurrentDatetime
from langchain_google_community.calendar.get_calendars_info import GetCalendarsInfo
from langchain_google_community.calendar.search_events import CalendarSearchEvents
from langchain_google_community.gmail.get_message import GmailGetMessage
from langchain_google_community.gmail.get_thread import GmailGetThread
from langchain_google_community.gmail.search import GmailSearch
from langchain_google_community.gmail.utils import (
    build_resource_service,
    get_google_credentials,
)

_gmail_needed = [GmailSearch, GmailGetMessage, GmailGetThread]

_calendar_needed = [
    CalendarCreateEvent,
    CalendarSearchEvents,
    GetCalendarsInfo,
    GetCurrentDatetime,
]

_cached_credentials: Any | None = None
_cached_api_resource: Any | None = None
_cached_gmail_tools: list | None = None
_cached_calendar_tools: list | None = None


def _get_credentials() -> Any | None:
    global _cached_credentials
    if _cached_credentials is None:
        try:
            _cached_credentials = get_google_credentials(
                token_file="token.json",
                scopes=[
                    "https://mail.google.com/",
                    "https://www.googleapis.com/auth/calendar",
                ],
                client_secrets_file="../../credentials.json",
            )
        except Exception:
            return None
    return _cached_credentials


def _get_api_resource() -> Any | None:
    global _cached_api_resource
    if _cached_api_resource is None:
        credentials = _get_credentials()
        if credentials is None:
            return None
        try:
            _cached_api_resource = build_resource_service(credentials=credentials)
        except Exception:
            return None
    return _cached_api_resource


def GmailTools() -> list:
    global _cached_gmail_tools
    if _cached_gmail_tools is None:
        api_resource = _get_api_resource()
        if api_resource is None:
            return []
        try:
            toolkit = GmailToolkit(api_resource=api_resource)
            _cached_gmail_tools = toolkit.get_tools()
        except Exception:
            return []
    return _cached_gmail_tools


def CalendarTools() -> list:
    global _cached_calendar_tools
    if _cached_calendar_tools is None:
        api_resource = _get_api_resource()
        if api_resource is None:
            return []
        try:
            toolkit = CalendarToolkit(api_resource=api_resource)
            _cached_calendar_tools = toolkit.get_tools()
        except Exception:
            return []
    return _cached_calendar_tools
