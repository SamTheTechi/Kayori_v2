# GOAL.md — Agentic upgrades for Kayori

Porting selected agent-runtime behaviors from the **Hermes** agent
(`../hermesAgent`) into Kayori. We only take patterns that fit a *companion
chat agent* — not the coding-agent machinery (LSP, kanban swarms, browser
providers, etc.).

This is a living plan. We tick items off and add notes as we build.

---

## Roadmap (in build order)

### 1. Tool-call limit (iteration budget)  — `DONE`
**Problem:** Kayori's ReAct loop (`agent/chat/graph.py` → `route_after_model`)
looped `tools ⇄ call_model` with no cap. If the model kept emitting tool calls
it ran forever → runaway Groq spend.

**Hermes reference:** `agent/iteration_budget.py` — a counter consumed per tool
round, hard break with a graceful message when exhausted.

**What we shipped:**
- `model_calls` counter added to `AgentGraphState` (`shared_types/types.py`),
  incremented each `call_model` run (`agent/chat/nodes/call_model.py`) — robust,
  independent of what's in persisted history.
- `route_after_model` (`agent/chat/graph.py`) routes to `postprocess` instead of
  `tools` once `model_calls > max_tool_rounds`. Hard stop — no extra API call, so
  no dangling-tool-call errors and no infinite loop.
- `DEFAULT_MAX_TOOL_ROUNDS = 6`, configurable via `ReactAgentService(max_tool_rounds=…)`.
- `postprocess` (`agent/chat/nodes/postprocess.py`) handles the cut-off
  gracefully: salvages any partial model text, else a friendly wrap-up line
  (`BUDGET_REPLY_TEXT`), and logs `tool_budget_exhausted`.
- `recursion_limit = 2·max_tool_rounds + 6` passed at invoke
  (`agent/chat/service.py`) so OUR budget is the binding constraint (no raw
  `GraphRecursionError`).

**Verified:** stub model that always calls tools stops at exactly N rounds; a
high budget no longer raises; normal one-tool-call→answer flow unchanged.

_Stretch (not this pass):_ wrap the model call with error classification +
jittered backoff retry so Groq 429s recover instead of returning the canned
"temporary issue" string in `agent/chat/service.py`.

---

### 2. Standing goals with a judge loop  — `TODO`
**Idea:** A durable, user-level objective (e.g. "help me learn Spanish",
"check in about the interview") that Kayori pursues across turns instead of
sending generic proactive messages.

**Hermes reference:** `hermes_cli/goals.py` — `GoalState` (goal text, status,
turns_used, max_turns, subgoals, last_verdict) + a cheap auxiliary-LLM "judge"
that evaluates after each turn whether the goal is satisfied; turn budget is
the backstop; auto-pause after repeated judge-parse failures.

**Plan for Kayori:**
- Add a `GoalState` model (`shared_types/models.py`) + state-store methods
  (`StateStore` protocol + Redis/in-memory impls).
- Reuse the existing **proactive loop** (`orchestrator._handle_proactive`) and
  **life agent** so proactive outreach pursues the active goal.
- Judge: small auxiliary call (reuse `life_model`) returning
  `{"done": bool, "reason": str}`; bounded by `max_turns`.
- Surface `/goal`, `/goal pause`, `/goal resume`, `/goal clear` via the input
  adapters / webhook.

**Landing spots:** `shared_types/models.py`, `shared_types/protocol.py`,
`gateway/state/*`, `agent/orchestration/orchestrator.py`, `agent/life/*`.

---

### 3. Smarter memory & context  — `TODO`
Kayori already has window-12 + LLM contraction + episodic vector memory. Two
upgrades from Hermes:

**3a. Iterative summary updates** — `agent/memory/conversation_contraction.py`
- Hermes (`context_compressor.py:~1019`) *updates the previous summary* instead
  of re-summarizing from scratch each compaction.
- Kayori already stores the summary as a flagged first message
  (`kayori_compacted`), so feed the old summary back in and ask for a
  delta-update. Cheaper, less drift.

**3b. Episodic recency-decay + dedup** — `agent/memory/episodic_memory.py`
- Current recall blend: `0.7·backend + 0.2·importance + 0.1·confidence`, hard
  cap 250 episodes, **no recency decay, no dedup**.
- Add a recency term to the recall score, and dedup near-identical facts at
  `remember()` time so the store doesn't fill with restatements.

**Landing spots:** `agent/memory/conversation_contraction.py`,
`agent/memory/episodic_memory.py`.

---

### 4. Persona / recap — improve existing, don't clone Hermes  — `TODO`
We already have a persona setup (life profile seeded from file in
`main.py:_seed_life_profile` + the mood engine). Hermes' `docker/SOUL.md`
hot-reloads a persona file into the system prompt every turn.

**Decision:** Do NOT copy Hermes' whole SOUL/system-prompt machinery. Instead
**improve Kayori's current life + system prompt** so the persona stays live and
mood-aware:
- Enhance the existing prompt templates in `agent/prompts/` (`chat_template.py`,
  `life_template.py`, `life.md`) rather than introducing a parallel SOUL system.
- Fold the life profile + current mood into the prompt build so persona is
  reflected fresh each turn.
- (Optional) lightweight session recap after long idle gaps, reusing the
  `time_since_last` signal already in `_handle_proactive`.

**Landing spots:** `agent/prompts/*`, `agent/chat/nodes/prepare_context.py`.

---

## Decisions / notes
- Source agent: `../hermesAgent` (read-only reference; we port patterns, not code).
- Skip prompt caching (`prompt_caching.py`) — it's Anthropic `cache_control`
  specific and won't help on Groq.
- Keep changes small and self-contained; match Kayori's existing style.
