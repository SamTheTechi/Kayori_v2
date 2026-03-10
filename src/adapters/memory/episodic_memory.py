from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    pass

COMPACT_BATCH_SIZE = 200
COMPACT_AGE_WEIGHT = 0.7
COMPACT_WEAKNESS_WEIGHT = 0.3
RECALL_VECTOR_WEIGHT = 0.7
RECALL_IMPORTANCE_WEIGHT = 0.2
RECALL_CONFIDENCE_WEIGHT = 0.1
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


@dataclass(slots=True, kw_only=True)
class EpisodicMemoryStore:
    vector_store: Any
    namespace: str = "kayori-episodic"
    min_score_default: float = 0.35
    max_episodes: int | None = 250

    def __post_init__(self) -> None:
        self.namespace = (
            self.namespace or "kayori-episodic"
        ).strip() or "kayori-episodic"
        self.min_score_default = self._clamp(
            self._to_float(self.min_score_default, 0.35), 0.0, 1.0
        )
        if self.max_episodes is not None:
            self.max_episodes = max(0, self._to_int(self.max_episodes, 250))

    @classmethod
    def from_env(cls) -> EpisodicMemoryStore:
        try:
            from langchain_pinecone import PineconeEmbeddings, PineconeVectorStore
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "langchain_pinecone is required to use EpisodicMemoryStore.from_env()"
            ) from exc

        pinecone_api_key = (os.getenv("PINECONE_API_KEY") or "").strip()
        index_name = (
            os.getenv("PINECONE_INDEX_NAME") or os.getenv("PINECONE_INDEX") or ""
        ).strip()
        host = (
            os.getenv("PINECONE_INDEX_HOST") or os.getenv("PINECONE_HOST") or ""
        ).strip()
        namespace = (
            os.getenv("PINECONE_NAMESPACE") or "kayori-episodic"
        ).strip() or "kayori-episodic"
        embedding_model = (
            os.getenv("PINECONE_EMBEDDING_MODEL") or "multilingual-e5-large"
        ).strip()

        if not pinecone_api_key:
            raise ValueError("PINECONE_API_KEY is required")
        if not index_name and not host:
            raise ValueError(
                "PINECONE_INDEX_NAME/PINECONE_INDEX or PINECONE_INDEX_HOST is required"
            )

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
        max_episodes_raw = (os.getenv("EPISODIC_MAX_EPISODES") or "").strip()
        max_episodes = cls._to_int(max_episodes_raw, 250) if max_episodes_raw else 250

        return cls(
            vector_store=vector_store,
            namespace=namespace,
            min_score_default=cls._to_float(
                os.getenv("EPISODIC_RECALL_MIN_SCORE"), 0.35
            ),
            max_episodes=max_episodes,
        )

    async def remember(
        self,
        *,
        fact: str,
        source: str,
        category: str = "misc",
        importance: int = 3,
        confidence: float = 0.8,
        tags: list[str] | None = None,
        context: str = "",
    ) -> dict[str, Any]:
        record = self._build_fact_record(
            fact=fact,
            source=source,
            category=category,
            importance=importance,
            confidence=confidence,
            tags=tags,
            context=context,
        )

        await self.vector_store.aadd_texts(
            texts=[self._embedding_text(record)],
            metadatas=[dict(record)],
            ids=[str(record["id"])],
            namespace=self.namespace,
        )

        if self.max_episodes is not None:
            try:
                await self.compact(max_episodes=self.max_episodes)
            except Exception as exc:
                print(f"[episodic-memory] compact failed: {exc}")

        return dict(record)

    async def recall(
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
            self.min_score_default
            if min_score is None
            else self._to_float(min_score, self.min_score_default),
            0.0,
            1.0,
        )

        results = await self.vector_store.asimilarity_search_with_score(
            query=query_text,
            k=max(top_k * 5, 20),
            namespace=self.namespace,
        )

        ranked: list[tuple[float, dict[str, Any]]] = []
        seen_ids: set[str] = set()
        for doc, raw_score in results:
            metadata = dict(getattr(doc, "metadata", {}) or {})
            if not metadata:
                continue

            record = self._record_from_metadata(metadata)
            if record is None:
                continue

            record_id = str(record.get("id") or "")
            if not record_id or record_id in seen_ids:
                continue
            seen_ids.add(record_id)

            vector_score = self._normalize_vector_score(raw_score)
            importance_score = self._importance_score(record.get("importance"))
            confidence = self._clamp(
                self._to_float(record.get("confidence"), 0.5), 0.0, 1.0
            )
            final_score = (
                (vector_score * RECALL_VECTOR_WEIGHT)
                + (importance_score * RECALL_IMPORTANCE_WEIGHT)
                + (confidence * RECALL_CONFIDENCE_WEIGHT)
            )
            if final_score >= threshold:
                ranked.append((final_score, record))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [dict(record) for _, record in ranked[:top_k]]

    async def compact(self, *, max_episodes: int | None = None) -> int:
        keep = self.max_episodes if max_episodes is None else max_episodes
        if keep is None:
            return 0

        keep = max(0, self._to_int(keep, 0))
        ids: list[str] = []
        async with self.vector_store._async_index_context() as index:
            async for page in index.list(namespace=self.namespace):
                ids.extend(str(item).strip() for item in page if str(item).strip())

            if len(ids) <= keep:
                return 0

            records: list[dict[str, Any]] = []
            for start in range(0, len(ids), COMPACT_BATCH_SIZE):
                batch = ids[start : start + COMPACT_BATCH_SIZE]
                fetched = await index.fetch(ids=batch, namespace=self.namespace)
                vectors = getattr(fetched, "vectors", {}) or {}
                for vector_id in batch:
                    vector = vectors.get(vector_id)
                    if vector is None:
                        continue
                    metadata = dict(getattr(vector, "metadata", {}) or {})
                    metadata.setdefault("id", vector_id)
                    record = self._record_from_metadata(metadata)
                    if record is not None:
                        records.append(record)

        if len(records) <= keep:
            return 0

        records.sort(
            key=lambda record: self._parse_ts(str(record.get("timestamp", "")))
        )
        total = len(records)
        scored: list[tuple[float, str]] = []
        for idx, record in enumerate(records):
            age_score = 1.0 if total == 1 else 1.0 - (idx / (total - 1))
            retention = self._retention_strength(
                importance=record.get("importance"),
                confidence=record.get("confidence"),
            )
            weakness = 1.0 - retention
            eviction_score = (age_score * COMPACT_AGE_WEIGHT) + (
                weakness * COMPACT_WEAKNESS_WEIGHT
            )
            record_id = str(record.get("id") or "").strip()
            if record_id:
                scored.append((eviction_score, record_id))

        overflow = max(0, len(scored) - keep)
        if overflow == 0:
            return 0

        scored.sort(key=lambda item: item[0], reverse=True)
        delete_ids = [record_id for _, record_id in scored[:overflow]]
        if not delete_ids:
            return 0

        await self.vector_store.adelete(ids=delete_ids, namespace=self.namespace)
        return len(delete_ids)

    def _build_fact_record(
        self,
        *,
        fact: str,
        source: str,
        category: str,
        importance: int,
        confidence: float,
        tags: list[str] | None,
        context: str,
    ) -> dict[str, Any]:
        normalized_fact = self._clean_text(fact, 600)
        if not normalized_fact:
            raise ValueError("fact must be non-empty")

        normalized_category = self._normalize_category(category)
        normalized_importance = max(1, min(5, self._to_int(importance, 3)))
        normalized_confidence = self._clamp(self._to_float(confidence, 0.8), 0.0, 1.0)
        return {
            "id": f"FM-{uuid4().hex[:10]}",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": self._clean_text(source or "unknown", 80) or "unknown",
            "category": normalized_category,
            "importance": normalized_importance,
            "confidence": normalized_confidence,
            "tags": self._normalize_tags(tags or []),
            "fact": normalized_fact,
            "context": self._clean_text(context, 600),
        }

    def _record_from_metadata(self, metadata: dict[str, Any]) -> dict[str, Any] | None:
        record_id = self._clean_text(metadata.get("id", ""), 80)
        fact = self._clean_text(metadata.get("fact", ""), 600)
        if not record_id or not fact:
            return None

        raw_tags = metadata.get("tags", [])
        if isinstance(raw_tags, str):
            tags = [part.strip() for part in raw_tags.split(",") if part.strip()]
        elif isinstance(raw_tags, (list, tuple, set)):
            tags = [str(part).strip() for part in raw_tags if str(part).strip()]
        else:
            tags = []

        return {
            "id": record_id,
            "timestamp": self._clean_text(
                metadata.get("timestamp", datetime.now(UTC).isoformat()),
                80,
            )
            or datetime.now(UTC).isoformat(),
            "source": self._clean_text(metadata.get("source", "unknown"), 80)
            or "unknown",
            "category": self._normalize_category(metadata.get("category", "misc")),
            "importance": max(
                1, min(5, self._to_int(metadata.get("importance", 3), 3))
            ),
            "confidence": self._clamp(
                self._to_float(metadata.get("confidence", 0.5), 0.5), 0.0, 1.0
            ),
            "tags": self._normalize_tags(tags),
            "fact": fact,
            "context": self._clean_text(metadata.get("context", ""), 600),
        }

    def _embedding_text(self, record: dict[str, Any]) -> str:
        return "\n".join(
            [
                f"fact: {record.get('fact', '')}",
                f"context: {record.get('context', '')}",
                f"category: {record.get('category', 'misc')}",
                f"tags: {', '.join(record.get('tags') or [])}",
                f"source: {record.get('source', 'unknown')}",
            ]
        )

    @staticmethod
    def _importance_score(value: Any) -> float:
        importance = max(1, min(5, EpisodicMemoryStore._to_int(value, 3)))
        return EpisodicMemoryStore._clamp(float(importance) / 5.0, 0.0, 1.0)

    @staticmethod
    def _retention_strength(*, importance: Any, confidence: Any) -> float:
        importance_score = EpisodicMemoryStore._importance_score(importance)
        confidence_score = EpisodicMemoryStore._clamp(
            EpisodicMemoryStore._to_float(confidence, 0.5),
            0.0,
            1.0,
        )
        return (importance_score * 0.7) + (confidence_score * 0.3)

    @staticmethod
    def _normalize_category(value: Any) -> str:
        text = EpisodicMemoryStore._normalize_spaces(value).lower()
        if text in FACT_CATEGORIES:
            return text
        return "misc"

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
            return datetime.fromtimestamp(0, tz=UTC)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
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
        return f"{text[: max_len - 3]}..."

    @staticmethod
    def _normalize_tags(tags: list[str] | tuple[str, ...] | set[str]) -> list[str]:
        normalized: set[str] = set()
        for tag in tags:
            text = EpisodicMemoryStore._normalize_spaces(tag)
            if text:
                normalized.add(text.lower())
        return sorted(normalized)


__all__ = ["EpisodicMemoryStore"]
