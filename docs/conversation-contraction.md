# Conversation Contraction

Summarizes old chat history and extracts facts for long-term storage.

## What It Does

Prevents context overflow by:
- Summarizing older messages into a running compacted summary
- Extracting facts for episodic memory in the same model call
- Keeping recent messages raw
- Replacing old history with a marked `SystemMessage` plus recent turns

## How It Works

### Two Methods

**1. maybe_compact()** - Threshold gate
```python
await contraction.maybe_compact(
    state_store=state,
    episodic_memory=memory
)
```

**2. compact()** - Full compaction
```python
await contraction.compact(
    state_store=state,
    episodic_memory=memory
)
```

### Compaction Process

```
1. Load full history
2. Detect an existing compacted summary in the first message
3. Split old messages from the most recent four raw messages
4. Run one model call that returns JSON with `summary` and `facts`
5. Normalize and store extracted facts in episodic memory
6. Replace history with a marked summary message plus the recent messages
```

## Key Constants

```python
COMPACT_THRESHOLD = 12       # Trigger at 12 messages
COMPACT_KEEP_RECENT = 4      # Keep last 4 messages raw
COMPACTED_KEY = "kayori_compacted"
```

## Example

**Before compaction (12 messages):**
```
User: Hi!
Bot: Hello!
User: I love Python
Bot: Me too!
... (8 more messages)
User: What's your favorite library?
```

**After compaction:**
```
[System: Summary of first 8 messages...]
User: What's your favorite library?
Bot: I think...
User: Tell me more
Bot: Sure!
```

**Extracted facts:**
```python
[
    {
        "fact": "User loves Python",
        "category": "preference",
        "importance": 4,
        "confidence": 0.9
    }
]
```

## LLM Summarization

The model receives:
```
Existing summary: (previous summary or empty)
Messages:
  user: Hi!
  assistant: Hello!
  ...

Output JSON:
{
  "summary": "User greeted bot, mentioned Python love...",
  "facts": [
    {
      "fact": "User loves Python",
      "category": "preference",
      "importance": 4,
      "confidence": 0.9,
      "tags": ["programming"],
      "context": "Mentioned in greeting"
    }
  ]
}
```

If the model call fails, returns invalid JSON, or produces an empty summary, compaction exits without replacing history.

## Synthetic Summary Message

Stored as marked `SystemMessage`:
```python
SystemMessage(
    content="Summary text...",
    additional_kwargs={"kayori_compacted": True}
)
```

## When Compaction Happens

- After each chat turn through `maybe_compact()`
- Through the scheduled `COMPACT` envelope handled by the orchestrator

## Runtime Usage

From orchestrator:
```python
await conversation_contraction.maybe_compact(
    state_store=state,
    episodic_memory=episodic_memory
)

await conversation_contraction.compact(
    state_store=state,
    episodic_memory=episodic_memory
)
```

## File Reference

[`src/core/conversation_contraction.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/src/core/conversation_contraction.py)
