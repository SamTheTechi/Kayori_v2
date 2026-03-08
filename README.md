# Kayori v2

Kayori v2 is an async, adapter-based AI companion built around LangGraph, platform runtimes, and a small orchestrated message pipeline. The goal of this version is to keep the runtime modular: input comes in through adapters, the orchestrator handles state + agent execution, and outputs are routed through an output sink.

## What Makes Kayori v2 Different?

This version is less of a monolith and more of a runtime shell for different agent capabilities. Instead of one large app doing everything directly, the system is split into clear pieces:

- Input adapters normalize external messages into `MessageEnvelope`
- A message bus decouples ingress from processing
- `AgentOrchestrator` loads state and calls the agent
- `ReactAgentService` runs the LangGraph ReAct agent
- `OutputSink` decides whether responses go back to the same platform or to every configured output

The repo is still under active refactor, but the structure is much cleaner than the older version and easier to swap pieces in and out.

## Core Features

#### 1. Adapter-Based Runtime

- Discord, Telegram, and console input/output adapters exist in the repo
- Runtimes are separated from adapters so platform connection lifecycle is reusable
- Input and output are wired independently in `main.py`

#### 2. Orchestrated Agent Flow

- `AgentOrchestrator` owns the runtime pipeline
- Incoming messages are consumed from the bus
- Current mood state is loaded from the state store
- The agent generates a reply and returns an `OutboundMessage`
- The output sink routes the final response

#### 3. Tool-Using Agent

- `WeatherTool`
- `ReminderTool`
- `SpotifyTool`
- `TavilySearch`

#### 4. Output Routing Modes

- `direct` mode sends Discord -> Discord, Telegram -> Telegram, Console -> Console
- `multi` mode broadcasts one outbound message to every configured output adapter
- Routing is handled by `OutputSink`

#### 5. State + Memory Foundations

- In-memory state store is the active boot path right now
- Redis state and bus adapters exist but are not used by default
- Episodic and graph memory modules are present for future integration

## Architecture Overview

- `main.py` boots the app, wires runtimes, state store, tools, agent, orchestrator, and adapters
- `core/orchestrator.py` handles message consumption, state lookup, agent execution, and outbound message creation
- `agent/service.py` builds and runs the ReAct graph
- `core/ouputsink.py` routes outbound messages by mode
- `shared_types/` holds the common models, protocols, and typed state

Current default runtime path:

1. A platform adapter receives a message
2. The adapter publishes a `MessageEnvelope` to the message bus
3. `AgentOrchestrator` consumes the envelope
4. Mood state is loaded from the state store
5. `ReactAgentService` generates a reply
6. The orchestrator builds an `OutboundMessage`
7. `OutputSink` dispatches it to the selected output adapters

## Current Runtime Defaults

As of the current `main.py`:

- Input: Discord
- Output: Discord
- State store: in-memory
- Message bus: in-memory
- Output mode: `direct`
- Model path: `ChatGroq` via `ReactAgentService.from_env(...)`

## Mood System Status

Mood state exists and is passed into the prompt, but the mood engine is not fully integrated into the active runtime yet.

- Initial mood comes from `InMemoryStateStore`
- Each emotion starts at `0.5`
- The orchestrator currently reads mood and passes it to the agent
- The current boot path does not persist mood updates automatically

## Prerequisites

- Python 3.14+
- A Groq-compatible API key in `API_KEY`
- Discord bot token for the current default runtime
- Optional tool/service credentials depending on what you enable

## Environment Setup

Create a `.env` file in the project root.

Minimum for the current default Discord runtime:

```env
API_KEY=
DISCORD_BOT_TOKEN=
DISCORD_USER_ID=
```

Optional values:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

WEATHER_API_KEY=
REMINDER_FALLBACK_USER_ID=

SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=

TAVILY_API_KEY=

ENABLE_TOOL_AUDIT=true
TOOL_AUDIT_LOG_PATH=logs/tool_audit.jsonl
TOOL_AUDIT_MAX_LINES=5000
```

Notes:

- `DISCORD_USER_ID` is used as the default DM target for Discord output
- `TELEGRAM_CHAT_ID` is used as the default Telegram output target
- `WEATHER_API_KEY` is required for the weather tool
- `TAVILY_API_KEY` is required if you want Tavily search to work

## Installation

### Manual

```bash
git clone <repo-url>
cd kayori_v2
pip install .
```

If you use `uv`, the repo already includes `uv.lock`:

```bash
uv sync
```

## Run

```bash
python main.py
```

## Active Modules vs Present Modules

Wired into the current boot path:

- Discord runtime and adapters
- In-memory message bus
- In-memory state store
- Agent orchestrator
- React agent service
- Weather, reminder, Spotify, and Tavily tools

Present in repo but not part of the default runtime path:

- Telegram adapters/runtime
- Console adapters
- Redis bus/state adapters
- Mood engine integration
- Episodic / graph memory integration
- Scheduler-driven proactive behavior

## Reminder Routing

`ReminderTool` needs a target when it republishes a delayed message. The fallback order is:

1. Explicit `target_user_id`
2. `envelope.target_user_id`
3. `envelope.author_id`
4. `REMINDER_FALLBACK_USER_ID`

If none of these exist, the reminder cannot be routed properly.

## Known Rough Edges

- The repo is mid-refactor and some modules are still being reshaped
- Some filenames and imports still reflect older naming mistakes
- There are currently no checked-in automated tests
- Documentation can drift quickly while the architecture is changing

## Next Direction

The current design is clearly moving toward:

- thinner `main.py`
- orchestrator-owned runtime logic
- cleaner input/process/output separation
- better state and mood integration
- output routing that can switch between platform-local and multi-platform delivery

## License

MIT. See `LICENSE`.
