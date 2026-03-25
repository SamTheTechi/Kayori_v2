from __future__ import annotations

import json
from typing import Any

from langchain_core.embeddings import Embeddings
from redis.asyncio import Redis
from redisvl.index import SearchIndex
from redisvl.query import VectorQuery
from redisvl.query.filter import Tag
from redisvl.schema import IndexSchema

from src.shared_types.protocol import (
    EpisodicMemoryBackendRecord,
    EpisodicMemorySearchResult,
)

EPISODIC_KEY_PREFIX = "kayori:memory:episodic"


class RedisEpisodicMemory:
    def __init__(
        self,
        *,
        redis_client: Redis,
        embedding: Embeddings,
        index_name: str = "kayori_episodic_idx",
        dimension: int = 768,
        namespace: str | None = "kayori-episodic",
        prefix: str = EPISODIC_KEY_PREFIX,
        distance_metric: str = "cosine",
    ) -> None:
        self.redis_client = redis_client
        self.embedding = embedding
        self.index_name = str(index_name or "kayori_episodic_idx").strip() or "kayori_episodic_idx"
        self.dimension = int(dimension)
        self.namespace = str(namespace or "kayori-episodic").strip() or "kayori-episodic"
        self.prefix = str(prefix or EPISODIC_KEY_PREFIX).strip() or EPISODIC_KEY_PREFIX
        self.distance_metric = str(distance_metric or "cosine").strip().lower() or "cosine"
        self.index = SearchIndex(
            schema=IndexSchema.from_dict(
                {
                    "index": {
                        "name": self.index_name,
                        "prefix": f"{self.prefix}:",
                        "storage_type": "hash",
                    },
                    "fields": [
                        {"name": "record_id", "type": "tag"},
                        {"name": "namespace", "type": "tag"},
                        {"name": "content", "type": "text"},
                        {"name": "metadata_json", "type": "text"},
                        {
                            "name": "embedding",
                            "type": "vector",
                            "attrs": {
                                "algorithm": "hnsw",
                                "dims": self.dimension,
                                "distance_metric": self.distance_metric,
                                "datatype": "float32",
                            },
                        },
                    ],
                }
            ),
            redis_client=self.redis_client,
        )
        if not self.index.exists():
            self.index.create(overwrite=False, drop=False)

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
        self.index.load(
            [
                {
                    "id": self._record_key(record_id, namespace),
                    "record_id": record_id,
                    "namespace": namespace,
                    "content": str(content or ""),
                    "metadata_json": json.dumps(dict(metadata or {}), separators=(",", ":")),
                    "embedding": vector,
                }
            ],
            id_field="id",
        )

    async def search(
        self,
        *,
        query: str,
        limit: int,
        namespace: str | None = None,
    ) -> list[EpisodicMemorySearchResult]:
        namespace = self._resolve_namespace(namespace)
        vector = await self._embed_query(query)
        rows = self.index.query(
            VectorQuery(
                vector=vector,
                vector_field_name="embedding",
                num_results=max(1, int(limit)),
                return_fields=[
                    "record_id",
                    "content",
                    "metadata_json",
                    "vector_distance",
                ],
                filter_expression=Tag("namespace") == namespace,
            )
        )

        results: list[EpisodicMemorySearchResult] = []
        for row in rows:
            record_id = str(row.get("record_id") or "").strip()
            if not record_id:
                continue
            metadata = self._load_metadata(row.get("metadata_json"))
            metadata.setdefault("id", record_id)
            results.append(
                EpisodicMemorySearchResult(
                    record=EpisodicMemoryBackendRecord(
                        id=record_id,
                        content=str(row.get("content") or ""),
                        metadata=metadata,
                    ),
                    backend_score=float(row.get("vector_distance") or 0.0),
                )
            )
        return results

    async def list_ids(
        self,
        *,
        namespace: str | None = None,
    ) -> list[str]:
        namespace = self._resolve_namespace(namespace)
        cursor = 0
        ids: list[str] = []
        prefix = f"{self.prefix}:{namespace}:"
        while True:
            cursor, keys = await self.redis_client.scan(
                cursor=cursor,
                match=f"{prefix}*",
                count=200,
            )
            for key in keys:
                text = self._decode(key)
                if text.startswith(prefix):
                    record_id = text[len(prefix):].strip()
                    if record_id:
                        ids.append(record_id)
            if cursor == 0:
                return ids

    async def fetch_records(
        self,
        *,
        ids: list[str],
        namespace: str | None = None,
    ) -> list[EpisodicMemoryBackendRecord]:
        if not ids:
            return []

        namespace = self._resolve_namespace(namespace)
        pipe = self.redis_client.pipeline()
        for record_id in ids:
            pipe.hgetall(self._record_key(record_id, namespace))

        records: list[EpisodicMemoryBackendRecord] = []
        for row in await pipe.execute():
            if not row:
                continue
            fields = {self._decode(key): value for key, value in dict(row).items()}
            record_id = self._decode(fields.get("record_id")).strip()
            if not record_id:
                continue
            metadata = self._load_metadata(fields.get("metadata_json"))
            metadata.setdefault("id", record_id)
            records.append(
                EpisodicMemoryBackendRecord(
                    id=record_id,
                    content=self._decode(fields.get("content")),
                    metadata=metadata,
                )
            )
        return records

    async def delete(
        self,
        *,
        ids: list[str],
        namespace: str | None = None,
    ) -> None:
        if not ids:
            return

        namespace = self._resolve_namespace(namespace)
        await self.redis_client.delete(
            *[self._record_key(record_id, namespace) for record_id in ids]
        )

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

    def _record_key(self, record_id: str, namespace: str) -> str:
        return f"{self.prefix}:{namespace}:{str(record_id).strip()}"

    def _resolve_namespace(self, namespace: str | None) -> str:
        return str(namespace or self.namespace).strip() or self.namespace

    @staticmethod
    def _load_metadata(raw: Any) -> dict[str, Any]:
        text = RedisEpisodicMemory._decode(raw)
        if not text:
            return {}
        try:
            value = json.loads(text)
        except Exception:
            return {}
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _decode(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value or "")


__all__ = ["RedisEpisodicMemory"]
