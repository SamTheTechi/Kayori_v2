from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from src.shared_types.protocol import (
    EpisodicMemoryBackend,
    EpisodicMemoryBackendRecord,
)

DEFAULT_NAMESPACE = "kayori-episodic"
DEFAULT_MAX_EPISODES = 250
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


class EpisodicMemoryStore:
    def __init__(
        self,
        *,
        backend: EpisodicMemoryBackend,
        namespace: str = DEFAULT_NAMESPACE,
        min_score_default: float = 0.35,
        max_episodes: int | None = DEFAULT_MAX_EPISODES,
    ) -> None:
        self.backend = backend
        self.namespace = self._clean_text(namespace, 600) or DEFAULT_NAMESPACE
        self.min_score_default = self._clamp(
            self._to_float(min_score_default, 0.35),
            0.0,
            1.0,
        )
        self.max_episodes = (
            None
            if max_episodes is None
            else max(0, self._to_int(max_episodes, DEFAULT_MAX_EPISODES))
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
        record = self._make_record(
            fact=fact,
            source=source,
            category=category,
            importance=importance,
            confidence=confidence,
            tags=tags,
            context=context,
        )

        await self.backend.upsert(
            record_id=record["id"],
            content="\n".join(
                [
                    f"fact: {record.get('fact', '')}",
                    f"context: {record.get('context', '')}",
                    f"category: {record.get('category', 'misc')}",
                    f"tags: {', '.join(record.get('tags') or [])}",
                    f"source: {record.get('source', 'unknown')}",
                ]
            ),
            metadata=record,
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
        query = self._clean_text(query, 600)
        if not query:
            return []

        limit = max(1, min(100, self._to_int(limit, 3)))
        threshold = self._clamp(
            self.min_score_default
            if min_score is None
            else self._to_float(min_score, self.min_score_default),
            0.0,
            1.0,
        )

        results = await self.backend.search(
            query=query,
            limit=max(limit * 5, 20),
            namespace=self.namespace,
        )

        ranked: list[tuple[float, dict[str, Any]]] = []
        seen_ids: set[str] = set()
        for result in results:
            record = self._record_from_backend_record(result.record)
            if record is None:
                continue

            record_id = record["id"]
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)

            backend_score = self._to_float(result.backend_score, 0.0)
            if not 0.0 <= backend_score <= 1.0:
                backend_score = self._clamp(
                    (backend_score + 1.0) / 2.0, 0.0, 1.0)
            importance = max(1, min(5, self._to_int(
                record.get("importance"), 3))) / 5.0
            score = (
                backend_score * 0.7
                + importance * 0.2
                + self._clamp(self._to_float(record.get("confidence"), 0.5), 0.0, 1.0)
                * 0.1
            )
            if score >= threshold:
                ranked.append((score, record))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in ranked[:limit]]

    async def compact(self, *, max_episodes: int | None = None) -> int:
        keep = self.max_episodes if max_episodes is None else max_episodes
        if keep is None:
            return 0

        keep = max(0, self._to_int(keep, 0))
        ids = await self.backend.list_ids(namespace=self.namespace)
        if len(ids) <= keep:
            return 0

        records: list[dict[str, Any]] = []
        for start in range(0, len(ids), 200):
            batch = ids[start: start + 200]
            fetched = await self.backend.fetch_records(
                ids=batch,
                namespace=self.namespace,
            )
            for item in fetched:
                record = self._record_from_backend_record(item)
                if record is not None:
                    records.append(record)

        if len(records) <= keep:
            return 0

        def sort_key(record: dict[str, Any]) -> datetime:
            try:
                parsed = datetime.fromisoformat(
                    str(record.get("timestamp", "")))
            except Exception:
                return datetime.fromtimestamp(0, tz=UTC)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

        records.sort(key=sort_key)

        scored: list[tuple[float, str]] = []
        total = len(records)
        for index, record in enumerate(records):
            record_id = record["id"]
            age_score = 1.0 if total == 1 else 1.0 - (index / (total - 1))
            importance = max(1, min(5, self._to_int(
                record.get("importance"), 3))) / 5.0
            confidence = self._clamp(
                self._to_float(record.get("confidence"), 0.5),
                0.0,
                1.0,
            )
            weakness = 1.0 - ((importance * 0.7) + (confidence * 0.3))
            eviction_score = (
                (age_score * 0.7)
                + (weakness * 0.3)
            )
            scored.append((eviction_score, record_id))

        overflow = len(scored) - keep
        scored.sort(key=lambda item: item[0], reverse=True)
        delete_ids = [record_id for _, record_id in scored[:overflow]]
        await self.backend.delete(ids=delete_ids, namespace=self.namespace)
        return len(delete_ids)

    def _make_record(
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
        fact = self._clean_text(fact, 600)
        if not fact:
            raise ValueError("fact must be non-empty")

        normalized_tags: set[str] = set()
        for tag in tags or []:
            tag = " ".join(str(tag or "").strip().split()).lower()
            if tag:
                normalized_tags.add(tag)

        return {
            "id": f"FM-{uuid4().hex[:10]}",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": self._clean_text(source or "unknown", 80) or "unknown",
            "category": (
                category_name
                if (category_name := " ".join(str(category or "").strip().split()).lower()) in FACT_CATEGORIES
                else "misc"
            ),
            "importance": max(1, min(5, self._to_int(importance, 3))),
            "confidence": self._clamp(self._to_float(confidence, 0.8), 0.0, 1.0),
            "tags": sorted(normalized_tags),
            "fact": fact,
            "context": self._clean_text(context, 600),
        }

    def _record_from_backend_record(
        self,
        record: EpisodicMemoryBackendRecord,
    ) -> dict[str, Any] | None:
        metadata = dict(record.metadata or {})
        metadata.setdefault("id", record.id)

        record_id = self._clean_text(metadata.get("id", ""), 80)
        fact = self._clean_text(metadata.get("fact", ""), 600)
        if not record_id or not fact:
            return None

        tags = metadata.get("tags", [])
        if isinstance(tags, str):
            tags = [part.strip() for part in tags.split(",") if part.strip()]
        elif isinstance(tags, (list, tuple, set)):
            tags = [str(part).strip() for part in tags if str(part).strip()]
        else:
            tags = []

        normalized_tags: set[str] = set()
        for tag in tags:
            tag = " ".join(str(tag or "").strip().split()).lower()
            if tag:
                normalized_tags.add(tag)

        return {
            "id": record_id,
            "timestamp": self._clean_text(
                metadata.get("timestamp", datetime.now(UTC).isoformat()),
                80,
            )
            or datetime.now(UTC).isoformat(),
            "source": self._clean_text(metadata.get("source", "unknown"), 80)
            or "unknown",
            "category": (
                category_name
                if (category_name := " ".join(str(metadata.get("category", "misc") or "").strip().split()).lower()) in FACT_CATEGORIES
                else "misc"
            ),
            "importance": max(1, min(5, self._to_int(metadata.get("importance", 3), 3))),
            "confidence": self._clamp(
                self._to_float(metadata.get("confidence", 0.5), 0.5),
                0.0,
                1.0,
            ),
            "tags": sorted(normalized_tags),
            "fact": fact,
            "context": self._clean_text(metadata.get("context", ""), 600),
        }

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
    def _clean_text(value: Any, max_len: int) -> str:
        text = " ".join(str(value or "").strip().split())
        if len(text) <= max_len:
            return text
        return f"{text[: max_len - 3]}..."


__all__ = ["EpisodicMemoryStore"]
