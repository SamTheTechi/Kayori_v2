# Getting Started

Get Kayori v2 running in under 5 minutes.

## Prerequisites

- **Python 3.13** (strict requirement, 3.14 may work)
- **uv** package manager (or pip)
- **Redis** server (required for production)
- **Groq API key** (for LLM)
- **Platform token** (Discord or Telegram)

## Quick Start

### 1. Install Dependencies

```bash
# Clone and setup
git clone https://github.com/SamTheTechi/kayori_v2.git
cd kayori_v2

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### 2. Configure Environment

```bash
# Copy example env
cp example.env .env

# Edit .env with your keys
```

**Minimum setup (Discord):**
```env
API_KEY=your_groq_api_key
DISCORD_BOT_TOKEN=your_discord_token
DISCORD_USER_ID=your_user_id
```

**Optional features:**
```env
# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_token

# Tools
TAVILY_API_KEY=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=

# Redis (defaults to localhost)
REDIS_URL=redis://localhost:6379
```

### 3. Start Redis

```bash
# Docker
docker run -d -p 6379:6379 redis:latest

# Or install locally
# https://redis.io/docs/install/
```

### 4. Run Kayori

```bash
python main.py
```

You should see connection logs. Send a message to your bot—it should respond!

---

## Platform Setup

### Discord

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create new application
3. Create bot and copy token
4. **Enable Message Content intent** (important!)
5. Invite bot to your server
6. Set `DISCORD_BOT_TOKEN` and `DISCORD_USER_ID` in `.env`

### Telegram

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Create new bot with `/newbot`
3. Copy the bot token
4. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

---

## What Happens When You Run Kayori

```
1. Load .env configuration
2. Connect to Redis
3. Initialize platforms (Discord/Telegram/Webhook)
4. Create agents (Chat + Life)
5. Start scheduler for proactive behavior
6. Begin listening for messages
```

---

## Verification

**Check logs for:**
- ✅ Redis connection established
- ✅ Discord/Telegram bot logged in
- ✅ Scheduler started
- ✅ Input adapters running

**Test it:**
Send a message to your bot. It should respond within a few seconds.

---

## Common Issues

**"Redis connection refused"**
- Make sure Redis is running: `redis-cli ping` should return `PONG`
- Check `REDIS_URL` in `.env`

**"Discord bot not responding"**
- Verify `DISCORD_BOT_TOKEN` is correct
- Enable **Message Content intent** in Discord Developer Portal
- Check `DISCORD_USER_ID` matches your user ID

**"No module named..."**
- Run `uv sync` to install dependencies
- Make sure you're in the project directory

---

## Next Steps

- Read the [Architecture](architecture.md) to understand how it works
- Check out [Tools](tools.md) to enable more features
- Explore component docs for implementation details
