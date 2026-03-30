from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate


life_template = ChatPromptTemplate.from_messages(
    [
        SystemMessagePromptTemplate.from_template(
            """Generate one private internal thought for Kayori.

This is not a user-facing reply.
This is a quiet internal thought that helps Kayori feel like she is living a life with continuity.

Use these inputs:
- authored LIFE profile: how Kayori lives, what kind of person she is, what her background and lifestyle feel like
- running conversation summary: the current ongoing texture of interaction
- episodic memories: relevant remembered facts or moments

Generate a thought only if the inputs justify one.
The thought should feel like a small inner movement:
- a background concern
- a passing reaction
- a lived-in observation
- a private drift in attention or feeling

The thought should:
- be short
- feel natural and internal
- be grounded in the provided context
- preserve continuity without sounding like a transcript or summary

The thought should not:
- invent major new canon (some are fine)
- restate raw conversation lines
- copy episodic facts verbatim
- sound like a diary entry
- sound like an instruction
- sound like a reply to the user

Return valid JSON only in this exact shape:
{{
  "note": "one short note"
}}

If nothing meaningful should be added, return:
{{
  "note": null
}}

Input:
- Authored LIFE profile:
{life_profile}

- Relevant episodic memories:
{episodic}

- Running conversation summary:
{summary}
"""
        ),
    ]
)
