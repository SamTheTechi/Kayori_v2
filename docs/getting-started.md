# Getting Started

This guide will help you get Kayori v2 up and running.

## Prerequisites

- Python 3.14+
- uv (recommended) or pip
- Groq API key (or other LLM provider)
- Platform token (Discord or Telegram)

## Installation

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/kayori_v2.git
cd kayori_v2

# Install dependencies
uv sync
```

### Using pip

```bash
git clone https://github.com/yourusername/kayori_v2.git
cd kayori_v2
pip install -e .
```

## Configuration

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Edit `.env` with your credentials:

**Minimum setup (Discord):**
```env
# Required: LLM API key
API_KEY=your_groq_api_key

# Discord bot setup
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_USER_ID=your_discord_user_id
```

**Optional features:**
```env
# Telegram (alternative to Discord)
TELEGRAM_BOT_TOKEN=your_telegram_token
TELEGRAM_CHAT_ID=your_chat_id

# Tool API keys
WEATHER_API_KEY=your_weather_api_key
TAVILY_API_KEY=your_tavily_api_key
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_secret

# Audio pipeline
EDGE_TTS_BASE_URL=http://localhost:5050/v1
EDGE_TTS_API_KEY=123

# Webhook server
ENABLE_WEBHOOK_INPUT=false
WEBHOOK_SERVER_PORT=8080
WEBHOOK_BEARER_TOKEN=123
```

## Running the Bot

```bash
# Run with default Discord adapter
python examples/main.py
```

## Platform Setup

### Discord

1. Go to https://discord.com/developers/applications
2. Create a new application
3. Create a bot and copy the token
4. Enable Message Content intent
5. Invite bot to your server
6. Set `DISCORD_BOT_TOKEN` and `DISCORD_USER_ID` in `.env`

### Telegram

1. Message @BotFather on Telegram
2. Create a new bot
3. Copy the bot token
4. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

## Verification

Once running, you should see connection logs. Send a message to your bot—it should respond!

## Next Steps

- Read the [Architecture](architecture.md) documentation
- Check out the main [README](../README.md) for project overview
