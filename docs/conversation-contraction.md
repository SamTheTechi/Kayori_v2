# Conversation Contraction

Summarizes old chat history and extracts facts for long-term storage.

## What It Does

Prevents context overflow by:
- 📝 Summarizing older messages into compact summary
- 💡 Extracting important facts to episodic memory
- 🧹 Keeping recent messages raw for continuity
- ⚡ Triggering after inactivity or when history gets too long

## How It Works

### Two Methods

**1. maybe_compact()** - Threshold gate
```python
# Only compacts if history > 12 messages
await contraction.maybe_compact(
    thread_id="user123",
    state_store=state,
    episodic_memory=memory
)
```

**2. compact()** - Full compaction
```python
# Always compacts (bypasses threshold)
await contraction.compact(
    thread_id="user123",
    state_store=state,
    episodic_memory=memory
)
```

### Compaction Process

```
1. Load full history
2. Detect existing summary (if any)
3. Split: old messages vs recent (keep last 4)
4. LLM summarizes old messages + extracts facts
5. Write facts to episodic memory
6. Replace history with: [summary] + [recent 4 messages]
```

## Key Constants

```python
COMPACT_THRESHOLD = 12       # Trigger at 12 messages
COMPACT_KEEP_RECENT = 4      # Keep last 4 messages raw
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

**Why one call for both?**
- Model already reading old messages
- Avoids second pass
- Efficient single LLM call

## Synthetic Summary Message

Stored as marked `SystemMessage`:
```python
SystemMessage(
    content="Summary text...",
    additional_kwargs={"kayori_compacted": True}
)
```

**Why SystemMessage?**
- Not presented as bot's prior reply
- Marker prevents re-summarizing
- Clear separation from dialogue

## When Compaction Happens

**Two triggers:**

1. **After each chat turn** (maybe_compact)
   - Only if history > 12 messages
   - Immediate pressure relief

2. **After 30 min inactivity** (scheduled compact)
   - Bypasses threshold
   - Delayed cleanup

**Why both?**
- Immediate: Prevents context overflow
- Scheduled: Cleans up even short conversations

## Runtime Usage

From orchestrator:
```python
# After each chat turn
await conversation_contraction.maybe_compact(
    thread_id=thread_id,
    state_store=state,
    episodic_memory=episodic_memory
)

# When scheduled compact fires
await conversation_contraction.compact(
    thread_id=thread_id,
    state_store=state,
    episodic_memory=episodic_memory
)
```

## Pros and Cons

### ✅ Strengths

**Dual Output**
- Summary + facts from one call
- Efficient single LLM invocation
- No redundant processing

**Threshold Gate**
- maybe_compact prevents unnecessary work
- Only compacts when needed
- Saves API costs

**Summary Refresh**
- Detects existing summary
- Updates instead of duplicating
- Running summary stays current

**Recent Window**
- Keeps last 4 messages raw
- Maintains conversational continuity
- Doesn't over-compress

**SystemMessage Marker**
- Clear separation from dialogue
- Prevents re-summarizing summary
- Clean implementation

### ❌ Limitations

**JSON Parsing**
- Relies on model outputting valid JSON
- No strict schema validation
- Can fail silently

**Fixed Thresholds**
- 12 messages may not suit all cases
- No dynamic threshold based on complexity
- One size fits all

**Summary Quality**
- Depends on LLM summarization
- May lose nuance
- No user control over what's kept

**Transcript Assumptions**
- Assumes plain text messages
- Doesn't handle attachments well
- Limited to human/assistant roles

**No User Feedback**
- Users can't correct summaries
- No way to mark facts as wrong
- One-way extraction

---

## File Reference

[`src/core/conversation_contraction.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/src/core/conversation_contraction.py)
