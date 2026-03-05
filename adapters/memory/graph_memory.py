from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

try:
    from langchain_core.documents import Document
except Exception:  # pragma: no cover - optional dependency guard
    class Document:  # type: ignore[no-redef]
        def __init__(self, page_content: str, metadata: dict[str, Any] | None = None) -> None:
            self.page_content = page_content
            self.metadata = metadata or {}

try:
    from langchain_neo4j import GraphCypherQAChain, Neo4jGraph
    from langchain_neo4j.graphs.graph_document import GraphDocument, Node, Relationship
except Exception as exc:  # pragma: no cover - optional dependency guard
    GraphCypherQAChain = None  # type: ignore[assignment]
    Neo4jGraph = None  # type: ignore[assignment]
    GraphDocument = Any  # type: ignore[assignment]
    Node = Any  # type: ignore[assignment]
    Relationship = Any  # type: ignore[assignment]
    _NEO4J_IMPORT_ERROR: Exception | None = exc
else:
    _NEO4J_IMPORT_ERROR = None


class ExtractedRelation(BaseModel):
    subject: str
    predicate: str
    obj: str
    confidence: float = 0.7


class RelationExtraction(BaseModel):
    entities: list[str] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)


class GraphMemory:
    """Gemini extraction + Neo4j graph memory.

    - Extract relations from text using structured output.
    - Write relations to Neo4j graph.
    - Query with GraphCypherQAChain.
    """

    def __init__(
        self,
        *,
        uri: str,
        username: str,
        password: str,
        extractor_llm: Any,
        query_llm: Any | None = None,
        database: str = "neo4j",
        verbose: bool = False,
    ) -> None:
        if _NEO4J_IMPORT_ERROR is not None:
            raise RuntimeError(
                "GraphMemory requires 'langchain-neo4j' and 'neo4j' packages."
            ) from _NEO4J_IMPORT_ERROR
        if extractor_llm is None:
            raise ValueError("extractor_llm is required")
        if not is_valid_neo4j_uri(uri):
            raise ValueError(f"Invalid NEO4J uri: {uri!r}")
        if not clean_text(username, 256) or not clean_text(password, 256):
            raise ValueError("username and password are required")

        self.graph = Neo4jGraph(
            url=uri,
            username=username,
            password=password,
            database=clean_text(database, 120) or "neo4j",
            refresh_schema=False,
        )
        self.extractor_llm = extractor_llm
        llm_for_query = query_llm or extractor_llm

        self.cypher_chain = GraphCypherQAChain.from_llm(
            cypher_llm=llm_for_query,
            qa_llm=llm_for_query,
            graph=self.graph,
            verbose=verbose,
            allow_dangerous_requests=True,
        )

    @classmethod
    def from_env(cls, *, extractor_llm: Any, query_llm: Any | None = None) -> GraphMemory | None:
        uri = os.getenv("NEO4J_URI", "").strip()
        username = os.getenv("NEO4J_USERNAME", "").strip()
        password = os.getenv("NEO4J_PASSWORD", "").strip()
        database = os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j"
        if not (
            uri
            and username
            and password
            and extractor_llm is not None
            and is_valid_neo4j_uri(uri)
        ):
            return None
        return cls(
            uri=uri,
            username=username,
            password=password,
            extractor_llm=extractor_llm,
            query_llm=query_llm,
            database=database,
        )

    def close(self) -> None:
        close_fn = getattr(self.graph, "close", None)
        if callable(close_fn):
            close_fn()

    def add_relations_from_text(self, text: str, *, source: str) -> int:
        payload = clean_text(text, 40000)
        if not payload:
            return 0

        extracted = self._extract_relations(payload)
        if extracted is None:
            return 0

        graph_docs: list[GraphDocument] = []
        seen: set[tuple[str, str, str]] = set()
        source_value = clean_text(source, 80) or "agent"

        for item in extracted.relations:
            subject = clean_text(item.subject, 120)
            predicate = clean_relation_label(item.predicate)
            obj = clean_text(item.obj, 120)
            if not (subject and predicate and obj):
                continue

            key = (subject.lower(), predicate, obj.lower())
            if key in seen:
                continue
            seen.add(key)

            source_node = Node(id=subject, type="Entity")
            target_node = Node(id=obj, type="Entity")
            relationship = Relationship(
                source=source_node,
                target=target_node,
                type=predicate,
                properties={
                    "source": source_value,
                    "confidence": clamp_float(item.confidence, 0.0, 1.0),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            source_doc = Document(
                page_content=f"{subject} {predicate} {obj}",
                metadata={"source": source_value},
            )
            graph_docs.append(
                GraphDocument(
                    nodes=[source_node, target_node],
                    relationships=[relationship],
                    source=source_doc,
                )
            )

        if not graph_docs:
            return 0

        self._add_graph_documents(graph_docs)
        return len(graph_docs)

    def recall_context(self, query: str, *, hops: int = 2, limit: int = 20) -> str:
        payload = clean_text(query, 4000)
        if not payload:
            return ""

        hop_count = clamp_int(hops, 1, 4)
        top_k = clamp_int(limit, 1, 50)
        query_with_hints = (
            f"{payload}\n\n"
            f"Constraint: max traversal depth={hop_count}, max rows={top_k}."
        )

        result = self.cypher_chain.invoke({"query": query_with_hints})
        if isinstance(result, dict):
            value = result.get("result", result)
        else:
            value = result
        return str(value).strip()

    def _extract_relations(self, text: str) -> RelationExtraction | None:
        llm = self.extractor_llm.with_structured_output(RelationExtraction)
        prompt = (
            "Extract directed factual triples from the text. "
            "Return entities and relations. "
            "Use concise relation labels like WORKS_AT, MANAGES, DEPENDS_ON, LIVES_IN, OWNS. "
            "If nothing factual exists, return empty lists.\n\n"
            f"Text:\n{text}"
        )
        try:
            result = llm.invoke(prompt)
            if isinstance(result, RelationExtraction):
                return result
            if isinstance(result, dict):
                return RelationExtraction.model_validate(result)
            return None
        except Exception:
            return None

    def _add_graph_documents(self, graph_docs: list[GraphDocument]) -> None:
        try:
            self.graph.add_graph_documents(
                graph_docs,
                include_source=False,
                baseEntityLabel=False,
            )
        except TypeError:
            # Some versions use snake_case kwargs.
            self.graph.add_graph_documents(
                graph_docs,
                include_source=False,
                base_entity_label=False,
            )
        try:
            self.graph.refresh_schema()
        except Exception:
            pass


def clean_text(value: Any, max_len: int) -> str:
    clean = " ".join(str(value or "").strip().split())
    if len(clean) <= max_len:
        return clean
    return clean[:max_len].rstrip()


def clean_relation_label(value: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_]+", "_", (value or "").strip().upper())
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw[:64] or "RELATED_TO"


def clamp_float(value: Any, low: float, high: float) -> float:
    try:
        f = float(value)
    except Exception:
        f = low
    return max(low, min(high, f))


def clamp_int(value: Any, low: int, high: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = low
    return max(low, min(high, number))


def is_valid_neo4j_uri(uri: str) -> bool:
    parsed = urlparse((uri or "").strip())
    return parsed.scheme in {"neo4j", "neo4j+s", "bolt", "bolt+s", "bolt+ssc"} and bool(parsed.netloc)


__all__ = ["GraphMemory", "RelationExtraction", "ExtractedRelation"]
