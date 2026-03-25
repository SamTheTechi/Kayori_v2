# Scheduler

This document explains how the scheduler works today, what it is good for, and
how to use it with the current trigger API.

## Purpose

The scheduler is a small runtime service that publishes delayed or recurring
events into the same bus used by normal inbound messages.

It is useful for:

- delayed check-ins,
- reminders,
- recurring internal tasks,
- life-style background events.

The scheduler itself does not generate the final user-facing reply. It publishes
a `MessageEnvelope` into the bus, and the orchestrator decides what to do with
that event.

## High-Level Flow

1. Create a backend.
2. Create `AgentScheduler`.
3. Start it.
4. Push one or more `Trigger` objects.
5. When a trigger fires, the scheduler publishes a `MessageEnvelope` to the bus.
6. The orchestrator routes that event by `MessageSource`.

## Trigger Model

Current trigger shape:

```python
@dataclass(slots=True)
class Trigger:
    trigger_type: TriggerType
    source: MessageSource
    interval_seconds: float
    content: str = "__internal__"
    metadata: dict[str, Any] = field(default_factory=dict)
    repeat: bool = False
    fuzzy_seconds: float | None = None
```

What the fields mean:

- `trigger_type`
  - `PRECISE`: fire after `interval_seconds`
  - `FUZZY`: fire after `interval_seconds` with a random spread
- `source`
  - the `MessageSource` used when publishing to the bus
- `content`
  - the text published into the envelope
  - defaults to `__internal__`, which is currently used for internal scheduled
    events
- `metadata`
  - optional extra structured context
- `interval_seconds`
  - time until the first fire
  - if `repeat=True`, also the gap between future fires
- `repeat`
  - whether the trigger repeats
- `fuzzy_seconds`
  - only for `FUZZY`
  - random window added after the base interval

## Setup

```python
from src.adapters.scheduler.in_memory import InMemorySchedulerBackend
from src.core.scheduler import AgentScheduler

backend = InMemorySchedulerBackend()
scheduler = AgentScheduler(backend=backend, bus=bus)
await scheduler.start()
```

## Examples

### One-Time Exact Trigger

```python
from src.shared_types.models import MessageSource
from src.shared_types.types import Trigger, TriggerType

await scheduler.push(
    Trigger(
        trigger_type=TriggerType.PRECISE,
        source=MessageSource.SCHEDULER,
        content="Send a warm check-in message to the user.",
        interval_seconds=60,
    )
)
```

Meaning:

- wait 60 seconds
- fire once

### Repeating Exact Trigger

```python
await scheduler.push(
    Trigger(
        trigger_type=TriggerType.PRECISE,
        source=MessageSource.LIFE,
        interval_seconds=21600,
        repeat=True,
    )
)
```

Meaning:

- first fire after 21600 seconds
- then every 21600 seconds again

### Fuzzy Trigger

```python
await scheduler.push(
    Trigger(
        trigger_type=TriggerType.FUZZY,
        source=MessageSource.SCHEDULER,
        content="Check in casually with the user.",
        interval_seconds=3600,
        fuzzy_seconds=900,
    )
)
```

Meaning:

- base time is 1 hour from now
- actual fire happens randomly within the next 15 minutes after that base time

### Repeating Fuzzy Trigger

```python
await scheduler.push(
    Trigger(
        trigger_type=TriggerType.FUZZY,
        source=MessageSource.SCHEDULER,
        content="Send a light check-in.",
        interval_seconds=86400,
        fuzzy_seconds=1800,
        repeat=True,
    )
)
```

Meaning:

- first fire around 24 hours from now
- then repeat every 24 hours
- each time with up to 30 minutes of random spread

### Optional Metadata

```python
await scheduler.push(
    Trigger(
        trigger_type=TriggerType.PRECISE,
        source=MessageSource.SCHEDULER,
        content="Send good morning to the user.",
        interval_seconds=60,
        metadata={"kind": "morning_greeting"},
    )
)
```

### Inactivity-Based Compaction Timer

The current runtime also uses the scheduler as an idle timer instead of only as
a repeating job system.

Pattern:

```python
await scheduler.remove(f"compact:{thread_id}")
await scheduler.push(
    Trigger(
        trigger_type=TriggerType.PRECISE,
        source=MessageSource.COMPACT,
        interval_seconds=1800,
        metadata={"thread_id": thread_id},
        repeat=False,
        _trigger_id=f"compact:{thread_id}",
    )
)
```

Meaning:

- every chat turn removes the old compact timer
- a new one-shot compact trigger is scheduled
- compaction only fires after inactivity, not on a fixed repeating loop

## How It Works Internally

- `push()` validates the trigger and computes the first scheduled fire time
- the backend stores the trigger
- the scheduler loop polls the backend for due triggers
- when a trigger is due, the scheduler publishes a `MessageEnvelope` with:
  - `source = trigger.source`
  - `content = trigger.content`
  - `metadata = trigger.metadata + scheduler audit fields`
- if `repeat=True`, the next fire time is computed and stored again

Scheduler audit metadata currently includes:

- `scheduler_trigger_id`
- `scheduler_scheduled_for`
- `scheduler_repeat`

## Tradeoffs

This scheduler design is intentionally small, but that comes with tradeoffs.

### Good Parts

- simple public trigger API
- same bus pipeline as normal messages
- supports one-time, repeating, and fuzzy events
- backend can be swapped between in-memory and Redis

### Limitations

- first scheduling is relative-time based, not absolute wall-clock based
- no direct route fields on the trigger itself
- no custom in-process callback system anymore
- internal runtime actions still travel through `MessageEnvelope`
- final behavior still depends on how the orchestrator handles each source

## Operational Notes

- invalid triggers are rejected and logged; they do not crash the server
- if the scheduler has no bus, the trigger is logged as unhandled
- empty trigger content is dropped before publish
- `FUZZY` triggers must provide `fuzzy_seconds`
