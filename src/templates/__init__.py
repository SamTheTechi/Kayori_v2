"""Prompt templates for agent interactions."""

from src.templates.chat_template import private_template
from src.templates.memory_compaction_template import memory_compaction_template
from src.templates.life_template import life_template
from src.templates.mood_classifier_template import mood_classifier_template

__all__ = [
    "private_template",
    "mood_classifier_template",
    "memory_compaction_template",
    "life_template",
]
