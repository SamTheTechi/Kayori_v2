# Mood Engine

The mood engine tracks and updates the runtime mood state.

## What It Does

It is responsible for:
- Changes based on user messages
- Parsing a model-produced delta for the fast emotions
- Applying conflict and reinforcement rules across the full mood state
- Supporting drift and spike operations on the stored state

## Emotion Model

### Fast Emotions (change quickly)
- Affection, Amused, Curious, Concerned
- Disgusted, Embarrassed, Frustrated

### Long Emotions (change slowly)
- Trust, Attachment, Confidence

The model only predicts deltas for the fast emotions. Long emotions are adjusted indirectly during `apply()`.

## How It Works

The engine exposes three main operations:

```
1. analyze(text) → Get emotion delta from LLM
2. apply(state, delta) → Update state + propagate
3. drift(state) → Slowly return to neutral
```

### Phase 1: Analysis

`analyze()` formats the recent messages with the current content and calls the configured chat model:

```python
delta = await mood_engine.analyze(
    content="User message",
    messages=recent_context,
)
```

Parsing behavior:
- Empty content returns a neutral delta
- Model failures return a neutral delta
- Invalid JSON falls back to neutral after a fragment parse attempt
- Parsed fast-emotion values are clamped to `-1.0` to `1.0`

### Phase 2: Application

`apply()` updates fast emotions directly, then propagates effects through the conflict and reinforcement maps:

```python
next_mood = mood_engine.apply(current_mood, delta)
```

Examples from the current graph:
- Affection → reinforces → Trust, Attachment
- Frustrated → conflicts with → Affection, Trust
- Amused → reinforces → Affection, Attachment

When a fast emotion affects a long emotion, the propagated change is scaled by `relation_build_factor`.

### Phase 3: Drift

`drift()` moves every emotion back toward the neutral midpoint:

```python
mood = mood_engine.drift(current_mood)
```

Long emotions drift more slowly than fast emotions.

## Emotion Range

Stored mood values are clamped to `0.0` through `1.0`, with `0.5` as the neutral point.

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
mood = await state_store.get_mood()

# 2. Analyze message
delta = await mood_engine.analyze(content, recent_messages)

# 3. Apply changes
next_mood = mood_engine.apply(mood, delta)

# 4. Save updated mood
await state_store.set_mood(next_mood)
```

## File Reference

[`src/core/mood_engine.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/src/core/mood_engine.py)
