# Kayori v2

Kayori v2 is an async, adapter-based conversational agent built with LangGraph.

## Current Status

This repository is in active refactor. The runnable path today is [`app.py`](/home/Asuna/Projects/macro/new/kayori_v2/app.py).

### What is wired and used right now

- Input: Telegram (configured in `enabled_inputs`)
- Output: Telegram (configured in `enabled_outputs`)
- Orchestration: LangGraph pipeline graph + async message bus
- Agent: ReAct-style graph (`ReactAgentService`) with `ChatGroq`
- Tooling currently enabled in code: `WeatherTool`
- State store: in-memory
- Message bus: in-memory

### What exists but is not part of the active runtime path

- Discord adapters/runtime
- Redis bus/state adapters
- Reminder/Spotify/User-device tools (present, not enabled in current `tools` list)
- Scheduler/memory modules (present, not integrated into `app.py` boot path)

## Architecture (Current Runtime)

1. Input adapter normalizes incoming platform messages into `MessageEnvelope`
2. Envelope is published to message bus
3. Orchestrator consumes envelope and invokes LangGraph pipeline
4. Pipeline loads mood state, calls agent, builds `OutboundMessage`
5. Output dispatcher sends to configured output adapters

Main files:

- [`app.py`](/home/Asuna/Projects/macro/new/kayori_v2/app.py)
- [`core/orchestrator.py`](/home/Asuna/Projects/macro/new/kayori_v2/core/orchestrator.py)
- [`agent/service.py`](/home/Asuna/Projects/macro/new/kayori_v2/agent/service.py)
- [`agent/react_agent.py`](/home/Asuna/Projects/macro/new/kayori_v2/agent/react_agent.py)

## Prerequisites

- Python 3.13 recommended
- Telegram bot token
- Groq API key

## Environment Variables

Create `.env` in project root.

Required for current default runtime:

```env
API_KEY=your_groq_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_OUTPUT_CHAT_ID=target_chat_id_for_outbound_messages
```

Optional:

```env
# Weather tool (enabled in current app.py tools list)
WEATHER_API_KEY=your_weatherapi_key

# If you enable additional tools in app.py
REMINDER_FALLBACK_USER_ID=
ENABLE_SPOTIFY_TOOL=false
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=
JOIN_API_KEY=
JOIN_DEVICE_ID=

# If you enable discord input/output paths
DISCORD_BOT_TOKEN=
DISCORD_TOKEN=
```

## Run

```bash
pip install -r requirements.txt
python app.py
```

## Why `ReminderTool` Needs `user_id` / `target_user_id`

`ReminderTool` schedules work to run later and republishes a new message into the bus. When that delayed message is emitted, there may be no original chat context available, so routing must include a destination.

Resolution order in [`tools/reminder.py`](/home/Asuna/Projects/macro/new/kayori_v2/tools/reminder.py):

1. `target_user_id` argument
2. `envelope.target_user_id`
3. `envelope.author_id`
4. `REMINDER_FALLBACK_USER_ID`

If none exists, the tool returns:

`Reminder could not be scheduled because target user id is missing.`

## Notes

- This repo currently has no automated tests checked in.
- Some documentation from earlier architecture (HTTP API endpoints, server module, older scheduler setup) does not match the current boot path.

## License

MIT. See [`LICENSE`](/home/Asuna/Projects/macro/new/kayori_v2/LICENSE).
