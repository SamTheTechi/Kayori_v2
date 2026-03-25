from __future__ import annotations

import asyncio
import math
from typing import Any

from langchain_core.embeddings import Embeddings

from src.shared_types.protocol import (
    EpisodicMemoryBackendRecord,
    EpisodicMemorySearchResult,
)


class InMemoryEpisodicMemory:
    def __init__(
        self,
        *,
        embedding: Embeddings,
        namespace: str | None = "kayori-episodic",
    ) -> None:
        self.embedding = embedding
        self.namespace = str(namespace or "kayori-episodic").strip() or "kayori-episodic"
        self.records: dict[str, dict[str, dict[str, Any]]] = {}
        self.vectors: dict[str, dict[str, list[float]]] = {}
        self._lock = asyncio.Lock()

    async def upsert(
        self,
        *,
        record_id: str,
        content: str,
        metadata: dict[str, Any],
        namespace: str | None = None,
    ) -> None:
        record_id = str(record_id or "").strip()
        if not record_id:
            raise ValueError("record_id must be non-empty")

        namespace = self._resolve_namespace(namespace)
        vector = await self._embed_text(content)

        async with self._lock:
            self.records.setdefault(namespace, {})[record_id] = {
                "id": record_id,
                "content": str(content or ""),
                "metadata": dict(metadata or {}),
            }
            self.vectors.setdefault(namespace, {})[record_id] = vector

    async def search(
        self,
        *,
        query: str,
        limit: int,
        namespace: str | None = None,
    ) -> list[EpisodicMemorySearchResult]:
        namespace = self._resolve_namespace(namespace)
        query_vector = await self._embed_query(query)

        async with self._lock:
            records = dict(self.records.get(namespace, {}))
            vectors = dict(self.vectors.get(namespace, {}))

        scored: list[EpisodicMemorySearchResult] = []
        for record_id, vector in vectors.items():
            record = records.get(record_id)
            if record is None:
                continue
            scored.append(
                EpisodicMemorySearchResult(
                    record=EpisodicMemoryBackendRecord(
                        id=record_id,
                        content=str(record.get("content") or ""),
                        metadata=dict(record.get("metadata") or {}),
                    ),
                    backend_score=self._cosine_similarity(query_vector, vector),
                )
            )

        scored.sort(key=lambda item: item.backend_score, reverse=True)
        return scored[: max(1, int(limit))]

    async def list_ids(
        self,
        *,
        namespace: str | None = None,
    ) -> list[str]:
        namespace = self._resolve_namespace(namespace)
        async with self._lock:
            return list(self.records.get(namespace, {}).keys())

    async def fetch_records(
        self,
        *,
        ids: list[str],
        namespace: str | None = None,
    ) -> list[EpisodicMemoryBackendRecord]:
        if not ids:
            return []

        namespace = self._resolve_namespace(namespace)
        async with self._lock:
            records = dict(self.records.get(namespace, {}))

        result: list[EpisodicMemoryBackendRecord] = []
        for record_id in ids:
            record = records.get(record_id)
            if record is None:
                continue
            result.append(
                EpisodicMemoryBackendRecord(
                    id=record_id,
                    content=str(record.get("content") or ""),
                    metadata=dict(record.get("metadata") or {}),
                )
            )
        return result

    async def delete(
        self,
        *,
        ids: list[str],
        namespace: str | None = None,
    ) -> None:
        if not ids:
            return

        namespace = self._resolve_namespace(namespace)
        async with self._lock:
            records = self.records.get(namespace, {})
            vectors = self.vectors.get(namespace, {})
            for record_id in ids:
                records.pop(record_id, None)
                vectors.pop(record_id, None)

    async def _embed_text(self, text: str) -> list[float]:
        if hasattr(self.embedding, "aembed_documents"):
            vectors = await self.embedding.aembed_documents([text])
        else:
            vectors = self.embedding.embed_documents([text])
        return [float(value) for value in vectors[0]]

    async def _embed_query(self, text: str) -> list[float]:
        if hasattr(self.embedding, "aembed_query"):
            vector = await self.embedding.aembed_query(text)
        else:
            vector = self.embedding.embed_query(text)
        return [float(value) for value in vector]

    def _resolve_namespace(self, namespace: str | None) -> str:
        return str(namespace or self.namespace).strip() or self.namespace

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)


__all__ = ["InMemoryEpisodicMemory"]
