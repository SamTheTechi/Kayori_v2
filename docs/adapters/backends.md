# Backend Adapters

Backend adapters implement infrastructure services for bus, state, episodic memory, and scheduling.

## Available Backend Adapters

| Category | Implementations |
|----------|-----------------|
| Message Bus | `RedisMessageBus`, `InMemoryMessageBus` |
| State Store | `RedisStateStore`, `InMemoryStateStore` |
| Episodic Memory Backend | `RedisEpisodicMemory`, `InMemoryEpisodicMemory`, `PineconeEpisodicMemory` |
| Scheduler Backend | `RedisSchedulerBackend`, `InMemorySchedulerBackend` |

The current runtime in `main.py` wires Redis for bus, state, scheduler, and episodic memory.

## Message Bus

Protocol:

```python
class MessageBus(Protocol):
    async def publish(self, envelope: MessageEnvelope) -> None: ...
    async def consume(self) -> MessageEnvelope: ...
```

### RedisMessageBus

Current behavior:
- `publish()` serializes the envelope and `LPUSH`es it to the queue key
- `consume()` blocks on `BRPOP` and reconstructs `MessageEnvelope`
- default queue key is `kayori:message_queue`

### InMemoryMessageBus

Current behavior:
- wraps an `asyncio.Queue`
- keeps all messages in-process only

## State Store

Protocol:

```python
class StateStore(Protocol):
    async def get_mood(self) -> MoodState: ...
    async def set_mood(self, mood: MoodState) -> None: ...
    async def get_history(self) -> MessagesHistory: ...
    async def append_messages(self, msgs: list[BaseMessage]) -> None: ...
    async def replace_messages(self, msgs: list[BaseMessage]) -> None: ...
    async def get_interaction_state(self) -> InteractionState: ...
    async def set_interaction_state(self, state: InteractionState) -> None: ...
    async def get_life_profile(self) -> str: ...
    async def replace_life_profile(self, profile: str) -> None: ...
    async def get_life_notes(self) -> list[LifeNote]: ...
    async def append_life_note(self, note: LifeNote) -> None: ...
    async def consume_life_note(self) -> LifeNote | None: ...
    async def prune_life_notes(self, *, max_age_seconds: float) -> int: ...
```

### RedisStateStore

Current behavior:
- stores mood, history, interaction state, life profile, and life notes as Redis keys
- preserves a compacted summary message at the front of history when present
- includes a legacy mood hash migration path

Current key prefixes:
- `kayori:state:mood`
- `kayori:state:history`
- `kayori:state:interaction`
- `kayori:state:life_profile`
- `kayori:state:life_notes`

This store is global in the current runtime. It is not partitioned by thread or channel.

### InMemoryStateStore

Current behavior:
- stores the same state model in Python objects guarded by an `asyncio.Lock`
- is process-local and non-persistent

## Episodic Memory Backend

Protocol:

```python
class EpisodicMemoryBackend(Protocol):
    async def upsert(...): ...
    async def search(...): ...
    async def list_ids(...): ...
    async def fetch_records(...): ...
    async def delete(...): ...
```

### RedisEpisodicMemory

Current behavior:
- stores records in Redis hashes under `kayori:memory:episodic:{namespace}:{record_id}`
- uses `redisvl` for vector indexing and search
- stores `record_id`, `namespace`, `content`, `metadata_json`, and `embedding`
- creates the search index if it does not already exist

### PineconeEpisodicMemory

Current behavior:
- creates a Pinecone index when missing
- uses `PineconeVectorStore` for async similarity search
- supports the same backend protocol shape as the Redis implementation

### InMemoryEpisodicMemory

Current behavior:
- stores records and vectors in Python dictionaries
- computes cosine similarity in-process
- is useful for testing or small local runs

## Scheduler Backend

Protocol:

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

Current behavior:
- stores trigger payloads as JSON at `scheduler:trigger:{trigger_id}`
- stores due-ordering in the sorted set `scheduler:heap`
- stores suppression timestamps in `scheduler:suppress`
- `pop_due()` removes or requeues due triggers based on suppression state

### InMemorySchedulerBackend

Current behavior:
- stores triggers in a min-heap
- keeps suppression state in a dict
- does not persist across restarts

## Configuration

Current production backend wiring uses:

```env
REDIS_URL=redis://localhost:6379
```

Pinecone support additionally requires the corresponding API credentials if that backend is selected in code.

## File References

- [`gateway/bus/redis_bus.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/bus/redis_bus.py)
- [`gateway/bus/in_memory.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/bus/in_memory.py)
- [`gateway/state/redis.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/state/redis.py)
- [`gateway/state/in_memory.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/state/in_memory.py)
- [`gateway/memory/redis.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/memory/redis.py)
- [`gateway/memory/in_memory.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/memory/in_memory.py)
- [`gateway/memory/pinecone.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/memory/pinecone.py)
- [`gateway/scheduler/redis.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/scheduler/redis.py)
- [`gateway/scheduler/in_memory.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/scheduler/in_memory.py)

## Related

- [Input Adapters](input.md)
- [Output Adapters](output.md)
- [Episodic Memory](../episodic-memory.md)
- [Architecture](../architecture.md)
