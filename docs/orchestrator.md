# Orchestrator

The `AgentOrchestrator` coordinates all runtime services.

## What It Does

Think of the orchestrator as a **conductor** managing:
- Consuming messages from the bus
- Routing by type (chat, life reflection, history cleanup)
- Coordinating mood, memory, and agent response
- Managing one personal conversation state
- Scheduling proactive tasks

## Message Flow

```
1. Consume message from bus
2. Route by source:
   - LIFE → Run internal reflection
   - COMPACT → Cleanup history
   - Other → Handle chat (main path)
```

## Chat Turn Path (Main Flow)

When a user message arrives:

```
1. Load context (mood + last 12 messages)
2. Analyze mood change (LLM classifies emotions)
3. Recall memories (2 relevant facts from episodic storage)
4. Generate reply (Chat Agent with tools)
5. Persist turn (save user message + bot response)
6. Schedule history cleanup (after 30 min inactivity)
7. Cleanup now if history > 12 messages
8. Send response to user
```

## Key Constants

```python
AGENT_WINDOW = 12        # Messages sent to agent
MOOD_WINDOW = 4          # Messages for mood analysis
COMPACT_IDLE_SECONDS = 1800  # Wait 30 min before compacting
```

## Source Routing

Three message types:

| Source | Handler | Purpose |
|--------|---------|---------|
| `LIFE` | `_handle_life()` | Internal reflection |
| `COMPACT` | `_handle_compact()` | History cleanup |
| Others | `_handle_chat()` | Normal conversation |

## Life Reflection

Runs every 20 seconds (configurable):
1. Loads recent conversation summary
2. Loads relevant memories
3. Loads user's life profile
4. Life Agent reflects and generates life note
5. Stores note if noteworthy

## History Compaction

Two triggers:
- **Immediate**: If history > 12 messages after a turn
- **Scheduled**: After 30 minutes of inactivity

Process:
1. Summarize old messages into running summary
2. Extract important facts to episodic memory
3. Replace old messages with summary + keep last 4 raw

## Pros and Cons

### ✅ Strengths

**Clear Coordination**
- Single place for runtime logic
- Delegates to specialized services
- Easy to understand flow

**Personal-Agent Simplicity**
- One state model for one user
- No thread routing overhead
- Easier to reason about continuity

**Proactive Design**
- Background reflection
- Automatic history management
- Customizable scheduling

**Error Resilient**
- Failures logged with context
- One component failing doesn't crash system
- Graceful degradation

### ❌ Limitations

**Sequential Steps**
- `_handle_chat()` runs 8 steps in sequence
- Each step blocks next
- Could be more parallel

**Tight Coupling**
- Knows about compact trigger policy
- Manages scheduler directly
- Could be more event-driven

**Life Reflection Frequency**
- 20 seconds seems very frequent
- May generate redundant notes
- No adaptive scheduling

**Limited Testing**
- Complex coordination logic untested
- Edge cases unverified
- No integration tests

---

## File Reference

[`src/core/orchestrator.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/src/core/orchestrator.py)
