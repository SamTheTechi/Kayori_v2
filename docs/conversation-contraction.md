# Conversation Contraction

This document explains how older chat history is summarized and converted into
episodic facts.

## Purpose

`ConversationContractionService` in
[`src/core/conversation_contraction.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/core/conversation_contraction.py)
owns conversation-history compaction.

Its job is to:

- detect when a thread should compact,
- summarize older history into one synthetic message,
- extract durable facts for episodic memory,
- and write the compacted history back into the state store.

This service is separate from the orchestrator so the compaction workflow has
one clear home.

## Public Methods

The current public API is:

- `maybe_compact(...)`
- `compact(...)`

The lower-level LLM step is private:

- `_contract_messages(...)`

That split is intentional:

- `maybe_compact(...)` is the threshold gate
- `compact(...)` is the full workflow
- `_contract_messages(...)` is just the summarize-and-extract step

## High-Level Flow

### `maybe_compact(...)`

1. Read thread history length from the state store.
2. If it is at or below the threshold, do nothing.
3. If it is above the threshold, call `compact(...)`.

Current threshold:

- `COMPACT_THRESHOLD = 12`

### `compact(...)`

1. Load the full stored message history.
2. Detect whether the first message is already a compacted summary.
3. Separate older messages from the last recent turns.
4. Ask the model to produce:
   - one refreshed running summary
   - a list of episodic facts
5. Write the facts into episodic memory.
6. Replace the stored history with:
   - one synthetic summary `AIMessage`
   - the last recent raw messages

Current recent window:

- `COMPACT_KEEP_RECENT = 4`

That means the service keeps the last two user-assistant turns raw while
compressing older context.

## Synthetic Summary Message

The compacted summary is stored as an `AIMessage` with:

```python
additional_kwargs={"kayori_compacted": True}
```

That marker lets the service detect and refresh the running summary later
instead of repeatedly summarizing the summary as if it were normal dialogue.

## LLM Step

The actual model call lives in `_contract_messages(...)`.

It does three things:

1. render a plain-text transcript from the older message slice
2. prompt the model using
   [`src/templates/episodic_strength_template.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/templates/episodic_strength_template.py)
3. parse JSON from the model response

The response is expected to contain:

- `summary`
- `facts`

Each fact is normalized before being written to episodic memory.

## Why Contraction Also Extracts Facts

This service is intentionally doing two outputs from one model call:

- summarized old conversation history
- durable long-term facts

That is efficient because the model is already reading the same old messages.
It avoids a second pass over the same history slice.

## Runtime Use

The orchestrator currently uses this service in two ways:

- after each chat turn:
  - `maybe_compact(...)`
- when a scheduled compact event fires:
  - `compact(...)`

This gives both:

- immediate pressure relief when the active window grows too large
- delayed inactivity-based compaction

## Tradeoffs

### Good Parts

- one core service owns history contraction
- summary and episodic facts come from the same pass
- existing compacted summaries are refreshed instead of duplicated
- keeps recent turns raw for continuity

### Current Limits

- output is still parsed from JSON text rather than a stricter typed schema
- the compacted summary is stored as an `AIMessage`, which is pragmatic but not
  a distinct history object type
- the transcript renderer assumes plain human/assistant text messages

## File Reference

The implementation described here lives in
[`src/core/conversation_contraction.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/core/conversation_contraction.py).
