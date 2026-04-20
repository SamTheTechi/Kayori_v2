# Tools

Tools give the agent abilities to interact with the real world: search the web, control Spotify, set reminders, manage calendars.

## Available Tools

| Tool | Purpose | API Keys Required |
|------|---------|-------------------|
| ReminderTool | Schedule delayed messages | No |
| SpotifyTool | Control Spotify playback | Yes (OAuth) |
| TavilySearch | Web search | Yes (Tavily) |
| CalendarTools | Google Calendar integration | Yes (Google) |
| LifeInfoTool | Read/write life profile | No |
| WeatherTool | Weather lookup | Yes (Weather API) |
| GmailTools | Gmail integration | Yes (Google) |

---

## ReminderTool

### What It Does

Schedules delayed messages that get delivered back to the user.

### Usage

```python
# Agent calls this automatically when user says "remind me in 10 minutes to..."
ReminderTool(output=output_dispatcher)
```

### How It Works

1. User says "Remind me to call mom in 15 minutes"
2. Agent calls `ReminderTool(delay_minutes=15, content="Call mom")`
3. Tool creates async task that sleeps for 15 minutes
4. After delay, tool sends `OutboundMessage` via output sink
5. User receives: "Reminder: Call mom"

### Parameters

```python
delay_minutes: int = 15          # How long to wait (1-1440)
content: str | None = None       # Reminder text
target_user_id: str | None = None # Who to remind
```

---

## SpotifyTool

### What It Does

Controls Spotify playback: play, pause, skip, volume, search.

### Commands

| Command | Description |
|---------|-------------|
| `play` / `resume` | Resume playback |
| `play_track` | Search and play a track |
| `pause` | Pause playback |
| `next` | Skip to next track |
| `previous` | Go to previous track |
| `now_playing` | Get current track info |
| `volume_up` | Increase volume (+10%) |
| `volume_down` | Decrease volume (-10%) |

### Setup

```env
SPOTIFY_CLIENT_ID=your_id
SPOTIFY_CLIENT_SECRET=your_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8080/callback
```

### Usage Examples

```python
# Play specific track
SpotifyTool()._arun(command="play_track", query="Bohemian Rhapsody")
# → "Queued and playing: Bohemian Rhapsody by Queen"

# Check what's playing
SpotifyTool()._arun(command="now_playing")
# → "Now playing: Bohemian Rhapsody by Queen on Desktop"

# Adjust volume
SpotifyTool()._arun(command="volume_up", step=10)
# → "Volume increased from 50% to 60%."
```

### How It Works

1. OAuth authentication via Spotify
2. Requires active Spotify device
3. Uses spotipy library
4. All calls wrapped in `asyncio.to_thread()` (sync library)

---

## TavilySearch

### What It Does

Web search via Tavily API.

### Setup

```env
TAVILY_API_KEY=your_key
```

### Usage

```python
from langchain_tavily import TavilySearch

search = TavilySearch(max_results=3, topic="general")
```

### Features

- Up to 3 results (configurable)
- General topic (not news-specific)
- Returns search snippets
- LangChain native tool

---

## CalendarTools

### What It Does

Google Calendar integration for scheduling.

### Setup

Requires Google OAuth credentials.

### Features

- List upcoming events
- Create calendar events
- Check availability

---

## LifeInfoTool

### What It Does

Reads and writes the user's life profile from state store.

### Usage

```python
LifeInfoTool(state_store=state)
```

### What It Accesses

- Life profile text (stored in Redis)
- User preferences, goals, interests
- Long-term context about user

---

## WeatherTool

### What It Does

Weather lookup via geopy and weather API.

### Setup

```env
WEATHER_API_KEY=your_key
WEATHER_DEFAULT_LOCATION=New York
```

### Features

- Location-based weather
- Uses geopy for geocoding
- Current conditions

---

## GmailTools

### What It Does

Gmail integration for email.

### Setup

Requires Google OAuth credentials.

### Features

- Read emails
- Search inbox
- Send emails

---

## Adding a New Tool

### Step 1: Create Tool Class

```python
from langchain_core.tools import BaseTool
from pydantic import BaseModel

class MyToolArgs(BaseModel):
    query: str
    option: int = 10

class MyTool(BaseTool):
    name: str = "my_tool"
    description: str = "Does something useful"
    args_schema: type[BaseModel] = MyToolArgs
    
    async def _arun(self, query: str, option: int = 10, state: dict | None = None) -> str:
        # Do something
        result = await some_async_function(query, option)
        return f"Result: {result}"
    
    def _run(self, *args, **kwargs) -> str:
        raise NotImplementedError("Use async execution")
```

### Step 2: Add to Agent

```python
tools = [
    ReminderTool(output=output_dispatcher),
    LifeInfoTool(state_store=state),
    SpotifyTool(),
    TavilySearch(max_results=3, topic="general"),
    MyTool(),  # ← Add here
]

agent = ReactAgentService(model=chat_model, tools=tools)
```

---

## Configuration

Tools added in `main.py`:

```python
tools = [
    ReminderTool(output=output_dispatcher),
    LifeInfoTool(state_store=state),
    SpotifyTool(),
    TavilySearch(max_results=3, topic="general"),
]
tools.extend(CalendarTools())
```

---

## Key Takeaways

1. **ReAct pattern**: Agent reasons about tool use
2. **Async-only**: All tools use `_arun()`
3. **State access**: Tools can see conversation context
4. **Easy to add**: Extend `BaseTool`, wire in
5. **Error resilient**: Failures logged, user sees friendly errors

---

## Related

- [Agent System](agent.md) - How tools are used
- [Orchestrator](orchestrator.md) - Tool execution context
- [Getting Started](getting-started.md) - Setup tool API keys
