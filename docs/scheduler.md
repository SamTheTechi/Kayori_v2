# Scheduler

The scheduler publishes delayed or recurring events to the message bus.

## What It Does

It stores triggers, polls for due work, and publishes the resulting envelopes back to the bus for the orchestrator to handle.

## Trigger Types

### Precise Triggers
Fire after a fixed interval:
```python
Trigger(
    trigger_type=TriggerType.PRECISE,
    source=MessageSource.COMPACT,
    interval_seconds=60,  # Fire in 60 seconds
)
```

### Fuzzy Triggers
Fire with random delay spread:
```python
Trigger(
    trigger_type=TriggerType.FUZZY,
    source=MessageSource.PROACTIVE,
    interval_seconds=3600,  # Base: 1 hour
    fuzzy_seconds=900,
    content="__internal__"
)
```

### Repeating Triggers
Auto-reschedule after firing:
```python
Trigger(
    trigger_type=TriggerType.PRECISE,
    source=MessageSource.LIFE,
    interval_seconds=20,
    repeat=True  # Keep firing every 20s
)
```

## How It Works

```
1. push(trigger) → Store in backend
2. Normalize the scheduled fire time
3. Poll the backend on each scheduler tick
4. Publish due triggers to the bus as `MessageEnvelope` objects
5. Reschedule repeating triggers or remove one-shot triggers
```

## Current Usage

**LIFE Trigger** (every 20 seconds):
```python
await scheduler.push(Trigger(
    trigger_type=TriggerType.PRECISE,
    source=MessageSource.LIFE,
    interval_seconds=20,
    repeat=True
))
```

**Compaction Timer** (after 30 min inactivity):
```python
await scheduler.remove("compact")
await scheduler.push(Trigger(
    trigger_type=TriggerType.PRECISE,
    source=MessageSource.COMPACT,
    interval_seconds=1800,
    repeat=False,
    _trigger_id="compact",
))
```

## File Reference

[`gateway/scheduler/service.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/gateway/scheduler/service.py)
