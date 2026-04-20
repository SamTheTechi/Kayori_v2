# Orchestrator

The `AgentOrchestrator` coordinates all runtime services.

## What It Does

The orchestrator is the runtime entrypoint after messages leave the bus. It is responsible for:
- Consuming messages from the bus
- Coalescing adjacent inbound envelopes when possible
- Routing by `MessageEnvelope.source`
- Coordinating mood analysis, episodic recall, agent response, and state updates
- Rescheduling background compaction
- Delivering outbound messages through the output sink

## Message Flow

```
1. Consume message from bus
2. Route by source:
   - LIFE → Run internal reflection
   - COMPACT → Run conversation compaction
   - PROACTIVE → Run proactive chat path
   - Other → Run chat path
```

## Chat Turn Path (Main Flow)

For normal inbound chat messages:

```
1. Normalize inbound content, including STT for audio envelopes
2. Load mood state and recent agent context
3. Run mood analysis for non-proactive turns
4. Recall relevant episodic facts
5. Generate a reply with the chat agent
6. Persist messages and update interaction state
7. Reschedule the compaction trigger
8. Run `maybe_compact()` on the active history
9. Build and send the outbound message
```

## Key Constants

```python
AGENT_WINDOW = 12
MOOD_WINDOW = 4
COMPACT_IDLE_SECONDS = 1800
MESSAGE_COALESCE_WINDOW_SECONDS = 0.5
MAX_PENDING_LIFE_NOTES = 3
```

## Source Routing

Current routing paths:

| Source | Handler | Purpose |
|--------|---------|---------|
| `LIFE` | `_handle_life()` | Internal reflection |
| `COMPACT` | `_handle_compact()` | History cleanup |
| `PROACTIVE` | `_handle_proactive()` | Self-initiated outreach |
| Others | `_handle_chat()` | Normal conversation |

## Life Reflection

The life path:
1. Prunes expired life notes
2. Skips work if too many life notes are already pending
3. Loads the compacted conversation summary, life profile, and recent episodic recall
4. Calls the life agent to generate a note
5. Stores the note if the life agent returned one

## Proactive Path

The proactive path is gated by interaction state and current mood:
- Uses the average of `Trust`, `Attachment`, and `Confidence` to compute a daily send cap
- Stops if there is no known route source, the cap is exhausted, or the user has ignored recent proactive messages
- Re-enters the chat path with a synthetic `PROACTIVE` envelope and then routes the final outbound reply back to the last known chat source

## History Compaction

Compaction happens in two places:
- Immediately after a chat turn via `maybe_compact()`
- Later through the scheduled `COMPACT` trigger

The compaction service is responsible for summarizing older history, extracting facts into episodic memory, and replacing old messages with a compacted summary plus recent raw messages.

## File Reference

[`src/core/orchestrator.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/src/core/orchestrator.py)
