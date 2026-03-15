from __future__ import annotations

import asyncio
import json
import random
import re
from dataclasses import dataclass
from os import getenv
from typing import Any

from shared_types.models import (
    EMOTIONS,
    FAST_EMOTIONS,
    MOOD_NEUTRAL,
    SLOW_EMOTIONS,
    MoodState,
)
from templates.mood_classifier_template import mood_classifier_template

EMOJI_MAP: dict[str, tuple[str, str]] = {
    "Affection": ("💖", "💔"),
    "Amused": ("😂", "😑"),
    "Confidence": ("🫡", "😶"),
    "Frustrated": ("😤", "😌"),
    "Concerned": ("🥺", "😎"),
    "Curious": ("🧐", "😴"),
    "Trust": ("🤝", "🫥"),
    "Calmness": ("🧘", "😵"),
}


@dataclass(slots=True)
class MoodEngine:
    sensitivity: dict[str, float]
    conflict_multiplier: float = 0.08
    reinforce_multiplier: float = 0.04
    fast_change_multiplier: float = 1.0
    slow_change_multiplier: float = 0.45
    fast_drift_multiplier: float = 1.0
    slow_drift_multiplier: float = 0.45
    fast_spike_scale: float = 1.0
    slow_spike_scale: float = 0.4
    classifier_model: Any | None = None
    classifier_model_name: str = "llama-3.1-8b-instant"
    classifier_timeout_seconds: float = 0.4

    def analyze_delta(self, content: str) -> dict[str, float]:
        # Compatibility path: dynamic analyzer is async only.
        _ = content
        return _neutral_delta()

    async def analyze_delta_async(self, content: str) -> dict[str, float]:
        text = str(content or "").strip()
        if not text:
            return _neutral_delta()

        model = await self._classifier()
        if model is None:
            return _neutral_delta()

        prompt_messages = mood_classifier_template.format_messages(text=text)
        try:
            raw = await asyncio.wait_for(
                model.ainvoke(prompt_messages),
                timeout=max(0.05, float(self.classifier_timeout_seconds)),
            )
        except Exception:
            return _neutral_delta()

        return _parse_delta(_extract_content(raw))

    async def _classifier(self) -> Any | None:
        if self.classifier_model is not None:
            return self.classifier_model

        # Lazy import to keep module load cheap and avoid hard failure when env is missing.
        try:
            from langchain_groq import ChatGroq
        except Exception:
            return None

        api_key = str(getenv("API_KEY", "") or "").strip()
        if not api_key:
            return None

        try:
            self.classifier_model = ChatGroq(
                model=self.classifier_model_name,
                temperature=0,
                api_key=api_key,
            )
        except Exception:
            return None
        return self.classifier_model

    def apply(self, current: MoodState, delta: dict[str, float]) -> MoodState:
        next_state = MoodState.from_dict(current.as_dict())

        conflicts = {
            "Affection": ["Frustrated"],
            "Frustrated": ["Affection", "Trust", "Calmness"],
            "Confidence": ["Concerned"],
            "Curious": ["Concerned"],
            "Concerned": ["Calmness", "Confidence"],
            "Trust": ["Frustrated"],
            "Calmness": ["Frustrated", "Concerned"],
        }
        reinforces = {
            "Affection": ["Trust", "Calmness"],
            "Amused": ["Affection", "Calmness"],
            "Confidence": ["Trust", "Calmness"],
            "Concerned": ["Frustrated"],
            "Curious": ["Confidence"],
            "Trust": ["Affection", "Calmness"],
            "Calmness": ["Trust", "Confidence"],
        }

        for tone in EMOTIONS:
            base = float(getattr(next_state, tone))
            tempo_multiplier = (
                self.slow_change_multiplier
                if tone in SLOW_EMOTIONS
                else self.fast_change_multiplier
            )
            change = (
                float(delta.get(tone, 0.0))
                * float(self.sensitivity.get(tone, 0.3))
                * float(tempo_multiplier)
            )
            value = base + change

            for conflict in conflicts.get(tone, []):
                conflict_distance = float(
                    getattr(next_state, conflict)) - MOOD_NEUTRAL
                value -= conflict_distance * self.conflict_multiplier

            for reinforce in reinforces.get(tone, []):
                reinforce_distance = (
                    float(getattr(next_state, reinforce)) - MOOD_NEUTRAL
                )
                value += reinforce_distance * self.reinforce_multiplier

            drift_rate = 0.08 * (
                self.slow_drift_multiplier
                if tone in SLOW_EMOTIONS
                else self.fast_drift_multiplier
            )
            drift = abs(value - MOOD_NEUTRAL) * drift_rate
            if value > MOOD_NEUTRAL:
                value -= drift
            elif value < MOOD_NEUTRAL:
                value += drift
            setattr(next_state, tone, value)

        return next_state.clamp()

    def drift(self, current: MoodState, amount: float = 0.01) -> MoodState:
        next_state = MoodState.from_dict(current.as_dict())
        for tone in EMOTIONS:
            value = float(getattr(next_state, tone))
            step = amount * (
                self.slow_drift_multiplier
                if tone in SLOW_EMOTIONS
                else self.fast_drift_multiplier
            )
            if value > MOOD_NEUTRAL:
                value -= step
            elif value < MOOD_NEUTRAL:
                value += step
            setattr(next_state, tone, value)
        return next_state.clamp()

    def spike(
        self, current: MoodState, low: float = 0.08, high: float = 0.2
    ) -> MoodState:
        next_state = MoodState.from_dict(current.as_dict())
        weighted_tones = [*FAST_EMOTIONS, *FAST_EMOTIONS, *SLOW_EMOTIONS]
        tone = random.choice(weighted_tones)
        spike_scale = (
            self.slow_spike_scale if tone in SLOW_EMOTIONS else self.fast_spike_scale
        )
        value = float(getattr(next_state, tone))
        value += random.uniform(low, high) * spike_scale * \
            random.choice([-1.0, 1.0])
        setattr(next_state, tone, value)
        return next_state.clamp()

    def reaction_from_delta(
        self, delta: dict[str, float], threshold: float = 0.75
    ) -> str:
        tone = max(EMOTIONS, key=lambda key: abs(float(delta.get(key, 0.0))))
        strength = float(delta.get(tone, 0.0))
        if abs(strength) < threshold:
            return ""
        positive_emoji, negative_emoji = EMOJI_MAP[tone]
        return positive_emoji if strength > 0 else negative_emoji


def _neutral_delta() -> dict[str, float]:
    return dict.fromkeys(EMOTIONS, 0.0)


def _extract_content(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()

    content = getattr(raw, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()

    return str(raw).strip()


def _parse_delta(raw_text: str) -> dict[str, float]:
    if not raw_text:
        return _neutral_delta()

    payload: dict[str, Any] | None = None
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            payload = data
    except Exception:
        match = re.search(r"\{[\s\S]*\}", raw_text)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    payload = data
            except Exception:
                payload = None

    if payload is None:
        return _neutral_delta()

    parsed = _neutral_delta()
    for emotion in EMOTIONS:
        value = payload.get(emotion, 0.0)
        try:
            numeric = float(value)
        except Exception:
            numeric = 0.0
        clamped = max(-1.0, min(1.0, numeric))
        parsed[emotion] = round(clamped, 4)
    return parsed
