from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Sequence
from uuid import uuid4

TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)
DEFAULT_MAX_EPISODES = 5000
DEFAULT_DEDUPE_WINDOW = 30
DEFAULT_RECALL_MIN_SCORE = 0.05
MEMORY_HEADER = (
    "# Episodic Memory\n\n"
    "> High-salience autobiographical episodes.\n"
    "> Durable markdown memory for language-agent workflows.\n\n"
)


@dataclass(slots=True)
class EpisodicEpisode:
    id: str
    timestamp: str
    source: str
    salience: int
    emotion: str
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source,
            "salience": self.salience,
            "emotion": self.emotion,
            "tags": list(self.tags),
            "summary": self.summary,
            "context": self.context,
        }


class EpisodicMemoryStore:
    """Simple durable episodic memory using a markdown file."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_episodes: int | None = DEFAULT_MAX_EPISODES,
        dedupe_window: int = DEFAULT_DEDUPE_WINDOW,
    ):
        self.path = Path(path)
        self._lock = RLock()
        self._cache: list[EpisodicEpisode] | None = None
        self._cache_mtime_ns: int | None = None
        self.max_episodes = _normalize_max_episodes(max_episodes)
        self.dedupe_window = max(0, to_int(dedupe_window, DEFAULT_DEDUPE_WINDOW))

    def remember(
        self,
        *,
        event: str,
        source: str,
        salience: int = 3,
        emotion: str = "Neutral",
        tags: list[str] | None = None,
        context: str = "",
    ) -> EpisodicEpisode:
        episode = build_episode(
            event=event,
            source=source,
            salience=salience,
            emotion=emotion,
            tags=tags,
            context=context,
        )
        if not episode.summary:
            raise ValueError("event must be non-empty")

        with self._lock:
            self._ensure_file()
            duplicate = self._find_duplicate_locked(episode)
            if duplicate is not None:
                return duplicate
            self._append_episode(episode)
            self._invalidate_cache()
            self._prune_if_needed_locked()
        return episode

    def recall(
        self,
        query: str,
        limit: int = 3,
        *,
        min_score: float = DEFAULT_RECALL_MIN_SCORE,
    ) -> list[EpisodicEpisode]:
        query_text = clean_text(query, 600)
        top_k = clamp(to_int(limit, 3), 1, 100)
        if not query_text:
            return self.recent(limit=top_k)

        with self._lock:
            episodes = self._read_all_locked()

        now = datetime.now(timezone.utc)
        threshold = max(0.0, min(1.0, float(min_score)))
        scored = [
            (episode_score(episode, query_text, now), episode) for episode in episodes
        ]
        ranked = sorted(
            [item for item in scored if item[0] >= threshold],
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked:
            return self.recent(limit=top_k)
        return [episode for _, episode in ranked[:top_k]]

    def recent(self, limit: int = 5) -> list[EpisodicEpisode]:
        top_k = clamp(to_int(limit, 5), 1, 100)
        with self._lock:
            episodes = self._read_all_locked()
        return sorted(episodes, key=lambda episode: episode.timestamp, reverse=True)[:top_k]

    def recall_context(self, query: str, limit: int = 3) -> str:
        return self.format_episodes(self.recall(query, limit=limit))

    def compact(self, *, max_episodes: int | None = None) -> int:
        with self._lock:
            self._ensure_file()
            episodes = self._read_all_locked()
            limit = (
                self.max_episodes
                if max_episodes is None
                else _normalize_max_episodes(max_episodes)
            )
            if limit is None or len(episodes) <= limit:
                return 0

            kept = episodes[-limit:]
            removed = len(episodes) - len(kept)
            self._rewrite_file_locked(kept)
            self._invalidate_cache()
            return removed

    def format_episodes(self, episodes: Sequence[EpisodicEpisode]) -> str:
        lines: list[str] = []
        for episode in episodes:
            tags = ", ".join(episode.tags) if episode.tags else "-"
            lines.append(
                f"[{episode.timestamp}] ({episode.salience}/5, {episode.source}) "
                f"{episode.summary} | emotion={episode.emotion} | tags={tags}"
            )
            if episode.context:
                lines.append(f"  context: {episode.context}")
        return "\n".join(lines)

    def _ensure_file(self) -> None:
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(MEMORY_HEADER, encoding="utf-8")

    def _append_episode(self, episode: EpisodicEpisode) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(render_episode_block(episode))

    def _rewrite_file_locked(self, episodes: Sequence[EpisodicEpisode]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            handle.write(MEMORY_HEADER)
            for episode in episodes:
                handle.write(render_episode_block(episode))

    def _read_all_locked(self) -> list[EpisodicEpisode]:
        if not self.path.exists():
            return []

        mtime_ns = self.path.stat().st_mtime_ns
        if self._cache is not None and self._cache_mtime_ns == mtime_ns:
            return list(self._cache)

        lines = self.path.read_text(encoding="utf-8").splitlines()
        episodes: list[EpisodicEpisode] = []
        current: dict[str, str] | None = None

        for line in lines:
            if line.startswith("## Episode "):
                if current:
                    episode = parse_episode(current)
                    if episode is not None:
                        episodes.append(episode)
                current = {"id": line.replace("## Episode ", "", 1).strip()}
                continue

            if current is None:
                continue

            if line.startswith("- ") and ":" in line:
                key, value = line[2:].split(":", maxsplit=1)
                current[key.strip().lower()] = value.strip()

        if current:
            episode = parse_episode(current)
            if episode is not None:
                episodes.append(episode)

        self._cache = episodes
        self._cache_mtime_ns = mtime_ns
        return list(episodes)

    def _find_duplicate_locked(self, candidate: EpisodicEpisode) -> EpisodicEpisode | None:
        if self.dedupe_window <= 0:
            return None
        episodes = self._read_all_locked()
        if not episodes:
            return None
        needle = dedupe_key(candidate)
        for existing in reversed(episodes[-self.dedupe_window:]):
            if dedupe_key(existing) == needle:
                return existing
        return None

    def _prune_if_needed_locked(self) -> int:
        limit = self.max_episodes
        if limit is None:
            return 0

        episodes = self._read_all_locked()
        if len(episodes) <= limit:
            return 0

        kept = episodes[-limit:]
        removed = len(episodes) - len(kept)
        self._rewrite_file_locked(kept)
        self._invalidate_cache()
        return removed

    def _invalidate_cache(self) -> None:
        self._cache = None
        self._cache_mtime_ns = None


class EpisodicMemoryExtender:
    """Small LangGraph adapter around EpisodicMemoryStore."""

    def __init__(self, store: EpisodicMemoryStore):
        self.store = store

    @classmethod
    def from_markdown(cls, path: str | Path) -> EpisodicMemoryExtender:
        return cls(EpisodicMemoryStore(path))

    def recall_into_state(
        self,
        *,
        query_key: str = "input",
        output_key: str = "episodic_memories",
        context_output_key: str | None = None,
        limit: int = 3,
        limit_key: str | None = None,
    ):
        def node(state: Mapping[str, Any]) -> dict[str, Any]:
            query = coerce_text(state.get(query_key))
            if not query:
                payload: dict[str, Any] = {output_key: []}
                if context_output_key:
                    payload[context_output_key] = ""
                return payload

            recall_limit = clamp(to_int(state.get(limit_key), limit), 1, 100) if limit_key else clamp(limit, 1, 100)
            episodes = self.store.recall(query, limit=recall_limit)
            payload: dict[str, Any] = {output_key: [episode.to_dict() for episode in episodes]}
            if context_output_key:
                payload[context_output_key] = self.store.format_episodes(episodes)
            return payload

        return node

    def remember_from_state(
        self,
        *,
        event_key: str = "input",
        source: str = "langgraph",
        source_key: str | None = None,
        salience: int = 3,
        salience_key: str | None = None,
        emotion: str = "Neutral",
        emotion_key: str | None = None,
        tags: list[str] | None = None,
        tags_key: str | None = None,
        context: str = "",
        context_key: str | None = None,
        output_key: str | None = None,
    ):
        default_tags = normalize_tags(tags or [])

        def node(state: Mapping[str, Any]) -> dict[str, Any]:
            event = coerce_text(state.get(event_key))
            if not event:
                return {}

            event_source = coerce_text(state.get(source_key)) if source_key else source
            event_emotion = coerce_text(state.get(emotion_key)) if emotion_key else emotion
            event_context = coerce_text(state.get(context_key)) if context_key else context
            event_tags = normalize_tags(coerce_tags(state.get(tags_key))) if tags_key else default_tags
            event_salience = clamp(to_int(state.get(salience_key), salience), 1, 5) if salience_key else salience

            episode = self.store.remember(
                event=event,
                source=event_source or source,
                salience=event_salience,
                emotion=event_emotion or emotion,
                tags=event_tags,
                context=event_context or context,
            )
            if not output_key:
                return {}
            return {output_key: episode.to_dict()}

        return node


def episode_score(episode: EpisodicEpisode, query: str, now: datetime) -> float:
    query_tokens = tokenize(query)
    episode_tokens = tokenize(f"{episode.summary} {episode.context} {' '.join(episode.tags)}")
    lexical = overlap_score(query_tokens, episode_tokens)
    meta = overlap_score(query_tokens, tokenize(f"{episode.source} {episode.emotion}"))

    try:
        created = datetime.fromisoformat(episode.timestamp)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - created).total_seconds() / 86400.0)
    except Exception:
        age_days = 365.0

    recency = 1.0 / (1.0 + age_days / 14.0)
    salience = clamp(episode.salience, 1, 5) / 5.0
    return lexical * 0.60 + salience * 0.20 + recency * 0.10 + meta * 0.10


def parse_episode(payload: Mapping[str, str]) -> EpisodicEpisode | None:
    return episode_from_mapping(payload)


def episode_from_mapping(payload: Mapping[str, Any]) -> EpisodicEpisode | None:
    episode_id = clean_text(str(payload.get("id", "")), 80)
    if not episode_id:
        return None

    return EpisodicEpisode(
        id=episode_id,
        timestamp=clean_text(
            str(payload.get("timestamp", datetime.now(timezone.utc).isoformat())),
            80,
        )
        or datetime.now(timezone.utc).isoformat(),
        source=clean_text(str(payload.get("source", "unknown")), 80) or "unknown",
        salience=clamp(to_int(payload.get("salience"), 3), 1, 5),
        emotion=clean_text(str(payload.get("emotion", "Neutral")), 40) or "Neutral",
        tags=normalize_tags(_coerce_tag_values(payload.get("tags"))),
        summary=clean_text(str(payload.get("summary", "")), 600),
        context=clean_text(str(payload.get("context", "")), 600),
    )


def tokenize(text: str) -> set[str]:
    normalized = normalize_text(text)
    word_tokens = {
        token.strip("_")
        for token in TOKEN_RE.findall(normalized)
        if token and token.strip("_")
    }
    if word_tokens:
        return word_tokens
    return char_ngrams(normalized, n=3)


def overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    return (2.0 * overlap) / (len(left) + len(right))


def coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return clean_text(value, 600)
    return clean_text(str(value), 600)


def coerce_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",")]
    if isinstance(value, Sequence):
        return [str(part).strip() for part in value]
    return [str(value).strip()]


def normalize_tags(tags: Sequence[str]) -> list[str]:
    return sorted({tag.strip().lower() for tag in tags if tag and tag.strip()})


def _coerce_tag_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",")]
    if isinstance(value, Sequence):
        return [str(part).strip() for part in value]
    return [str(value).strip()]


def dedupe_key(episode: EpisodicEpisode) -> tuple[str, str, str]:
    return (
        normalize_text(episode.summary),
        normalize_text(episode.context),
        normalize_text(episode.source),
    )


def build_episode(
    *,
    event: str,
    source: str,
    salience: int = 3,
    emotion: str = "Neutral",
    tags: list[str] | None = None,
    context: str = "",
) -> EpisodicEpisode:
    return EpisodicEpisode(
        id=f"EP-{uuid4().hex[:10]}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source=clean_text(source or "unknown", 80) or "unknown",
        salience=clamp(to_int(salience, 3), 1, 5),
        emotion=clean_text(emotion or "Neutral", 40) or "Neutral",
        tags=normalize_tags(tags or []),
        summary=clean_text(event, 600),
        context=clean_text(context, 600),
    )


def render_episode_block(episode: EpisodicEpisode) -> str:
    return (
        f"## Episode {episode.id}\n"
        f"- timestamp: {episode.timestamp}\n"
        f"- source: {episode.source}\n"
        f"- salience: {episode.salience}\n"
        f"- emotion: {episode.emotion}\n"
        f"- tags: {', '.join(episode.tags)}\n"
        f"- summary: {episode.summary}\n"
        f"- context: {episode.context}\n\n"
    )


def _normalize_max_episodes(value: int | None) -> int | None:
    if value is None:
        return None
    limit = to_int(value, DEFAULT_MAX_EPISODES)
    if limit <= 0:
        return None
    return limit


def to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def clean_text(value: str, max_len: int) -> str:
    clean = normalize_spaces(value)
    if len(clean) <= max_len:
        return clean
    return f"{clean[:max_len - 3]}..."


def normalize_text(value: str) -> str:
    return normalize_spaces(value).lower()


def normalize_spaces(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    return " ".join(normalized.strip().split())


def char_ngrams(text: str, n: int = 3) -> set[str]:
    compact = "".join(ch for ch in text if ch.isalnum())
    if not compact:
        return set()
    if len(compact) <= n:
        return {compact}
    return {compact[i: i + n] for i in range(0, len(compact) - n + 1)}


__all__ = ["EpisodicEpisode", "EpisodicMemoryStore", "EpisodicMemoryExtender"]
