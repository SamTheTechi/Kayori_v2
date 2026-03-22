from __future__ import annotations


def resolve_thread_id(
    *,
    target_user_id: str | None = None,
    channel_id: str | None = None,
    author_id: str | None = None,
    fallback_user_id: str | None = None,
    default: str = "global",
) -> str:
    """Resolve the canonical thread key for a message or trigger.

    The precedence is intentionally shared across the codebase so state,
    history, mood, and scheduled actions all point to the same key.
    """

    for candidate in (
        target_user_id,
        channel_id,
        author_id,
        fallback_user_id,
    ):
        key = str(candidate or "").strip()
        if key:
            return key
    return str(default or "").strip() or "global"
