# Mood Engine

This document explains the reasoning and mechanics behind Kayori's mood engine as it exists today.

## Purpose

The mood engine gives the assistant a small internal emotional state that changes over time. The goal is not to simulate a full psychology model. The goal is to make replies feel:

- emotionally continuous across turns
- more reactive than a stateless assistant
- capable of forming a slow-changing relationship layer

The design is intentionally split into short-term emotions and long-term emotions.

## Emotion Model

The engine uses the shared emotion definitions from [`src/shared_types/models.py`](/home/Asuna/Projects/macro/kayori/kayori_agent/src/shared_types/models.py).

Fast emotions:

- `Affection`
- `Amused`
- `Curious`
- `Concerned`
- `Disgusted`
- `Embarrassed`
- `Frustrated`

Long emotions:

- `Trust`
- `Attachment`
- `Confidence`

All emotions are stored in `MoodState` and are clamped to the range `0.0..1.0`, with `0.5` as neutral.

Why this split exists:

- fast emotions represent immediate conversational reaction
- long emotions represent relationship state
- fast emotions should move often
- long emotions should move slowly and feel earned

## High-Level Flow

The engine works in three separate phases:

1. `analyze(text)` asks the model for a delta over fast emotions only.
2. `apply(current_state, delta)` applies that delta and propagates secondary effects.
3. `drift(current_state)` slowly moves emotions back toward neutral over time.

This separation is deliberate.

- `analyze()` is perception
- `apply()` is state transition
- `drift()` is passive settling

Keeping them separate makes the system easier to test and reason about. A user message should create a reaction first. Settling down should happen later, not in the same step.

## Why The Classifier Only Predicts Fast Emotions

The classifier template in [`src/templates/mood_classifier_template.py`](/home/Asuna/Projects/macro/kayori/kayori_agent/src/templates/mood_classifier_template.py) emits only fast-emotion keys.

That is intentional.

Fast emotions are things the assistant can plausibly feel from one message:

- a message can make it more amused
- a message can make it more concerned
- a message can make it more frustrated

Long emotions are not supposed to jump directly because of one message. They should emerge from repeated fast reactions over time. That is why `Trust`, `Attachment`, and `Confidence` are not direct classifier outputs.

## The Apply Step

`apply()` in [`src/core/mood_engine.py`](/home/Asuna/Projects/macro/kayori/kayori_agent/src/core/mood_engine.py) runs in two passes.

### Pass 1: Direct Fast-Emotion Update

For each fast emotion:

- read the classifier delta
- multiply it by that emotion's sensitivity
- add the result to the current state

This is the direct "what did this message do to me" step.

### Pass 2: Propagation Through Emotion Graph

After the direct update, the engine takes a snapshot of the fast emotions and uses two rule tables:

- `conflicts`
- `reinforces`

These tables are keyed by the fast emotion that became active. For each active fast emotion:

- conflicting targets are pushed down
- reinforced targets are pushed up

This lets emotional states influence each other without asking the classifier to model every dependency explicitly.

Examples:

- `Affection` reinforces `Trust` and `Attachment`
- `Frustrated` conflicts with `Affection`, `Trust`, and `Attachment`
- `Embarrassed` reinforces `Affection` and `Trust`
- `Disgusted` conflicts with `Affection` and `Attachment`

The important part is that one shared graph now drives both fast and long targets. There is no separate long-only reinforce/conflict table anymore.

## Why One Interaction Graph Is Better Than Four Tables

An earlier version used:

- fast conflicts
- fast reinforces
- long conflicts
- long reinforces

That worked, but it created duplicated policy and made tuning harder. The same emotional idea had to be represented twice: once for short-term behavior and once for long-term behavior.

The current design keeps only one reinforce/conflict graph because:

- the emotional relationship itself should be defined once
- short-term and long-term differences should come from scaling, not duplicate maps
- it is easier to read and tune
- it reduces disagreement between fast and long logic

In other words, the rule "Affection supports Attachment" should exist once. The fact that `Attachment` is long-term should change the strength of the effect, not require a second copy of the rule.

## Slow-Build Relationship Logic

Long emotions are updated by the same propagation graph, but with slower movement.

When a conflict or reinforce target is one of:

- `Trust`
- `Attachment`
- `Confidence`

the effect is multiplied by `relation_build_factor`.

The current intent behind that scaling is:

- long-term relation should not react as quickly as fast emotions
- repeated fast reactions should gradually shape relationship state
- the assistant should feel consistent instead of volatile

This design keeps the relationship layer present without making it twitchy.

Note: if you want strict "build slow, break fast" behavior later, the current implementation can be tightened so only positive reinforcement gets scaled while negative conflict remains full-strength. The current code uses one shared scale for long targets.

## Drift

`drift()` is the only passive decay mechanism.

That was a deliberate choice. `apply()` no longer performs decay internally because that made the system feel artificially damped. A human reaction should happen first. Settling should happen later.

Current drift behavior:

- all emotions drift toward neutral
- fast emotions drift normally
- long emotions drift 20x slower

Why long emotions drift slowly:

- `Trust`, `Attachment`, and `Confidence` should not evaporate from minor inactivity
- they should feel more stable than conversational mood

## Spike

`spike()` only affects fast emotions.

This is intentional because spikes represent transient surges, not relationship change.

Examples of what a spike is meant to simulate:

- sudden annoyance
- sudden amusement
- sudden embarrassment

Examples of what a spike should not simulate:

- sudden trust
- sudden attachment
- sudden confidence bond-building

Long emotions are relational memory, not impulsive reactions.

## Sensitivity

Sensitivity is a per-emotion multiplier applied during the direct fast-emotion update.

It controls how strongly an emotion responds to the same classifier delta.

Examples:

- `Frustrated` with `1.5` reacts more strongly than normal
- `Trust` with `0.5` would react weakly if it were directly updated
- `1.0` means neutral/default behavior

Current sensitivity rules:

- values are allowed in `0.0..2.0`
- missing values default to `1.0`
- partial maps are allowed

This keeps tuning flexible without forcing every emotion to be configured every time.

## Tunable Parameters

The constructor currently exposes these main knobs:

- `sensitivity`
- `conflict_multiplier`
- `reinforce_multiplier`
- `spike_scale`
- `drift_multiplier`
- `relation_build_factor`

What they do:

- `sensitivity`: per-emotion direct responsiveness
- `conflict_multiplier`: how strongly active fast emotions suppress conflicting targets
- `reinforce_multiplier`: how strongly active fast emotions support related targets
- `spike_scale`: intensity of random fast-emotion spikes
- `drift_multiplier`: global rate of passive settling
- `relation_build_factor`: slows propagation into long-term emotions

The multiplier fields are clamped to `0.0..1.0` in the current implementation. This keeps tuning bounded and avoids extreme values making the engine unstable.

## Neutral Point And Clamping

All emotions are treated as values in `0.0..1.0`.

- `0.0` means minimal presence
- `0.5` means neutral
- `1.0` means strong presence

Using a neutral midpoint instead of signed values simplifies storage and interaction with prompts. The classifier still emits signed deltas in `-1.0..1.0`, but the stored state remains a bounded normalized range.

## Why The Engine Is Stateless

`MoodEngine` does not own a conversation's `MoodState`. It receives a current state and returns a next state.

This is the correct boundary for the project because:

- thread state belongs in the orchestrator/state store
- the engine should be reusable across threads
- model classification and state transition logic stay testable in isolation

The engine owns the rules. The state store owns the actual state.

## Design Tradeoffs

What this design optimizes for:

- simple enough to tune by hand
- expressive enough to make behavior feel continuous
- separate immediate reaction from long-term bond
- keep state bounded and deterministic

What this design intentionally does not try to do:

- perfect human emotion simulation
- deep psychological modeling
- implicit memory replacement
- unrestricted emergent state behavior

It is a controlled behavior layer, not a full personality engine.

## Current Limitations

Some current limitations are intentional and should be understood:

- the reinforce/conflict graph is hand-authored, not learned
- long-term relation is still derived from fast emotions, not from explicit event types
- drift is generic and does not yet depend on context or time gaps
- the engine assumes one neutral midpoint for every emotion

These are acceptable tradeoffs for the current scope because they keep the system understandable and debuggable.

## Summary

The mood engine is built around one central idea:

- messages create fast emotional reactions
- fast reactions influence other emotions
- long-term relationship state emerges slowly from those reactions
- passive settling happens separately over time

That split is what makes the assistant feel more continuous without making the system unmanageably complex.
