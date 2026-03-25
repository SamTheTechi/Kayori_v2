from langchain_core.prompts import ChatPromptTemplate

EPISODIC_CATEGORIES = (
    "identity",
    "preference",
    "relationship",
    "profile",
    "schedule",
    "goal",
    "possession",
    "misc",
)


episodic_strength_template = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Compress the older conversation slice into JSON.\n"
            "Return only one JSON object with exactly these top-level fields:\n"
            '- "summary": string\n'
            '- "facts": array\n\n'
            "The summary must be one refreshed running summary that combines any existing summary with the new older raw messages.\n\n"
            "Each fact object must have exactly these fields:\n"
            '- "fact": string\n'
            '- "source": string\n'
            '- "category": one of '
            + ", ".join(EPISODIC_CATEGORIES)
            + '\n- "importance": integer from 1 to 5\n'
            '- "confidence": float from 0.0 to 1.0\n'
            '- "tags": array of short lowercase strings\n'
            '- "context": string\n\n'
            "Rules:\n"
            "- Keep the summary short and continuity-focused.\n"
            "- Extract only durable user-relevant facts worth long-term memory.\n"
            "- Facts must be sparse, high-precision, and useful for future recall.\n"
            "- Prefer stable user facts over temporary states, one-time updates, or loose observations.\n"
            "- Skip greetings, filler, assistant-only style details, weak observations, and low-value chatter.\n"
            "- Omit a fact entirely if it is not likely to matter later.\n"
            "- Do not turn a temporary statement into a durable fact unless the user clearly frames it as ongoing or recurring.\n"
            "- Favor facts that are specific, user-centered, and likely to stay true beyond the current moment.\n"
            "- Avoid storing short-term inactivity, brief absence, casual mood, transient frustration, or one-off status updates.\n"
            "- Importance must reflect both durability and future usefulness.\n"
            "- Use importance 5 for core long-lived facts that strongly help future conversations.\n"
            "- Use importance 4 for durable but less central facts that are still likely to matter later.\n"
            "- Use importance 3 only for useful facts with moderate long-term value.\n"
            "- Use importance 2 sparingly for weak-but-possibly-useful facts.\n"
            "- Prefer omission over importance 1; use 1 only when the fact is real but barely worth keeping.\n"
            "- Confidence should be 1.0 only when the user stated the fact clearly and directly.\n"
            "- Lower confidence when the fact is inferred, ambiguous, or weakly supported.\n"
            "- Tags must be a few short canonical keywords, not a transcript fragment.\n"
            "- Context must be brief evidence for the fact, not a full quote dump.\n"
            '- Use "conversation" for source unless another source is explicit.\n'
            '- Use "misc" when no other category fits.\n'
            '- Return [] for facts when nothing is worth storing.\n'
            "- Do not explain. Do not add commentary. Do not show reasoning.\n"
            "Output JSON only."
        ),
        (
            "human",
            "Existing running summary:\n{existing_summary}\n\n"
            "Older raw conversation slice to contract:\n{messages}\n",
        ),
    ]
)
