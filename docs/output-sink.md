# Output Sink

This document explains how outbound replies are routed to output adapters.

## Purpose

`OutputSink` in
[`src/core/outputsink.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/core/outputsink.py)
is the shared outbound dispatcher.

Its job is to:

- start and stop output adapters,
- choose which adapters should receive an outbound message,
- send to one or many outputs,
- log adapter failures without crashing the whole pipeline.

This keeps the orchestrator and tools from having to know about every specific
output adapter directly.

## High-Level API

The sink exposes three operations:

- `start()`
- `stop()`
- `send(message)`

The runtime uses it like any other output adapter.

## Routing Modes

The sink supports two modes:

- `direct`
- `multi`

### `direct`

In direct mode, the sink chooses only adapters whose `route_source` matches the
outbound message source.

Example:

- a `telegram` source message is sent only to Telegram outputs
- a `discord` source message is sent only to Discord outputs

This is the normal request-response mode.

### `multi`

In multi mode, the sink returns all configured outputs.

That means one outbound message fan-outs to every adapter in the sink.

This is useful for:

- broadcast-style testing
- mirrored outputs
- debugging multiple adapters at once

## Send Behavior

When `send(...)` is called:

1. the sink selects target adapters
2. it calls all selected adapters concurrently
3. it logs failures per adapter
4. it does not crash the whole send because one adapter failed

This is why the implementation uses `asyncio.gather(..., return_exceptions=True)`.

## Empty / Missing Output Cases

If no outputs are configured:

- `send(...)` returns immediately

If outputs exist but none match the current message:

- the sink logs `output_dropped_no_targets`

That makes dropped outbound messages visible without throwing runtime errors.

## Lifecycle

`start()` starts outputs in configured order.

`stop()` stops outputs in reverse order.

That is a small but useful lifecycle detail because teardown usually wants to
unwind dependencies in reverse order.

## Runtime Use

The orchestrator sends final replies through the sink.

Some tools also depend on an output adapter-like interface, so the sink lets
those tools reuse the same routing layer instead of writing directly to one
specific platform adapter.

## Tradeoffs

### Good Parts

- small, clear abstraction
- supports one-to-one and one-to-many routing
- adapter failures are isolated and logged
- the orchestrator only needs one outbound dependency

### Current Limits

- direct routing is based only on `message.source`
- there is no richer policy layer for priority, fallback, or per-channel rules
- the sink assumes all outputs can accept the same `OutboundMessage` shape

## File Reference

The implementation described here lives in
[`src/core/outputsink.py`](https://github.com/SamTheTechi/Kayori_v2/blob/main/src/core/outputsink.py).
