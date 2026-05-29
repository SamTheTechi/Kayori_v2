# Episodic Memory

Long-term fact storage with semantic search.

## What It Does

Stores durable facts about users and retrieves relevant ones during conversations:
- Stores normalized fact records
- Retrieves relevant records through the configured backend
- Ranks recall results with similarity, importance, and confidence
- Compacts old records when a maximum episode count is set

## How It Works

### Three Operations

**1. remember()** - Store a fact
```python
await memory.remember(
    fact="User loves Python",
    source="conversation",
    category="preference",
    importance=4,
    confidence=0.9,
    tags=["programming", "python"]
)
```

**2. recall()** - Find relevant facts
```python
facts = await memory.recall(
    query="What does the user like?",
    limit=3,
)
```

**3. compact()** - Cleanup old facts
```python
await memory.compact(
    max_episodes=250
)
```

## Fact Structure

```python
{
    "id": "FM-abc123",
    "timestamp": "2026-04-04T10:30:00+00:00",
    "fact": "User is learning Python",
    "source": "conversation",
    "category": "preference",
    "importance": 4,          # 1-5 scale
    "confidence": 0.9,        # 0.0-1.0
    "tags": ["programming"],
    "context": "Mentioned during chat"
}
```

## Categories

- `identity` - Who the user is
- `preference` - What they like
- `relationship` - Connection to assistant
- `profile` - Background info
- `schedule` - Time-based info
- `goal` - What they're working toward
- `possession` - What they have
- `misc` - Everything else

## Retrieval Ranking

Recall ranking uses:
```python
score = (
    similarity * 0.7
    + importance * 0.2
    + confidence * 0.1
)
```

The backend score is converted from distance to similarity with:

```python
similarity = 1.0 / (1.0 + distance)
```

## Compaction (Cleanup)

When the number of stored records exceeds the configured maximum:
1. List all IDs in the namespace
2. Fetch records in batches
3. Sort records by timestamp
4. Compute an eviction score from age and record weakness
5. Delete the overflow records with the highest eviction score

## Backend Implementation

`EpisodicMemoryStore` depends on the `EpisodicMemoryBackend` protocol. Backend selection is handled outside the store.

## Runtime Usage

**Orchestrator recalls before each turn:**
```python
facts = await episodic_memory.recall(
    query=user_message,
    limit=2,
)
```

**Conversation contraction extracts facts:**
```python
for fact in extracted_facts:
    await episodic_memory.remember(
        fact=fact["fact"],
        source="conversation",
        category=fact["category"],
        importance=fact["importance"]
    )
```

## File Reference

[`agent/memory/episodic_memory.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/agent/memory/episodic_memory.py)
