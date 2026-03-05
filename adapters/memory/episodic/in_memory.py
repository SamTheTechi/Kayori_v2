from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from memory.episodic_memory import (
    DEFAULT_DEDUPE_WINDOW,
    DEFAULT_MAX_EPISODES,
    DEFAULT_RECALL_MIN_SCORE,
    EpisodicEpisode,
    build_episode,
    dedupe_key,
    episode_score,
    to_int,
)


class InMemoryEpisodicMemoryStore:
    def __init__(
        self,
        *,
        max_episodes: int | None = DEFAULT_MAX_EPISODES,
        dedupe_window: int = DEFAULT_DEDUPE_WINDOW,
    ) -> None:
        self._episodes: list[EpisodicEpisode] = []
        self._lock = asyncio.Lock()
        self.max_episodes = _normalize_max_episodes(max_episodes)
        self.dedupe_window = max(0, to_int(dedupe_window, DEFAULT_DEDUPE_WINDOW))

    async def remember(
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

        async with self._lock:
            duplicate = self._find_duplicate_locked(episode)
            if duplicate is not None:
                return duplicate

            self._episodes.append(episode)
            self._prune_locked()
            return episode

    async def recall(
        self,
        query: str,
        limit: int = 3,
        *,
        min_score: float = DEFAULT_RECALL_MIN_SCORE,
    ) -> list[EpisodicEpisode]:
        top_k = max(1, min(100, to_int(limit, 3)))
        threshold = max(0.0, min(1.0, float(min_score)))
        now = datetime.now(timezone.utc)

        async with self._lock:
            snapshot = list(self._episodes)

        if not query.strip():
            return sorted(snapshot, key=lambda ep: ep.timestamp, reverse=True)[:top_k]

        scored = [(episode_score(ep, query, now), ep) for ep in snapshot]
        ranked = sorted(
            [item for item in scored if item[0] >= threshold],
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked:
            return sorted(snapshot, key=lambda ep: ep.timestamp, reverse=True)[:top_k]
        return [ep for _, ep in ranked[:top_k]]

    async def recent(self, limit: int = 5) -> list[EpisodicEpisode]:
        top_k = max(1, min(100, to_int(limit, 5)))
        async with self._lock:
            snapshot = list(self._episodes)
        return sorted(snapshot, key=lambda episode: episode.timestamp, reverse=True)[:top_k]

    async def recall_context(self, query: str, limit: int = 3) -> str:
        episodes = await self.recall(query, limit=limit)
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

    async def compact(self, *, max_episodes: int | None = None) -> int:
        limit = self.max_episodes if max_episodes is None else _normalize_max_episodes(max_episodes)
        if limit is None:
            return 0
        async with self._lock:
            if len(self._episodes) <= limit:
                return 0
            removed = len(self._episodes) - limit
            self._episodes = self._episodes[-limit:]
            return removed

    def _find_duplicate_locked(self, candidate: EpisodicEpisode) -> EpisodicEpisode | None:
        if self.dedupe_window <= 0:
            return None
        if not self._episodes:
            return None
        needle = dedupe_key(candidate)
        for existing in reversed(self._episodes[-self.dedupe_window:]):
            if dedupe_key(existing) == needle:
                return existing
        return None

    def _prune_locked(self) -> None:
        limit = self.max_episodes
        if limit is None:
            return
        if len(self._episodes) > limit:
            self._episodes = self._episodes[-limit:]


def _normalize_max_episodes(value: int | None) -> int | None:
    if value is None:
        return None
    parsed = to_int(value, DEFAULT_MAX_EPISODES)
    if parsed <= 0:
        return None
    return parsed
