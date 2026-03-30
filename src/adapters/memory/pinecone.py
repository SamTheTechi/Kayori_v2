from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings

from src.shared_types.protocol import (
    EpisodicMemoryBackendRecord,
    EpisodicMemorySearchResult,
)


class PineconeEpisodicMemory:
    def __init__(
        self,
        *,
        index_name: str = "kayori",
        dimension: int = 768,
        api_key: str,
        namespace: str | None = "kayori-episodic",
        embedding: Embeddings,
    ) -> None:
        from langchain_pinecone import PineconeVectorStore
        from pinecone import Pinecone, ServerlessSpec

        pc = Pinecone(api_key=api_key)

        if index_name not in [index["name"] for index in pc.list_indexes()]:
            pc.create_index(
                name=index_name,
                dimension=int(dimension),
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1",
                ),
            )

        pinecone_index = pc.Index(index_name)
        self.vector_store = PineconeVectorStore(
            embedding=embedding,
            index=pinecone_index,
            namespace=namespace,
        )
        self.namespace = namespace

    async def upsert(
        self,
        *,
        record_id: str,
        content: str,
        metadata: dict[str, Any],
        namespace: str | None = None,
    ) -> None:
        await self.vector_store.aadd_texts(
            texts=[content],
            metadatas=[dict(metadata)],
            ids=[record_id],
            namespace=namespace,
        )

    async def search(
        self,
        *,
        query: str,
        limit: int,
        namespace: str | None = None,
    ) -> list[EpisodicMemorySearchResult]:
        results = await self.vector_store.asimilarity_search_with_score(
            query=query,
            k=limit,
            namespace=namespace,
        )
        parsed: list[EpisodicMemorySearchResult] = []
        for doc, raw_score in results:
            metadata = dict(getattr(doc, "metadata", {}) or {})
            record_id = str(
                metadata.get("id")
                or getattr(doc, "id", "")
                or getattr(doc, "lc_id", "")
                or ""
            ).strip()
            if not record_id:
                continue
            parsed.append(
                EpisodicMemorySearchResult(
                    record=EpisodicMemoryBackendRecord(
                        id=record_id,
                        content=str(getattr(doc, "page_content", "") or ""),
                        metadata=metadata,
                    ),
                    backend_score=float(raw_score),
                )
            )
        return parsed

    async def list_ids(
        self,
        *,
        namespace: str | None = None,
    ) -> list[str]:
        ids: list[str] = []
        async with self.vector_store._async_index_context() as index:
            async for page in index.list(namespace=namespace):
                ids.extend(str(item).strip()
                           for item in page if str(item).strip())
        return ids

    async def fetch_records(
        self,
        *,
        ids: list[str],
        namespace: str | None = None,
    ) -> list[EpisodicMemoryBackendRecord]:
        if not ids:
            return []

        async with self.vector_store._async_index_context() as index:
            fetched = await index.fetch(ids=ids, namespace=namespace)
        vectors = getattr(fetched, "vectors", {}) or {}

        records: list[EpisodicMemoryBackendRecord] = []
        for record_id in ids:
            vector = vectors.get(record_id)
            if vector is None:
                continue
            metadata = dict(getattr(vector, "metadata", {}) or {})
            metadata.setdefault("id", record_id)
            records.append(
                EpisodicMemoryBackendRecord(
                    id=record_id,
                    content="",
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
        await self.vector_store.adelete(
            ids=ids,
            namespace=namespace,
        )


__all__ = ["PineconeEpisodicMemory"]
