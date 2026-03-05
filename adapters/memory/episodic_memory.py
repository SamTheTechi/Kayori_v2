from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from langchain_groq import ChatGroq
from langchain_pinecone import PineconeEmbeddings, PineconeVectorStore
from pydantic import BaseModel, Field

from templates.episodic_strength_template import episodic_strength_template


class _StrengthPayload(BaseModel):
    strength: float = Field(
        description="memory strength score between 0 and 1")


@dataclass(slots=True, kw_only=True)
class EpisodicMemoryStore:
    vector_store: PineconeVectorStore
    namespace: str = "kayori-episodic"
    min_score_default: float = 0.35
    recent_cache_size: int = 200
    strength_model: str = "llama-3.1-8b-instant"
    strength_api_key: str | None = None
    fallback_from_salience: bool = True

    _recent_cache: deque[dict[str, Any]] = field(init=False, repr=False)
    _fallback_from_salience: bool = field(init=False, repr=False)
    _llm: ChatGroq | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.namespace = (self.namespace or "kayori-episodic").strip()
        self.min_score_default = self._clamp(
            self._to_float(self.min_score_default, 0.35), 0.0, 1.0)
        self._recent_cache = deque(maxlen=max(
            1, self._to_int(self.recent_cache_size, 200)))
        self._fallback_from_salience = self.fallback_from_salience

        key = (self.strength_api_key or os.getenv("API_KEY") or "").strip()
        model_name = (self.strength_model or "").strip()
        if key and model_name:
            self._llm = ChatGroq(
                model=model_name,
                temperature=0.3,
                api_key=key,
            )

    @classmethod
    def from_env(cls) -> "EpisodicMemoryStore":
        pinecone_api_key = (os.getenv("PINECONE_API_KEY") or "").strip()
        index_name = (os.getenv("PINECONE_INDEX_NAME")
                      or os.getenv("PINECONE_INDEX") or "").strip()
        host = (os.getenv("PINECONE_INDEX_HOST")
                or os.getenv("PINECONE_HOST") or "").strip()
        namespace = (os.getenv("PINECONE_NAMESPACE")
                     or "kayori-episodic").strip() or "kayori-episodic"
        embedding_model = (os.getenv("PINECONE_EMBEDDING_MODEL")
                           or "multilingual-e5-large").strip()

        if not pinecone_api_key:
            raise ValueError("PINECONE_API_KEY is required")
        if not index_name and not host:
            raise ValueError(
                "PINECONE_INDEX_NAME/PINECONE_INDEX or PINECONE_INDEX_HOST is required")

        embeddings = PineconeEmbeddings(
            model=embedding_model,
            pinecone_api_key=pinecone_api_key,
        )
        vector_store = PineconeVectorStore(
            embedding=embeddings,
            pinecone_api_key=pinecone_api_key,
            index_name=index_name or None,
            host=host or None,
            namespace=namespace,
        )

        return cls(
            vector_store=vector_store,
            namespace=namespace,
            min_score_default=cls._to_float(
                os.getenv("EPISODIC_RECALL_MIN_SCORE"), 0.35),
            recent_cache_size=cls._to_int(
                os.getenv("EPISODIC_RECENT_CACHE"), 200),
            strength_model=(os.getenv("MEMORY_STRENGTH_MODEL")
                            or "llama-3.1-8b-instant").strip(),
            strength_api_key=(os.getenv(
                "API_KEY") or "").strip() or None,
            strength_temperature=cls._to_float(
                os.getenv("MEMORY_STRENGTH_TEMPERATURE"), 0.0),
            fallback_from_salience=True,
        )

    def remember(
        self,
        *,
        event: str,
        source: str,
        salience: int = 3,
        emotion: str = "Neutral",
        tags: list[str] | None = None,
        context: str = "",
    ) -> dict[str, Any]:
        episode = self._build_episode(
            event=event,
            source=source,
            salience=salience,
            emotion=emotion,
            tags=tags,
            context=context,
            strength=0.5,
        )
        episode["strength"] = self._score_strength(episode)

        self.vector_store.add_texts(
            texts=[self._embedding_text(episode)],
            metadatas=[dict(episode)],
            ids=[str(episode["id"])],
            namespace=self.namespace,
            async_req=False,
        )
        self._recent_cache.append(dict(episode))
        return dict(episode)

    def recall(
        self,
        query: str,
        limit: int = 3,
        *,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        query_text = self._clean_text(query, 600)
        if not query_text:
            return []

        top_k = max(1, min(100, self._to_int(limit, 3)))
        threshold = self._clamp(
            self.min_score_default if min_score is None else float(min_score),
            0.0,
            1.0,
        )

        results = self.vector_store.similarity_search_with_score(
            query=query_text,
            k=max(top_k * 5, 20),
            namespace=self.namespace,
        )

        ranked: list[tuple[float, dict[str, Any]]] = []
        for doc, raw_score in results:
            metadata = dict(getattr(doc, "metadata", {}) or {})
            if not metadata:
                continue

            episode = self._episode_from_metadata(metadata)
            if episode is None:
                continue

            vector_score = self._normalize_vector_score(raw_score)
            final_score = vector_score * 0.8 + \
                self._clamp(self._to_float(episode.get(
                    "strength"), 0.0), 0.0, 1.0) * 0.2
            if final_score >= threshold:
                ranked.append((final_score, episode))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [dict(episode) for _, episode in ranked[:top_k]]

    def recent(self, limit: int = 5) -> list[dict[str, Any]]:
        top_k = max(1, min(100, self._to_int(limit, 5)))
        if not self._recent_cache:
            return []

        snapshot = [dict(item) for item in self._recent_cache]
        snapshot.sort(key=lambda episode: self._parse_ts(
            str(episode.get("timestamp", ""))), reverse=True)
        return snapshot[:top_k]

    def _score_strength(self, episode: dict[str, Any]) -> float:
        salience = max(1, min(5, self._to_int(episode.get("salience"), 3)))
        fallback = self._clamp(float(salience) / 5.0, 0.0, 1.0)

        if self._llm is None:
            if self._fallback_from_salience:
                return fallback
            raise ValueError("ChatGroq is not configured")

        prompt_messages = episodic_strength_template.format_messages(
            summary=episode.get("summary", ""),
            context=episode.get("context", ""),
            source=episode.get("source", ""),
            emotion=episode.get("emotion", "Neutral"),
            salience=salience,
        )

        try:
            structured = self._llm.with_structured_output(_StrengthPayload)
            payload = structured.invoke(prompt_messages)
            if isinstance(payload, _StrengthPayload):
                value = payload.strength
            else:
                value = float(payload["strength"])
            return self._clamp(self._to_float(value, fallback), 0.0, 1.0)
        except Exception:
            if self._fallback_from_salience:
                return fallback
            raise

    def _build_episode(
        self,
        *,
        event: str,
        source: str,
        salience: int,
        emotion: str,
        tags: list[str] | None,
        context: str,
        strength: float,
    ) -> dict[str, Any]:
        summary = self._clean_text(event, 600)
        if not summary:
            raise ValueError("event must be non-empty")

        return {
            "id": f"EP-{uuid4().hex[:10]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": self._clean_text(source or "unknown", 80) or "unknown",
            "salience": max(1, min(5, self._to_int(salience, 3))),
            "emotion": self._clean_text(emotion or "Neutral", 40) or "Neutral",
            "strength": self._clamp(self._to_float(strength, 0.5), 0.0, 1.0),
            "tags": self._normalize_tags(tags or []),
            "summary": summary,
            "context": self._clean_text(context, 600),
        }

    def _episode_from_metadata(self, metadata: dict[str, Any]) -> dict[str, Any] | None:
        try:
            episode_id = self._clean_text(metadata.get("id", ""), 80)
            if not episode_id:
                return None

            raw_tags = metadata.get("tags", [])
            if isinstance(raw_tags, str):
                tags = [part.strip()
                        for part in raw_tags.split(",") if part.strip()]
            elif isinstance(raw_tags, list) or isinstance(raw_tags, tuple) or isinstance(raw_tags, set):
                tags = [str(part).strip()
                        for part in raw_tags if str(part).strip()]
            else:
                tags = []

            return {
                "id": episode_id,
                "timestamp": self._clean_text(metadata.get("timestamp", datetime.now(timezone.utc).isoformat()), 80) or datetime.now(timezone.utc).isoformat(),
                "source": self._clean_text(metadata.get("source", "unknown"), 80) or "unknown",
                "salience": max(1, min(5, self._to_int(metadata.get("salience", 3), 3))),
                "emotion": self._clean_text(metadata.get("emotion", "Neutral"), 40) or "Neutral",
                "strength": self._clamp(self._to_float(metadata.get("strength", 0.5), 0.5), 0.0, 1.0),
                "tags": self._normalize_tags(tags),
                "summary": self._clean_text(metadata.get("summary", ""), 600),
                "context": self._clean_text(metadata.get("context", ""), 600),
            }
        except Exception:
            return None

    def _embedding_text(self, episode: dict[str, Any]) -> str:
        return "\n".join(
            [
                f"summary: {episode.get('summary', '')}",
                f"context: {episode.get('context', '')}",
                f"tags: {', '.join(episode.get('tags') or [])}",
                f"emotion: {episode.get('emotion', 'Neutral')}",
                f"source: {episode.get('source', 'unknown')}",
            ]
        )

    @staticmethod
    def _normalize_vector_score(score: float) -> float:
        value = EpisodicMemoryStore._to_float(score, 0.0)
        if 0.0 <= value <= 1.0:
            return value
        return EpisodicMemoryStore._clamp((value + 1.0) / 2.0, 0.0, 1.0)

    @staticmethod
    def _parse_ts(raw: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(raw))
        except Exception:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _to_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _normalize_spaces(value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @staticmethod
    def _clean_text(value: Any, max_len: int) -> str:
        text = EpisodicMemoryStore._normalize_spaces(value)
        if len(text) <= max_len:
            return text
        return f"{text[:max_len - 3]}..."

    @staticmethod
    def _normalize_tags(tags: list[str] | tuple[str, ...] | set[str]) -> list[str]:
        normalized = set()
        for tag in tags:
            text = EpisodicMemoryStore._normalize_spaces(tag)
            if text:
                normalized.add(text.lower())
        return sorted(normalized)


__all__ = ["EpisodicMemoryStore"]
