# Agent System

Kayori uses two specialized agents working together to provide intelligent conversations.

## Overview

```
┌─────────────────────────────────────┐
│           AGENT SYSTEM              │
│                                     │
│  ┌──────────────┐  ┌──────────────┐ │
│  │  Chat Agent  │  │  Life Agent  │ │
│  │  (ReAct)     │  │ (Reflection) │ │
│  │              │  │              │ │
│  │ User-facing  │  │ Background   │ │
│  │ responses    │  │ processing   │ │
│  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────┘
```

**Why Two Agents?**
- **Chat Agent** focuses on responding to users (uses powerful 120B model)
- **Life Agent** handles internal reflection (uses smaller 20B model)
- Separation prevents background processing from blocking user responses
- Different models optimize cost vs. quality

---

## Chat Agent (ReactAgentService)

### What It Does

The main conversational agent that users interact with.

### How It Works

Uses **LangGraph ReAct pattern** (Reason + Act):
1. Receives user message + context
2. Reasons about what tools to use (if any)
3. Executes tools sequentially
4. Generates final response

### What It Receives

```python
{
    "content": "User's message",
    "messages": [last 12 messages],
    "mood": current_mood_state,
    "episodic": [2 relevant long-term memories],
    "envelope": original_message_metadata
}
```

### What It Returns

A text response string, or error message if generation fails.

### Tool Access

The chat agent has access to:
- **ReminderTool**: Schedule delayed messages
- **SpotifyTool**: Control Spotify playback
- **TavilySearch**: Web search (max 3 results)
- **CalendarTools**: Google Calendar integration
- **LifeInfoTool**: Read/write life profile

### Implementation

```python
agent = ReactAgentService(
    model=chat_model,  # GPT-OSS-120B
    tools=[...],
    timeout_seconds=60
)

reply = await agent.respond(
    content="Hello!",
    messages=recent_history,
    mood=current_mood,
    episodic=relevant_memories,
    envelope=message_envelope
)
```

### Error Handling

- Graph failures return user-friendly error messages
- 60-second timeout prevents hanging
- All errors logged with structured context

---

## Life Agent (LifeAgentService)

### What It Does

Background reflection agent that generates "life notes" from conversations.

### When It Runs

Triggered by scheduler every 20 seconds (configurable) via `MessageSource.LIFE`.

### How It Works

1. Receives scheduled LIFE trigger
2. Loads recent conversation summary
3. Loads relevant episodic memories
4. Loads user's life profile
5. Reflects on recent activity
6. Generates life note if something noteworthy happened

### What It Receives

```python
{
    "content": "trigger content",
    "summary": "recent conversation summary",
    "episodic": [relevant memories],
    "life_profile": "user's life profile text",
    "recent_notes": [last 3 life notes]
}
```

### What It Returns

A life note string, or `None` if nothing noteworthy happened.

### Life Notes

Life notes are short observations stored in Redis:
```python
{
    "content": "User mentioned they're learning Python",
    "timestamp": "2026-04-04T10:30:00+00:00",
    "kind": None
}
```

**Purpose:**
- Track important user information over time
- Build understanding of user's interests/goals
- Inform future conversations
- Maximum 3 pending notes at once (prevents spam)

### Implementation

```python
life_agent = LifeAgentService(
    model=chat_model2,  # GPT-OSS-20B (cheaper)
    tools=[TavilySearch()],
    timeout_seconds=60
)

note = await life_agent.reflect(
    content=trigger_content,
    summary=conversation_summary,
    episodic=memories,
    life_profile=profile,
    recent_notes=recent_life_notes
)

if note:
    await state_store.append_life_note(thread_id, note)
```

---

## LangGraph Integration

Both agents use **LangGraph state graphs**:

### Chat Agent Graph

```
Input → Tool Selection → Tool Execution → Response Generation → Output
         (LLM decides)   (if needed)      (LLM generates)
```

### Life Agent Graph

```
Input → Context Loading → Reflection → Note Generation → Output
         (load history)  (LLM thinks)  (if noteworthy)
```

### State Management

LangGraph manages:
- Message history within conversation
- Tool call sequences
- Error states
- Final outputs

---

## Model Choices

### Chat Agent: GPT-OSS-120B
- **Why**: Highest quality responses
- **Cost**: More expensive per call
- **Use**: User-facing interactions where quality matters

### Life Agent: GPT-OSS-20B
- **Why**: Good enough for reflection tasks
- **Cost**: 6x cheaper than 120B
- **Use**: Background processing where cost matters more than perfection

---

## File Structure

```
src/agent/
├── chat/
│   ├── service.py      # ReactAgentService class
│   └── graph.py        # LangGraph graph creation
├── life/
│   ├── service.py      # LifeAgentService class
│   └── graph.py        # LangGraph graph creation
└── __init__.py
```

---

## Key Takeaways

1. **Two agents, different purposes**: Chat for users, Life for reflection
2. **LangGraph handles complexity**: State management, tool orchestration
3. **Cost-conscious design**: Expensive model only where needed
4. **Async-first**: Non-blocking execution for both agents
5. **Error-resilient**: Failures logged, user sees friendly errors

---

## Related

- [Orchestrator](orchestrator.md) - How agents are coordinated
- [Mood Engine](mood-engine.md) - Emotional state tracking
- [Scheduler](scheduler.md) - LIFE trigger timing
