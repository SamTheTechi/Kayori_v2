# Episodic Memory

This document explains how episodic memory works in the current runtime.

## Purpose

`EpisodicMemoryStore` in
[`src/core/episodic_memory.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/core/episodic_memory.py)
is the long-term fact memory layer.

Its job is to:

- store durable facts about the user or relationship,
- retrieve the most relevant facts for the current turn,
- and trim stored memory when the backend grows too large.

It is intentionally backend-agnostic. Storage and search are delegated to an
`EpisodicMemoryBackend`.

## High-Level API

The store exposes three main operations:

- `remember(...)`
- `recall(...)`
- `compact(...)`

This keeps the runtime-facing interface small.

## Remember

`remember(...)` takes a fact payload and normalizes it into a stored record.

Current fields:

- `fact`
- `source`
- `category`
- `importance`
- `confidence`
- `tags`
- `context`

The store then writes that record to the backend as:

- metadata for exact stored values
- a rendered text blob for semantic search

That rendered text includes:

- fact
- context
- category
- tags
- source

This design keeps the backend simple while still letting vector search work on
more than just the raw fact string.

## Recall

`recall(query, limit, min_score)` retrieves candidate records from the backend
and re-ranks them in the store layer.

The current ranking combines:

- backend relevance score
- importance
- confidence

The weighting is intentionally simple:

- backend score gets most of the weight
- importance boosts durable memories
- confidence prevents uncertain facts from ranking too highly

This is why the store returns better results than a pure backend similarity
query alone.

## Compact

`compact(...)` limits how many stored episodic records remain in the backend.

The current eviction logic uses:

- age
- importance
- confidence

Older and weaker records are deleted first. More important and more confident
records are kept longer.

This is separate from conversation-history compaction. Here the store is
compacting long-term facts, not chat messages.

## Categories

Allowed fact categories are:

- `identity`
- `preference`
- `relationship`
- `profile`
- `schedule`
- `goal`
- `possession`
- `misc`

Unknown categories are normalized to `misc`.

## Backend Split

The store depends on the backend protocol from
[`src/shared_types/protocol.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/shared_types/protocol.py),
not on Pinecone or Redis directly.

Current backend implementations live in:

- [`src/adapters/memory/in_memory.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/adapters/memory/in_memory.py)
- [`src/adapters/memory/redis.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/adapters/memory/redis.py)
- [`src/adapters/memory/pinecone.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/adapters/memory/pinecone.py)

That means higher-level runtime code can keep using one store interface while
changing storage backends underneath.

## Runtime Use

The orchestrator currently uses episodic memory in two places:

- `recall(...)` before reply generation
- `remember(...)` indirectly through conversation contraction when old history
  is summarized into durable facts

This keeps long-term memory connected to both live chat and delayed
consolidation.

## Tradeoffs

### Good Parts

- backend-agnostic API
- small runtime-facing surface
- retrieval ranking is better than raw vector similarity alone
- durable fact categories fit companion-style memory well

### Current Limits

- record shape is still plain dicts, not stricter models
- ranking weights are fixed in code
- no dedupe layer beyond record id uniqueness

## File Reference

The implementation described here lives in
[`src/core/episodic_memory.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/core/episodic_memory.py).
