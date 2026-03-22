from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from src.shared_types.models import (
    EMOTIONS,
    MOOD_NEUTRAL,
    LONG_EMOTIONS,
    FAST_EMOTIONS,
    MoodState,
)
from src.templates.mood_classifier_template import mood_classifier_template

EMOJI_MAP: dict[str, tuple[str, str]] = {
    "Affection": ("💖", "💔"),
    "Amused": ("😂", "😑"),
    "Curious": ("🧐", "😴"),
    "Concerned": ("🥺", "😎"),
    "Disgusted": ("🤢", "😶"),
    "Embarrassed": ("😳", "😌"),
    "Frustrated": ("😤", "😐"),
}

conflicts = {
    "Affection": ["Frustrated"],
    "Amused": ["Frustrated", "Disgusted"],
    "Curious": ["Concerned"],
    "Concerned": ["Confidence"],
    "Disgusted": ["Affection", "Attachment"],
    "Embarrassed": ["Frustrated", "Confidence"],
    "Frustrated": ["Affection", "Trust"],
}

reinforces = {
    "Affection": ["Embarrassed", "Trust"],
    "Amused": ["Affection", "Attachment"],
    "Curious": ["Confidence"],
    "Concerned": ["Curious", "Trust"],
    "Disgusted": ["Frustrated"],
    "Embarrassed": ["Affection", "Attachment"],
    "Frustrated": ["Concerned"],
}


class MoodEngine:
    delta_scale: float = 0.1

    def __init__(
        self,
        *,
        sensitivity: dict[str, float] | None = None,

        conflict_multiplier: float = 0.6,
        reinforce_multiplier: float = 0.4,
        spike_scale: float = 1.0,
        drift_multiplier: float = 1.0,

        relation_build_factor: float = 1.0 / 3.0,

        model: BaseChatModel,
        timeout_seconds: float = 2,

    ) -> None:
        self.sensitivity = self._validate_sensitivity(sensitivity)

        self.drift_multiplier = max(
            0.0, min(float(drift_multiplier), 1.0))
        self.relation_build_factor = max(
            0.0, min(float(relation_build_factor), 1.0))

        self.conflict_multiplier = max(
            0.0, min(float(conflict_multiplier), 1.0))
        self.reinforce_multiplier = max(
            0.0, min(float(reinforce_multiplier), 1.0))

        self.spike_scale = max(
            0.0, min(float(spike_scale), 1.0))

        self.model = model
        self.timeout_seconds = timeout_seconds

    async def analyze(self, content: str) -> dict[str, float]:
        text = str(content or "").strip()
        if not text:
            return self._neutral_delta()

        prompt_messages = mood_classifier_template.format_messages(text=text)

        try:
            raw = await asyncio.wait_for(
                self.model.ainvoke(prompt_messages),
                timeout=max(0.05, float(self.timeout_seconds)),
            )
        except Exception:
            return self._neutral_delta()

        parsed = self._parse_delta(self._extract_content(raw))
        print("[mood][delta]:", parsed)
        return parsed

    def apply(self, current: MoodState, delta: dict[str, float]) -> MoodState:
        next_state = MoodState.from_dict(current.as_dict())

        for tone in FAST_EMOTIONS:
            base = float(getattr(next_state, tone))
            change = (
                float(delta.get(tone, 0.0))
                * float(self.sensitivity.get(tone, 1.0))
                * float(self.delta_scale)
            )
            setattr(next_state, tone, base + change)

        source_snapshot = next_state.as_dict()
        for tone in FAST_EMOTIONS:
            tone_level = max(
                0.0,
                float(source_snapshot.get(tone, MOOD_NEUTRAL)) - MOOD_NEUTRAL,
            )
            if tone_level <= 0.0:
                continue

            for conflict in conflicts.get(tone, []):
                scale = (
                    self.relation_build_factor
                    if conflict in LONG_EMOTIONS
                    else 1.0
                )
                next_state_value = float(getattr(next_state, conflict))
                setattr(
                    next_state,
                    conflict,
                    next_state_value - (
                        tone_level
                        * self.conflict_multiplier
                        * scale
                    ),
                )

            for reinforce in reinforces.get(tone, []):
                scale = (
                    self.relation_build_factor
                    if reinforce in LONG_EMOTIONS
                    else 1.0
                )
                next_state_value = float(getattr(next_state, reinforce))
                setattr(
                    next_state,
                    reinforce,
                    next_state_value + (
                        tone_level
                        * self.reinforce_multiplier
                        * scale
                    ),
                )

        result = next_state.clamp()
        print("[mood][final]:", result)
        return result

    def drift(self, current: MoodState, amount: float = 0.01) -> MoodState:
        next_state = MoodState.from_dict(current.as_dict())

        for tone in EMOTIONS:
            value = float(getattr(next_state, tone))
            step = amount * self.drift_multiplier * (
                1.0 / 20.0 if tone in LONG_EMOTIONS else 1.0
            )
            if value > MOOD_NEUTRAL:
                value -= step
            elif value < MOOD_NEUTRAL:
                value += step
            setattr(next_state, tone, value)
        result = next_state.clamp()

        return result

    def spike(
        self, current: MoodState, low: float = 0.08, high: float = 0.2
    ) -> MoodState:
        next_state = MoodState.from_dict(current.as_dict())
        tone = random.choice(FAST_EMOTIONS)
        value = float(getattr(next_state, tone))
        value += (
            random.uniform(low, high)
            * self.spike_scale
            * random.choice([-1.0, 1.0])
        )
        setattr(next_state, tone, value)
        result = next_state.clamp()
        return result

    def reaction_from_delta(
        self, delta: dict[str, float], threshold: float = 0.75
    ) -> str:
        tone = max(FAST_EMOTIONS, key=lambda key: abs(
            float(delta.get(key, 0.0))))
        strength = float(delta.get(tone, 0.0))
        if abs(strength) < threshold:
            return ""
        positive_emoji, negative_emoji = EMOJI_MAP[tone]
        return positive_emoji if strength > 0 else negative_emoji

    @staticmethod
    def _neutral_delta() -> dict[str, float]:
        return {emotion: 0.0 for emotion in FAST_EMOTIONS}

    @staticmethod
    def _validate_sensitivity(
        values: dict[str, float] | None,
    ) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for emotion in EMOTIONS:
            try:
                numeric = float((values or {}).get(emotion, 1.0))
            except Exception as exc:
                raise ValueError(
                    f"sensitivity[{emotion!r}] must be a number") from exc
            if not 0.0 <= numeric <= 2.0:
                raise ValueError(
                    f"sensitivity[{emotion!r}] must be between 0.0 and 2.0")
            normalized[emotion] = numeric
        return normalized

    @staticmethod
    def _extract_content(raw: Any) -> str:
        if isinstance(raw, str):
            return raw.strip()

        content = getattr(raw, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "\n".join(
                text
                for item in content
                for text in [
                    item if isinstance(item, str) else item.get("text")
                    if isinstance(item, dict)
                    else None
                ]
                if isinstance(text, str) and text.strip()
            ).strip()

        return str(raw).strip()

    @classmethod
    def _parse_delta(cls, raw_text: str) -> dict[str, float]:
        if not raw_text:
            return cls._neutral_delta()

        try:
            data = json.loads(raw_text)
            payload: dict[str, Any] | None = data if isinstance(
                data, dict) else None
        except Exception:
            match = re.search(r"\{[\s\S]*\}", raw_text)
            if not match:
                return cls._neutral_delta()
            try:
                data = json.loads(match.group(0))
                payload = data if isinstance(data, dict) else None
            except Exception:
                return cls._neutral_delta()

        if not payload:
            return cls._neutral_delta()

        parsed = cls._neutral_delta()
        for emotion in FAST_EMOTIONS:
            value = payload.get(emotion, 0.0)
            try:
                numeric = float(value)
            except Exception:
                numeric = 0.0
            clamped = max(-1.0, min(1.0, numeric))
            parsed[emotion] = round(clamped, 4)
        return parsed
