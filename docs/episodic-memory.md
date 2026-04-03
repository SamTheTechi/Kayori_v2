# Episodic Memory

Long-term fact storage with semantic search.

## What It Does

Stores durable facts about users and retrieves relevant ones during conversations:
- 💾 Remembers facts (name, preferences, goals)
- 🔍 Finds relevant memories via semantic search
- 🧹 Automatically cleans up old/weak memories
- 📂 Categorizes facts (identity, preference, relationship, etc.)

## How It Works

### Three Operations

**1. remember()** - Store a fact
```python
await memory.remember(
    thread_id="user123",
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
    thread_id="user123"
)
# Returns top 3 relevant facts ranked
```

**3. compact()** - Cleanup old facts
```python
await memory.compact(
    thread_id="user123",
    max_episodes=250  # Keep max 250 facts
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

Facts ranked by combining:
```python
score = (
    backend_score * 0.7 +      # Vector similarity (70%)
    importance * 0.2 +         # Importance score (20%)
    confidence * 0.1           # Confidence (10%)
)
```

**Why this works:**
- Semantic search finds related facts
- Importance boosts durable memories
- Confidence prevents uncertain facts from ranking high

## Compaction (Cleanup)

When memory exceeds limit (default 250 facts):

**Eviction score combines:**
- **Age**: Older facts more likely to delete
- **Weakness**: Low importance + confidence
- **Formula**: `(age * 0.7) + (weakness * 0.3)`

**Process:**
1. Sort facts by eviction score
2. Delete lowest-scoring facts
3. Keep most important/confident/recent

## Backend Implementation

Uses **RedisVL** (Redis Vector Library):
- HNSW index for vector similarity
- BAAI/bge-small-en-v1.5 embeddings (768 dims)
- Stored as Redis hashes with vector field

```python
memory_backend = RedisEpisodicMemory(
    redis_client=sync_redis,
    embedding=FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5"),
    dimension=768
)
```

## Runtime Usage

**Orchestrator recalls before each turn:**
```python
facts = await episodic_memory.recall(
    query=user_message,
    limit=2,
    thread_id=thread_id
)
# Pass to agent for context
```

**Conversation contraction extracts facts:**
```python
# When compacting history
for fact in extracted_facts:
    await episodic_memory.remember(
        thread_id=thread_id,
        fact=fact["fact"],
        source="conversation",
        category=fact["category"],
        importance=fact["importance"]
    )
```

## Pros and Cons

### ✅ Strengths

**Semantic Search**
- Finds related facts, not exact matches
- Better than keyword search
- Understands meaning

**Smart Ranking**
- Combines similarity + importance + confidence
- Important facts stay accessible
- Uncertain facts rank lower

**Automatic Cleanup**
- Prevents unbounded growth
- Deletes old/weak facts first
- Keeps memory efficient

**Backend Agnostic**
- Protocol-based design
- Works with Redis or in-memory
- Easy to swap storage

**Categorization**
- Organized fact types
- Useful for filtering
- Clear semantics

### ❌ Limitations

**No Deduplication**
- Similar facts stored separately
- Can have duplicates
- No merging logic

**Fixed Ranking Weights**
- 70/20/10 hardcoded
- No learning from feedback
- May not suit all use cases

**Vector Search Memory**
- 768 dims × 250 facts = ~1MB RAM
- Grows with fact count
- Can hit Redis memory limits

**Simple Categories**
- Manual categorization
- No auto-classification
- "misc" becomes catch-all

**Record Shape**
- Plain dicts, not strict models
- No validation
- Easy to misuse

---

## File Reference

[`src/core/episodic_memory.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/src/core/episodic_memory.py)
