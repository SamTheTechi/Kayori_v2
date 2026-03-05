from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import redis.asyncio as redis

from memory.episodic_memory import (
    DEFAULT_DEDUPE_WINDOW,
    DEFAULT_MAX_EPISODES,
    DEFAULT_RECALL_MIN_SCORE,
    EpisodicEpisode,
    build_episode,
    dedupe_key,
    episode_from_mapping,
    episode_score,
    to_int,
)


class RedisEpisodicMemoryStore:
    def __init__(
        self,
        redis_url: str,
        *,
        list_key: str = "kayori:memory:episodic:list",
        max_episodes: int | None = DEFAULT_MAX_EPISODES,
        dedupe_window: int = DEFAULT_DEDUPE_WINDOW,
    ) -> None:
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._list_key = list_key
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
            duplicate = await self._find_duplicate_locked(episode)
            if duplicate is not None:
                return duplicate

            raw = json.dumps(episode.to_dict(), separators=(",", ":"), ensure_ascii=False)
            pipe = self._client.pipeline()
            pipe.rpush(self._list_key, raw)
            if self.max_episodes is not None:
                pipe.ltrim(self._list_key, -self.max_episodes, -1)
            await pipe.execute()
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

        episodes = await self._load_all()
        if not query.strip():
            return sorted(episodes, key=lambda ep: ep.timestamp, reverse=True)[:top_k]

        scored = [(episode_score(ep, query, now), ep) for ep in episodes]
        ranked = sorted(
            [item for item in scored if item[0] >= threshold],
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked:
            return sorted(episodes, key=lambda ep: ep.timestamp, reverse=True)[:top_k]
        return [ep for _, ep in ranked[:top_k]]

    async def recent(self, limit: int = 5) -> list[EpisodicEpisode]:
        top_k = max(1, min(100, to_int(limit, 5)))
        raws = await self._client.lrange(self._list_key, -top_k, -1)
        out: list[EpisodicEpisode] = []
        for raw in reversed(raws):
            episode = _decode_episode(raw)
            if episode is not None:
                out.append(episode)
        return out

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
            length = await self._client.llen(self._list_key)
            if length <= limit:
                return 0
            removed = length - limit
            await self._client.ltrim(self._list_key, -limit, -1)
            return removed

    async def _find_duplicate_locked(self, candidate: EpisodicEpisode) -> EpisodicEpisode | None:
        if self.dedupe_window <= 0:
            return None
        raws = await self._client.lrange(self._list_key, -self.dedupe_window, -1)
        if not raws:
            return None
        needle = dedupe_key(candidate)
        for raw in reversed(raws):
            existing = _decode_episode(raw)
            if existing is None:
                continue
            if dedupe_key(existing) == needle:
                return existing
        return None

    async def _load_all(self) -> list[EpisodicEpisode]:
        raws = await self._client.lrange(self._list_key, 0, -1)
        out: list[EpisodicEpisode] = []
        for raw in raws:
            episode = _decode_episode(raw)
            if episode is not None:
                out.append(episode)
        return out


def _decode_episode(raw: str) -> EpisodicEpisode | None:
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return episode_from_mapping(payload)


def _normalize_max_episodes(value: int | None) -> int | None:
    if value is None:
        return None
    parsed = to_int(value, DEFAULT_MAX_EPISODES)
    if parsed <= 0:
        return None
    return parsed
