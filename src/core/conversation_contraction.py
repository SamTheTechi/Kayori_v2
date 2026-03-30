from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage

from src.logger import get_logger
from src.shared_types.protocol import EpisodicMemoryStore, StateStore
from src.templates.episodic_strength_template import episodic_strength_template

COMPACT_THRESHOLD = 12
COMPACT_KEEP_RECENT = 4
COMPACTED_KEY = "kayori_compacted"

FACT_CATEGORIES = {
    "identity",
    "preference",
    "relationship",
    "profile",
    "schedule",
    "goal",
    "possession",
    "misc",
}

logger = get_logger("core.contraction")


class ConversationContractionService:
    def __init__(
        self,
        *,
        model: BaseChatModel,
        timeout_seconds: float = 5,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.model = model

    async def maybe_compact(
        self,
        *,
        thread_id: str,
        state_store: StateStore,
        episodic_memory: EpisodicMemoryStore,
    ) -> None:
        if await state_store.history_len(thread_id) <= COMPACT_THRESHOLD:
            return
        await self.compact(
            thread_id=thread_id,
            state_store=state_store,
            episodic_memory=episodic_memory,
        )

    async def compact(
        self,
        *,
        thread_id: str,
        state_store: StateStore,
        episodic_memory: EpisodicMemoryStore,
    ) -> None:
        history = await state_store.get_history(thread_id)
        messages = history.all()

        existing_summary = ""
        raw_messages = list(messages)
        if raw_messages and self._is_compacted_summary(raw_messages[0]):
            existing_summary = str(raw_messages[0].content or "").strip()
            raw_messages = raw_messages[1:]

        if len(raw_messages) <= COMPACT_KEEP_RECENT:
            return

        messages_to_compact = raw_messages[:-COMPACT_KEEP_RECENT]
        recent_messages = raw_messages[-COMPACT_KEEP_RECENT:]
        if not messages_to_compact:
            return

        summary, facts = await self._contract_messages(
            messages=messages_to_compact,
            existing_summary=existing_summary,
        )
        summary = summary.strip()
        if not summary:
            return

        for fact in facts:
            await episodic_memory.remember(
                thread_id=thread_id,
                fact=str(fact.get("fact") or ""),
                source=str(fact.get("source") or "conversation"),
                category=str(fact.get("category") or "misc"),
                importance=int(fact.get("importance", 3) or 3),
                confidence=float(fact.get("confidence", 0.8) or 0.8),
                tags=list(fact.get("tags") or []),
                context=str(fact.get("context") or ""),
            )

        await state_store.replace_messages(
            thread_id,
            [
                SystemMessage(
                    content=summary,
                    additional_kwargs={COMPACTED_KEY: True},
                ),
                *recent_messages,
            ],
        )

    async def _contract_messages(
        self,
        messages: list[BaseMessage],
        existing_summary: str = "",
    ) -> tuple[str, list[dict[str, Any]]]:
        if not messages:
            return "", []

        msg = "\n".join(
            f"{self._message_role(message)}: {message.content}"
            for message in messages
            if str(message.content or "").strip()
        ) or "None."

        prompt_messages = episodic_strength_template.format_messages(
            existing_summary=self._clean_text(
                existing_summary, 4000) or "None.",
            messages=msg,
        )

        try:
            result = await asyncio.wait_for(
                self.model.ainvoke(prompt_messages),
                timeout=max(0.05, float(self.timeout_seconds)),
            )
        except Exception as exc:
            await logger.error(
                "contraction_failed",
                "Conversation contraction failed.",
                context={
                    "timeout_seconds": float(self.timeout_seconds),
                    "message_count": len(messages),
                },
                error=exc,
            )
            return "", []

        raw_text = self._clean_text(getattr(result, "content", result))
        if not raw_text:
            return "", []

        try:
            data = json.loads(raw_text)
        except Exception as exc:
            await logger.warning(
                "conversation_contraction_parse_failed",
                "Conversation contraction response was not valid JSON.",
                context={
                    "message_count": len(messages),
                    "raw_text_length": len(raw_text),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            return "", []

        if not isinstance(data, dict):
            return "", []

        facts = [
            fact for fact in (
                self._normalize_fact(item)
                for item in (data.get("facts") or [])
                if isinstance(item, dict)
            )
            if fact
        ]
        return self._clean_text(data.get("summary")), facts

    def _normalize_fact(self, fact: dict[str, Any]) -> dict[str, Any] | None:
        fact_text = self._clean_text(fact.get("fact"), 600)
        if not fact_text:
            return None

        category = self._clean_text(fact.get("category"), 40).lower() or "misc"
        category = category if category in FACT_CATEGORIES else "misc"

        raw_tags = fact.get("tags") or []
        if isinstance(raw_tags, str):
            raw_tags = [part.strip() for part in raw_tags.split(",")]
        tags = list(
            dict.fromkeys(
                value
                for tag in raw_tags
                if (value := self._clean_text(tag, 40).lower())
            )
        )

        return {
            "fact": fact_text,
            "source": self._clean_text(fact.get("source") or "conversation", 80) or "conversation",
            "category": category,
            "importance": max(1, min(5, int(fact.get("importance", 3) or 3))),
            "confidence": max(0.0, min(1.0, float(fact.get("confidence", 0.8) or 0.8))),
            "tags": tags,
            "context": self._clean_text(fact.get("context"), 600),
        }

    def _clean_text(self, value: Any, max_len: int = 2000) -> str:
        text = " ".join(str(value or "").strip().split())
        if len(text) <= max_len:
            return text
        return f"{text[: max_len - 3]}..."

    def _message_role(self, message: BaseMessage) -> str:
        if self._is_compacted_summary(message):
            return "system"
        if message.type == "human":
            return "user"
        if message.type == "ai":
            return "assistant"
        if message.type == "system":
            return "system"
        return "assistant"

    def _is_compacted_summary(self, message: BaseMessage) -> bool:
        return bool(getattr(message, "additional_kwargs", {}).get(COMPACTED_KEY))


__all__ = ["ConversationContractionService"]
