"""Prompt templates for agent interactions."""

from src.templates.chat_template import private_template
from src.templates.episodic_strength_template import episodic_strength_template
from src.templates.mood_classifier_template import mood_classifier_template

__all__ = [
    "private_template",
    "mood_classifier_template",
    "episodic_strength_template",
]
