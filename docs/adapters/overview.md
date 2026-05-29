# Adapters Overview

Adapters isolate platform and infrastructure concerns from the runtime logic.

## The Adapter Boundary

The core runtime depends on protocol interfaces from `shared_types/protocol.py`, not on concrete platform or backend implementations.

Current adapter groups:
- Input adapters publish `MessageEnvelope` objects to the message bus
- Output adapters deliver `OutboundMessage` objects to external platforms
- Runtime adapters manage platform connection lifecycle
- Backend adapters implement message bus, state, memory, and scheduler storage
- HTTP adapters register dashboard, logs, metrics, and ping routes on the webhook runtime
- Audio adapters provide STT and TTS integrations used by the orchestrator

## Adapter Categories

### Input Adapters

Current input adapters:
- `DiscordInputAdapter`
- `TelegramInputAdapter`
- `WebhookInputAdapter`
- `ConsoleInputGateway`

They convert external events into `MessageEnvelope` objects and publish them to the configured `MessageBus`.

### Output Adapters

Current output adapters:
- `DiscordOutputAdapter`
- `TelegramOutputAdapter`
- `WebhookOutputAdapter`
- `ConsoleOutputAdapter`

They accept `OutboundMessage` objects selected by `OutputSink` and translate them into platform-specific sends.

### Runtime Adapters

Current runtime adapters:
- `DiscordRuntime`
- `TelegramRuntime`
- `WebhookRuntime`

These runtimes manage SDK startup, connection state, route registration, and shared lifecycle for the corresponding input and output adapters.

### Backend Adapters

Current backend modules:
- `bus/` for message queue implementations
- `state/` for state store implementations
- `memory/` for episodic memory backends
- `scheduler/` for trigger storage backends

The production runtime in `main.py` currently wires Redis-backed implementations for bus, state, scheduler, and episodic memory.

## How Adapters Connect

### Example: Discord Text Flow

```
DiscordRuntime
  -> DiscordInputAdapter
  -> MessageEnvelope
  -> MessageBus
  -> AgentOrchestrator
  -> OutputSink
  -> DiscordOutputAdapter
```

### Example: Webhook Request Flow

```
WebhookRuntime route
  -> WebhookInputAdapter
  -> MessageEnvelope
  -> MessageBus
  -> AgentOrchestrator
  -> WebhookOutputAdapter
```

For synchronous webhook request/response, the webhook runtime also holds a pending response future keyed by envelope ID.

## Current Production Setup

From `main.py`:
- one primary chat app is selected with `PRIMARY_CHAT_APP`
- webhook input and webhook output are also wired
- Redis-backed bus, state, scheduler, and episodic memory are used
- generic audio support is available through adapters that publish `AudioPayload`

## Adapter Directory Structure

```text
gateway/
├── platforms/  # Per-platform adapters (input.py / output.py / runtime.py)
├── bus/        # Message bus implementations
├── state/      # State store backends
├── memory/     # Episodic memory backends
├── scheduler/  # Scheduler backends
├── audio/      # STT and TTS adapters
├── http/       # Dashboard, logs, metrics, ping routes
└── webhook_common.py
```

## Extending the Adapter Layer

To add a new platform:
1. Add a runtime if the platform needs a managed lifecycle
2. Add an input adapter that publishes `MessageEnvelope`
3. Add an output adapter that accepts `OutboundMessage`
4. Register the new adapter in the builders in `main.py`

## File References

- [`shared_types/protocol.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/shared_types/protocol.py)
- [`main.py`](https://github.com/SamTheTechi/Kayori_v2/blob/master/main.py)

## Related

- [Input Adapters](input.md)
- [Output Adapters](output.md)
- [Backend Adapters](backends.md)
- [Architecture](../architecture.md)
