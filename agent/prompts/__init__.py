"""Prompt templates for agent interactions."""

from agent.prompts.chat_template import private_template
from agent.prompts.memory_compaction_template import memory_compaction_template
from agent.prompts.life_template import life_template
from agent.prompts.mood_classifier_template import mood_classifier_template

__all__ = [
    "private_template",
    "mood_classifier_template",
    "memory_compaction_template",
    "life_template",
]
