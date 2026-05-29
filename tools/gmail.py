from __future__ import annotations

from typing import Any

from langchain_google_community import GmailToolkit
from langchain_google_community.gmail.get_message import GmailGetMessage
from langchain_google_community.gmail.get_thread import GmailGetThread
from langchain_google_community.gmail.search import GmailSearch
from langchain_google_community.gmail.utils import (
    build_gmail_service,
    get_google_credentials,
)

_gmail_needed = [GmailSearch, GmailGetMessage, GmailGetThread]

_cached_credentials: Any | None = None


def _get_credentials() -> Any | None:
    global _cached_credentials
    if _cached_credentials is None:
        try:
            _cached_credentials = get_google_credentials(
                token_file="gmail.token.json",
                scopes=[
                    "https://mail.google.com/",
                ],
                client_secrets_file="credentials.json",
            )
        except Exception:
            return None
    return _cached_credentials


def GmailTools() -> list:

    credentials = _get_credentials()
    if credentials is None:
        return []
    try:
        api_resource = build_gmail_service(
            credentials=credentials
        )
    except Exception:
        return []

    try:
        toolkit = GmailToolkit(api_resource=api_resource)
        return _select_tools(toolkit.get_tools(), _gmail_needed)
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
