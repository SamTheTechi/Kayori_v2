# Scheduler

The scheduler publishes delayed or recurring events to the message bus.

## What It Does

Drives proactive behavior:
- ⏰ Delayed check-ins and reminders
- 🔄 Recurring internal tasks
- 🧹 Inactivity-based history cleanup
- 💭 Life reflection triggers

**Key point:** The scheduler doesn't generate responses. It publishes events that the orchestrator handles.

## Trigger Types

### Precise Triggers
Fire after exact interval:
```python
Trigger(
    trigger_type=TriggerType.PRECISE,
    source=MessageSource.SCHEDULER,
    interval_seconds=60,  # Fire in 60 seconds
    content="Check-in message"
)
```

### Fuzzy Triggers
Fire with random delay spread:
```python
Trigger(
    trigger_type=TriggerType.FUZZY,
    source=MessageSource.SCHEDULER,
    interval_seconds=3600,  # Base: 1 hour
    fuzzy_seconds=900,       # Random +0-15 min
    content="Casual check-in"
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
2. Loop polls every 1 second
3. When trigger is due → Publish to bus
4. If repeat=True → Reschedule
5. If one-shot → Remove
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
# Reset on every chat turn
await scheduler.remove(f"compact:{thread_id}")
await scheduler.push(Trigger(
    trigger_type=TriggerType.PRECISE,
    source=MessageSource.COMPACT,
    interval_seconds=1800,  # 30 minutes
    metadata={"thread_id": thread_id},
    repeat=False
))
```

## Pros and Cons

### ✅ Strengths

**Simple API**
- Three trigger types cover most use cases
- Clear interval/repeat semantics
- Easy to understand

**Bus Integration**
- Triggers become messages
- Same pipeline as user input
- Orchestrator routes by source

**Flexible Timing**
- Precise for exact needs
- Fuzzy for natural behavior
- Repeating for recurring tasks

**Backend Agnostic**
- Works with Redis or in-memory
- Easy to swap storage
- Restore triggers on boot

### ❌ Limitations

**Relative Time Only**
- No absolute wall-clock scheduling
- Can't say "fire at 9 AM Monday"
- Interval-based only

**Polling-Based**
- Checks every 1 second
- Not event-driven
- 1-second granularity

**No Cron Support**
- Can't do complex schedules
- No "every weekday at 8 AM"
- Limited to intervals

**Bus Dependency**
- Triggers must go through message bus
- No direct callbacks
- Orchestrator must handle source

---

## File Reference

[`src/core/scheduler.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/src/core/scheduler.py)
