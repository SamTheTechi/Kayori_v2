# Mood Engine

The mood engine tracks emotional state across 10 dimensions to make responses feel emotionally continuous.

## What It Does

Gives the assistant an internal emotional state that:
- Changes based on user messages
- Influences response tone
- Evolves slowly over time (especially trust/attachment)
- Naturally drifts back to neutral

**Goal:** Not perfect emotion simulation, but enough to make replies feel reactive and continuous.

## Emotion Model

### Fast Emotions (change quickly)
- Affection, Amused, Curious, Concerned
- Disgusted, Embarrassed, Frustrated

### Long Emotions (change slowly)
- Trust, Attachment, Confidence

**Why the split?**
- Fast emotions = immediate reaction to one message
- Long emotions = relationship state, earned over time
- Long emotions updated via conflict/reinforcement graph, not directly

## How It Works

Three separate phases:

```
1. analyze(text) → Get emotion delta from LLM
2. apply(state, delta) → Update state + propagate
3. drift(state) → Slowly return to neutral
```

### Phase 1: Analysis

LLM classifies emotion changes from user message:
```python
delta = await mood_engine.analyze(
    content="User message",
    messages=recent_context,
    thread_id="user123"
)
# Returns: {"Affection": 0.2, "Amused": -0.1, ...}
```

**Why only fast emotions?**
- LLM predicts 7 fast emotions only
- Long emotions emerge from propagation
- Trust isn't felt from one message, it's built

### Phase 2: Application

Updates state with conflict/reinforcement graph:

```python
next_mood = mood_engine.apply(current_mood, delta)
```

**Two passes:**

1. **Direct update**: Add delta × sensitivity to each fast emotion
2. **Propagation**: Active emotions influence others

**Example graph:**
- Affection → reinforces → Trust, Attachment
- Frustrated → conflicts with → Affection, Trust
- Amused → reinforces → Affection, Attachment

**Long emotion scaling:**
When fast emotion influences long emotion:
```python
effect *= relation_build_factor  # Slower change
```

### Phase 3: Drift

All emotions slowly drift toward neutral (0.5):
```python
mood = mood_engine.drift(current_mood)
```

**Drift rates:**
- Fast emotions: Normal speed
- Long emotions: 20x slower (stable)

## Emotion Range

All emotions: `0.0` to `1.0`
- `0.0` = Minimal presence
- `0.5` = Neutral (default)
- `1.0` = Strong presence

## Tunable Parameters

| Parameter | Range | Purpose |
|-----------|-------|---------|
| `sensitivity` | 0.0-2.0 | Per-emotion responsiveness |
| `conflict_multiplier` | 0.0-1.0 | How much conflicts suppress |
| `reinforce_multiplier` | 0.0-1.0 | How much reinforcement boosts |
| `drift_multiplier` | 0.0-1.0 | Global drift speed |
| `relation_build_factor` | 0.0-1.0 | Long emotion scaling |
| `spike_scale` | 0.0-1.0 | Random spike intensity |

## Runtime Usage

From orchestrator:
```python
# 1. Load current mood
mood = await state_store.get_mood(thread_id)

# 2. Analyze message
delta = await mood_engine.analyze(content, recent_messages)

# 3. Apply changes
next_mood = mood_engine.apply(mood, delta)

# 4. Save updated mood
await state_store.set_mood(thread_id, next_mood)
```

## Pros and Cons

### ✅ Strengths

**Simple Yet Expressive**
- 10 dimensions cover key emotions
- Conflict/reinforcement graph handles interactions
- Tunable without being complex

**Separation of Concerns**
- `analyze()` = perception
- `apply()` = state transition
- `drift()` = passive settling
- Each testable in isolation

**Slow Relationship Building**
- Trust/Attachment change gradually
- Feels consistent, not twitchy
- Earned through repeated interactions

**Stateless Engine**
- Doesn't own state (orchestrator does)
- Reusable across threads
- Easy to test

**Natural Drift**
- Emotions return to neutral over time
- Long emotions drift 20x slower
- Feels realistic

### ❌ Limitations

**Hand-Authored Graph**
- Conflict/reinforcement rules manual
- Not learned from data
- Requires tuning

**LLM Classification**
- Depends on LLM quality
- 2-second timeout can fail
- Adds API cost per turn

**Simple Drift**
- Generic decay, not context-aware
- Doesn't consider time gaps
- Same rate for all situations

**No Negative Scaling**
- Can't do "build slow, break fast"
- Long emotions use same scale for +/- 
- Could be more nuanced

**Sensitivity Tuning**
- Manual process
- No adaptive learning
- Hard to get right

---

## File Reference

[`src/core/mood_engine.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/src/core/mood_engine.py)
