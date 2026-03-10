# Getting Started

This guide will help you get Kayori v2 up and running.

## Prerequisites

- Python 3.14+
- uv (recommended) or pip
- A Groq API key (or other LLM provider)
- Platform-specific tokens (Discord, Telegram) one is sufficient enough

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

Make Sure to Create and Active virtual env

## Configuration

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Edit `.env` with your credentials:

```env
# Required: LLM API key
API_KEY=your_groq_api_key

# For Discord (default)
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_USER_ID=your_discord_user_id

# Optional: Tool API keys
WEATHER_API_KEY=your_weather_api_key
TAVILY_API_KEY=your_tavily_api_key
```

## Running the Bot

```bash
# Run with default Discord adapter
python examples/main.py
```

## Platform Setup

### Discord

1. Create a Discord application at https://discord.com/developers/applications
2. Create a bot and copy the token
3. Enable required intents (Message Content, etc.)
4. Invite the bot to your server
5. Set `DISCORD_BOT_TOKEN` and `DISCORD_USER_ID` in `.env`

### Telegram

1. Create a bot via @BotFather on Telegram
2. Copy the bot token
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

## Verification

Once running, you should see logs indicating the bot is connected. Send a message to your bot and it should respond!

## Next Steps

- Read the [Architecture](architecture.md) documentation
- Review the main project overview in `README.md`
