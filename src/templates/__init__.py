"""Prompt templates for agent interactions."""

from templates.chat_template import private_template
from templates.episodic_strength_template import episodic_strength_template
from templates.mood_classifier_template import mood_classifier_template

__all__ = [
    "private_template",
    "mood_classifier_template",
    "episodic_strength_template",
]
