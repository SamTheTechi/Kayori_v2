# Backend Adapters

Backend adapters provide infrastructure services: message queuing, state storage, memory, and scheduling.

## Available Backend Adapters

| Category | Production | Development |
|----------|-----------|-------------|
| Message Bus | RedisMessageBus | InMemoryMessageBus |
| State Store | RedisStateStore | InMemoryStateStore |
| Episodic Memory | RedisEpisodicMemory | InMemoryEpisodicMemory |
| Scheduler | RedisSchedulerBackend | InMemorySchedulerBackend |

**Note:** Production uses Redis for everything. In-memory adapters are commented out in `main.py`.

---

## Message Bus

**Purpose:** Queue for asynchronous message processing

### Protocol

```python
class MessageBus(Protocol):
    async def publish(self, envelope: MessageEnvelope) -> None: ...
    async def consume(self) -> MessageEnvelope: ...
```

### RedisMessageBus

**How it works:**
- `publish()` → `LPUSH` to Redis list
- `consume()` → `BRPOP` from Redis list (blocking)

```python
bus = RedisMessageBus(
    redis_client=async_redis,
    queue_key="kayori:message_queue"
)
```

**Pros:**
✅ Persistent across restarts  
✅ Distributed (multiple consumers)  
✅ Simple queue semantics  

**Cons:**
❌ Requires Redis infrastructure  
❌ Single queue (no priority)  
❌ Messages lost if Redis down  

### InMemoryMessageBus

**How it works:**
- Python `asyncio.Queue` internally
- Volatile, lost on restart

```python
# bus = InMemoryMessageBus()  # Commented out
```

**Pros:**
✅ Zero dependencies  
✅ Fast (no network)  
✅ Perfect for testing  

**Cons:**
❌ Lost on restart  
❌ Single process only  
❌ Not for production  

---

## State Store

**Purpose:** Store conversation state, mood, life notes, user profiles

### Protocol

```python
class StateStore(Protocol):
    async def get_mood(self, thread_id: str) -> MoodState: ...
    async def set_mood(self, thread_id: str, mood: MoodState) -> None: ...
    async def get_history(self, thread_id: str) -> MessagesHistory: ...
    async def append_messages(self, thread_id: str, msgs: list) -> None: ...
    async def replace_messages(self, thread_id: str, msgs: list) -> None: ...
    async def get_life_profile(self) -> str: ...
    async def replace_life_profile(self, profile: str) -> None: ...
    async def get_life_notes(self, thread_id: str) -> list[LifeNote]: ...
    async def append_life_note(self, thread_id: str, note: LifeNote) -> None: ...
    # ... more methods
```

### RedisStateStore

**How it works:**
- Stores state as JSON in Redis keys
- Thread-isolated keys: `kayori:state:mood:{thread_id}`

**Key Structure:**
```
kayori:state:mood:{thread_id}       → MoodState JSON
kayori:state:history:{thread_id}    → MessagesHistory JSON
kayori:state:life_profile           → Profile text
kayori:state:life_notes:{thread_id} → LifeNote[] JSON
```

```python
state = RedisStateStore(redis_client=async_redis)
```

**Pros:**
✅ Persistent across restarts  
✅ Thread-isolated state  
✅ Atomic operations  
✅ Fast key-value access  

**Cons:**
❌ JSON serialization overhead  
❌ Large histories hit Redis memory  
❌ No relational queries  

### InMemoryStateStore

**How it works:**
- Python dicts internally
- Volatile, lost on restart

```python
# state = InMemoryStateStore()  # Commented out
```

**Pros:**
✅ Zero dependencies  
✅ Instant access  
✅ Perfect for testing  

**Cons:**
❌ Lost on restart  
❌ Single process only  
❌ Memory grows unbounded  

---

## Episodic Memory

**Purpose:** Long-term fact storage with semantic search

### Protocol

```python
class EpisodicMemoryBackend(Protocol):
    async def upsert(self, record_id: str, content: str, metadata: dict) -> None: ...
    async def search(self, query: str, limit: int) -> list[SearchResult]: ...
    async def list_ids(self) -> list[str]: ...
    async def fetch_records(self, ids: list[str]) -> list[Record]: ...
    async def delete(self, ids: list[str]) -> None: ...
```

### RedisEpisodicMemory

**How it works:**
- Uses RedisVL (Redis Vector Library)
- HNSW index for vector similarity search
- Embeddings from BAAI/bge-small-en-v1.5 (768 dimensions)

```python
memory_backend = RedisEpisodicMemory(
    redis_client=sync_redis,
    embedding=FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5"),
    index_name="kayori_episodic_idx",
    dimension=768
)
```

**Storage Format:**
```
Redis Hash: kayori:memory:episodic:{namespace}:{record_id}
  - record_id: "FM-abc123"
  - namespace: "kayori-episodic:thread123"
  - content: "fact: User likes Python\ncontext: ..."
  - metadata_json: {"fact": "...", "importance": 3, ...}
  - embedding: <binary vector>
```

**Retrieval Ranking:**
```python
score = (
    backend_score * 0.7 +      # Vector similarity
    importance * 0.2 +         # Importance (1-5 scale)
    confidence * 0.1           # Confidence (0-1 scale)
)
```

**Pros:**
✅ Semantic search (finds related facts)  
✅ Persistent storage  
✅ Automatic compaction  
✅ Importance/confidence ranking  

**Cons:**
❌ Requires Redis with RedisVL  
❌ Vector index uses significant RAM  
❌ Embedding model adds dependency  
❌ 768 dimensions × thousands of facts = memory heavy  

### InMemoryEpisodicMemory

**How it works:**
- Local vector database
- Uses sklearn or similar for similarity

```python
# memory_backend = InMemoryEpisodicMemory(embedding=embedding_model)  # Commented out
```

**Pros:**
✅ No Redis needed  
✅ Fast for small datasets  
✅ Perfect for testing  

**Cons:**
❌ Lost on restart  
❌ Doesn't scale  
❌ No distributed search  

---

## Scheduler Backend

**Purpose:** Store and retrieve scheduled triggers

### Protocol

```python
class SchedulerBackend(Protocol):
    async def push(self, trigger: Trigger) -> None: ...
    async def pop_due(self, now: float) -> list[Trigger]: ...
    async def reschedule(self, trigger: Trigger) -> None: ...
    async def suppress(self, trigger_id: str, until: float) -> None: ...
    async def remove(self, trigger_id: str) -> None: ...
    async def list_pending(self) -> list[Trigger]: ...
    async def restore(self) -> list[Trigger]: ...
```

### RedisSchedulerBackend

**How it works:**
- Stores triggers as JSON in Redis
- Polls for due triggers every 1 second
- Reschedules repeating triggers automatically

```python
scheduler_backend = RedisSchedulerBackend(redis_client=async_redis)
scheduler = AgentScheduler(backend=scheduler_backend, bus=bus)
```

**Trigger Storage:**
```
Redis key: kayori:scheduler:trigger:{trigger_id}
  → Trigger JSON with _scheduled_for timestamp
```

**Polling Loop:**
```python
while running:
    now = time.time()
    due_triggers = await backend.pop_due(now)
    for trigger in due_triggers:
        await dispatch(trigger)
    await asyncio.sleep(1.0)  # tick_interval
```

**Pros:**
✅ Persistent across restarts  
✅ Restore triggers on boot  
✅ Distributed (single consumer)  

**Cons:**
❌ Polling-based (not event-driven)  
❌ 1-second tick delay  
❌ Requires Redis  

### InMemorySchedulerBackend

**How it works:**
- Python list of triggers
- Volatile, lost on restart

```python
# scheduler_backend = InMemorySchedulerBackend()  # Commented out
```

**Pros:**
✅ Zero dependencies  
✅ Instant trigger firing  
✅ Perfect for testing  

**Cons:**
❌ Lost on restart  
❌ No distributed support  
❌ Not for production  

---

## Backend Adapter Pros and Cons (Overall)

### ✅ Strengths

**Protocol-Based Design**
- Core logic doesn't know about Redis
- Swap backends without code changes
- Test with in-memory implementations

**Redis Unification**
- Single infrastructure dependency
- All state in one place
- Easier to monitor and backup

**Persistence**
- State survives restarts
- Triggers restored on boot
- Memories persist across sessions

**Thread Isolation**
- Per-thread state in Redis keys
- No cross-talk between conversations
- Scalable to many users

### ❌ Limitations

**Redis Dependency**
- Single point of failure
- Requires Redis infrastructure
- RedisVL adds complexity
- Memory limits for large deployments

**No In-Memory Production Path**
- In-memory adapters commented out
- Effectively requires Redis
- Development needs Redis too

**Serialization Overhead**
- JSON encode/decode on every access
- Large histories hit performance
- No compression

**Limited Query Capabilities**
- Key-value only (no SQL)
- Can't query across threads
- Hard to analyze state

**Vector Search Memory**
- 768 dims × 10k facts = ~30MB RAM
- Grows linearly with facts
- No pagination support

---

## Configuration

```env
# Redis
REDIS_URL=redis://localhost:6379

# All backends use same Redis instance
# No separate configuration per backend
```

---

## When to Use Which Backend

### Production
- **Always Redis**: Persistence, distributed, reliable

### Development
- **Redis still recommended**: Matches production behavior
- **In-memory okay for**: Quick tests, CI pipelines

### Testing
- **In-memory preferred**: Fast, isolated, no setup
- **Mock protocols**: Even faster, full control

---

## Key Takeaways

1. **Protocols enable swapping**: Core doesn't care about implementation
2. **Redis is production standard**: All backends use it
3. **In-memory exists for testing**: But commented out in main.py
4. **Thread isolation via keys**: `{prefix}:{thread_id}` pattern
5. **Persistence matters**: Survives restarts, restores state

---

## Related

- [Input Adapters](input.md) - Platform adapters
- [Output Adapters](output.md) - Platform adapters
- [Episodic Memory](../episodic-memory.md) - Memory system details
- [Architecture](../architecture.md) - Overall system design
