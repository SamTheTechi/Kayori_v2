from __future__ import annotations

import asyncio
import os
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

try:
    from langchain_neo4j import Neo4jGraph
except Exception as exc:  # pragma: no cover - optional dependency guard
    Neo4jGraph = None  # type: ignore[assignment]
    _NEO4J_IMPORT_ERROR: Exception | None = exc
else:
    _NEO4J_IMPORT_ERROR = None


class GraphMemory:
    def __init__(
        self,
        *,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
    ) -> None:
        if _NEO4J_IMPORT_ERROR is not None:
            raise RuntimeError(
                "GraphMemory requires 'langchain-neo4j' and 'neo4j' packages."
            ) from _NEO4J_IMPORT_ERROR
        if not is_valid_neo4j_uri(uri):
            raise ValueError(f"Invalid NEO4J uri: {uri!r}")

        user_value = clean_text(username, 256)
        password_value = clean_text(password, 256)
        if not user_value or not password_value:
            raise ValueError("username and password are required")

        self.graph = Neo4jGraph(
            url=uri,
            username=user_value,
            password=password_value,
            database=clean_text(database, 120) or "neo4j",
            refresh_schema=False,
        )
        self._schema_ready = False

    @classmethod
    def from_env(cls) -> GraphMemory | None:
        uri = (os.getenv("NEO4J_URI") or "").strip()
        username = (os.getenv("NEO4J_USERNAME") or "").strip()
        password = (os.getenv("NEO4J_PASSWORD") or "").strip()
        database = (os.getenv("NEO4J_DATABASE") or "neo4j").strip() or "neo4j"

        if not (uri and username and password and is_valid_neo4j_uri(uri)):
            return None

        return cls(
            uri=uri,
            username=username,
            password=password,
            database=database,
        )

    async def remember(
        self,
        *,
        subject: str,
        predicate: str,
        obj: str,
        source: str,
        confidence: float = 0.8,
    ) -> dict[str, Any]:
        normalized = self._normalize_relation(
            subject=subject,
            predicate=predicate,
            obj=obj,
            source=source,
            confidence=confidence,
        )
        await self._ensure_schema()

        now_iso = datetime.now(UTC).isoformat()
        query = f"""
        MERGE (s:Entity {{id: $subject_id}})
        ON CREATE SET s.name = $subject, s.updated_at = $now
        ON MATCH SET s.name = $subject, s.updated_at = $now
        MERGE (o:Entity {{id: $object_id}})
        ON CREATE SET o.name = $object, o.updated_at = $now
        ON MATCH SET o.name = $object, o.updated_at = $now
        MERGE (s)-[r:{normalized["predicate"]}]->(o)
        ON CREATE SET
            r.source = $source,
            r.confidence = $confidence,
            r.created_at = $now,
            r.updated_at = $now
        ON MATCH SET
            r.source = $source,
            r.confidence = CASE
                WHEN r.confidence IS NULL OR r.confidence < $confidence THEN $confidence
                ELSE r.confidence
            END,
            r.updated_at = $now
        RETURN
            s.name AS subject,
            type(r) AS predicate,
            o.name AS object,
            r.source AS source,
            r.confidence AS confidence,
            r.created_at AS created_at,
            r.updated_at AS updated_at
        """
        rows = await asyncio.to_thread(
            self.graph.query,
            query,
            {
                "subject_id": normalized["subject_id"],
                "subject": normalized["subject"],
                "object_id": normalized["object_id"],
                "object": normalized["object"],
                "source": normalized["source"],
                "confidence": normalized["confidence"],
                "now": now_iso,
            },
        )
        if not rows:
            raise RuntimeError("Graph write succeeded without a return row")
        return self._record_from_row(rows[0])

    async def recall(
        self,
        *,
        entity: str | None = None,
        predicate: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        entity_id = normalize_entity_id(entity) if entity is not None else None
        predicate_value = (
            normalize_predicate(predicate) if predicate is not None else None
        )
        top_k = clamp_int(limit, 1, 100)

        if not entity_id and not predicate_value:
            raise ValueError("recall requires entity or predicate")

        await self._ensure_schema()
        rows = await asyncio.to_thread(
            self.graph.query,
            """
            MATCH (s:Entity)-[r]->(o:Entity)
            WHERE
                ($entity_id IS NULL OR s.id = $entity_id OR o.id = $entity_id)
                AND
                ($predicate IS NULL OR type(r) = $predicate)
            RETURN
                s.name AS subject,
                type(r) AS predicate,
                o.name AS object,
                r.source AS source,
                r.confidence AS confidence,
                r.created_at AS created_at,
                r.updated_at AS updated_at
            ORDER BY coalesce(r.updated_at, r.created_at) DESC, coalesce(r.confidence, 0.0) DESC
            LIMIT $limit
            """,
            {
                "entity_id": entity_id,
                "predicate": predicate_value,
                "limit": top_k,
            },
        )
        return [self._record_from_row(row) for row in rows]

    async def close(self) -> None:
        close_fn = getattr(self.graph, "close", None)
        if callable(close_fn):
            await asyncio.to_thread(close_fn)

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return

        await asyncio.to_thread(
            self.graph.query,
            """
            CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
            FOR (n:Entity)
            REQUIRE n.id IS UNIQUE
            """,
        )

        refresh_schema = getattr(self.graph, "refresh_schema", None)
        if callable(refresh_schema):
            await asyncio.to_thread(refresh_schema)
        self._schema_ready = True

    def _normalize_relation(
        self,
        *,
        subject: str,
        predicate: str,
        obj: str,
        source: str,
        confidence: float,
    ) -> dict[str, Any]:
        subject_value = clean_text(subject, 120)
        object_value = clean_text(obj, 120)
        source_value = clean_text(source, 80) or "unknown"
        subject_id = normalize_entity_id(subject_value)
        object_id = normalize_entity_id(object_value)
        predicate_value = normalize_predicate(predicate)

        if not subject_value or not subject_id:
            raise ValueError("subject must be non-empty")
        if not object_value or not object_id:
            raise ValueError("obj must be non-empty")
        if not predicate_value:
            raise ValueError("predicate must be non-empty")

        return {
            "subject": subject_value,
            "subject_id": subject_id,
            "predicate": predicate_value,
            "object": object_value,
            "object_id": object_id,
            "source": source_value,
            "confidence": clamp_float(confidence, 0.0, 1.0),
        }

    @staticmethod
    def _record_from_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "subject": clean_text(row.get("subject", ""), 120),
            "predicate": normalize_predicate(row.get("predicate", "")),
            "object": clean_text(row.get("object", ""), 120),
            "source": clean_text(row.get("source", "unknown"), 80) or "unknown",
            "confidence": clamp_float(row.get("confidence", 0.0), 0.0, 1.0),
            "created_at": clean_text(row.get("created_at", ""), 80),
            "updated_at": clean_text(row.get("updated_at", ""), 80),
        }


def clean_text(value: Any, max_len: int) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip()


def normalize_entity_id(value: Any) -> str:
    text = clean_text(value, 120).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:120]


def normalize_predicate(value: Any) -> str:
    text = clean_text(value, 64).upper()
    text = re.sub(r"[^A-Z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:64]


def clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except Exception:
        number = low
    return max(low, min(high, number))


def clamp_int(value: Any, low: int, high: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = low
    return max(low, min(high, number))


def is_valid_neo4j_uri(uri: str) -> bool:
    parsed = urlparse((uri or "").strip())
    return parsed.scheme in {"neo4j", "neo4j+s", "bolt", "bolt+s", "bolt+ssc"} and bool(
        parsed.netloc
    )


__all__ = ["GraphMemory"]
