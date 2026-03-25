# Orchestrator

This document explains what the orchestrator does today and how it ties the
core runtime services together.

## Purpose

`AgentOrchestrator` in
[`src/core/orchestrator.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/core/orchestrator.py)
is the runtime coordinator.

It is responsible for:

- consuming inbound envelopes from the bus,
- resolving the conversation thread,
- routing internal sources like `LIFE` and `COMPACT`,
- running the normal chat turn pipeline,
- rescheduling inactivity-based compaction,
- and sending outbound replies through the output sink.

It is not the place where long prompt logic, mood classification logic, or
history contraction logic live. It coordinates those services.

## High-Level Flow

1. Consume one `MessageEnvelope` from the bus.
2. Resolve `thread_id`.
3. Route by `MessageSource`.
4. For normal chat:
   - load mood and recent history
   - analyze mood delta
   - recall episodic memory
   - call the agent
   - persist the turn
   - reschedule compact-after-inactivity
   - maybe compact immediately if history is already too large
   - send the outbound reply

## Source Routing

The current orchestrator has three branches:

- `MessageSource.LIFE`
  - handled by `_handle_life(...)`
- `MessageSource.COMPACT`
  - handled by `_handle_compact(...)`
- everything else
  - handled by `_handle_chat(...)`

This keeps the entrypoint small while letting internal runtime events bypass the
normal conversational path.

## Chat Turn Path

The normal chat path is in `_handle_chat(...)`.

### 1. Load Short-Term State

The orchestrator pulls:

- current `MoodState`
- recent agent window
- recent mood-analysis window

Those windows are intentionally small:

- `AGENT_WINDOW = 12`
- `MOOD_WINDOW = 4`

### 2. Update Mood

The orchestrator asks the mood engine to:

- analyze the latest user message against recent context
- apply that delta to the current mood state

The updated mood is then written back into the state store before reply
generation.

### 3. Recall Episodic Memory

The orchestrator asks the episodic memory store for a small number of relevant
facts:

```python
facts = await self.episodic_memory.recall(query=content, limit=2)
```

Those recalled records are then passed into the agent graph so prompt shaping
can decide what to expose.

### 4. Generate Reply

Reply generation is delegated to
[`src/agent/service.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/agent/service.py).

The orchestrator passes:

- current content
- recent messages
- recalled episodic records
- updated mood
- original envelope

### 5. Persist Raw Turn

The orchestrator appends:

- `HumanMessage(content=content)`
- `AIMessage(content=reply_text)`

to the state store before any later contraction happens.

This matters because contraction should operate on real stored history, not on
temporary in-flight values.

### 6. Reschedule Compact-After-Inactivity

After the turn is stored, the orchestrator resets a one-shot compact trigger
for that thread.

Current behavior:

- one pending compact trigger per thread
- stable trigger id: `compact:{thread_id}`
- delay: `COMPACT_IDLE_SECONDS`
- trigger source: `MessageSource.COMPACT`

This gives "compact after inactivity" behavior instead of a repeating compact
job.

### 7. Opportunistic Compaction

The orchestrator also calls the contraction service's `maybe_compact(...)`
method after each chat turn.

This means history can compact immediately if it is already above the active
threshold, instead of waiting only for the idle timer.

### 8. Send Outbound Reply

If the final reply text is not empty, the orchestrator builds an
`OutboundMessage` and passes it to the configured output adapter.

The helper `_build_outbound(...)` carries through:

- source
- content
- channel / target user ids
- reply-to message id
- envelope metadata

## Scheduled Compaction Path

When a scheduled compact trigger fires, the orchestrator does not run a normal
chat turn.

Instead it calls:

```python
await self.conversation_contraction.compact(...)
```

That path bypasses the threshold gate because the scheduler already decided it
was time to compact.

## Tradeoffs

### Good Parts

- central place for runtime coordination
- clear source-based dispatch
- keeps other services focused on their own domain logic
- inactivity-based compaction lives near the chat activity signal

### Current Limits

- `_handle_chat(...)` still owns several sequential steps
- `LIFE` handling is still just a stub
- scheduler integration means the orchestrator knows about compact-trigger
  policy directly

## File Reference

The implementation described here lives in
[`src/core/orchestrator.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/core/orchestrator.py).
