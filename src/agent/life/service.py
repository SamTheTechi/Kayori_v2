from __future__ import annotations

from langchain_core.language_models import BaseChatModel


class LifeAgentService:
    def __init__(
        self,
        *,
        model: BaseChatModel,
        timeout_seconds: int = 60,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
