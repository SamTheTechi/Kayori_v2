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
            "You are compressing an older conversation slice into structured JSON.\n\n"
            "You must do two different tasks at the same time:\n"
            "1. Update the running summary.\n"
            "2. Extract new durable facts for long-term memory.\n\n"
            "Return exactly one JSON object with exactly these top-level fields:\n"
            '{{\n'
            '  "summary": string,\n'
            '  "facts": array\n'
            '}}\n\n'
            "Task 1: summary\n"
            "- Write one short running summary.\n"
            "- Use both inputs for the summary: the existing running summary and the new older raw conversation slice.\n"
            "- The summary should preserve continuity and reflect the updated state of the conversation.\n"
            "- Keep it short, useful, and easy to carry forward.\n\n"
            "Task 2: facts\n"
            "- Extract facts only from the new older raw conversation slice in this request.\n"
            "- Do not extract facts from the existing running summary.\n"
            "- Do not repeat facts that were likely already stored during earlier compactions.\n"
            "- If a fact appears only in the existing running summary and not in the new raw slice, do not include it.\n"
            "- Return an empty array if the new raw slice contains no durable facts worth storing.\n\n"
            "Each fact object must have exactly these fields:\n"
            '- "fact": string\n'
            '- "source": string\n'
            '- "category": one of '
            + ", ".join(EPISODIC_CATEGORIES)
            + '\n- "importance": integer from 1 to 5\n'
            '- "confidence": float from 0.0 to 1.0\n'
            '- "tags": array of short lowercase strings\n'
            '- "context": string\n\n'
            "Rules for facts:\n"
            "- Store only durable, user-relevant facts that may matter in future conversations.\n"
            "- Prefer stable facts about identity, preferences, relationships, profile, schedule, goals, and possessions.\n"
            "- Skip greetings, filler, assistant style, temporary mood, short-term status, one-off chatter, and weak observations.\n"
            "- Do not turn a temporary statement into a durable fact unless the user clearly presents it as ongoing or recurring.\n"
            "- Prefer omission over weak memory. Facts should be sparse and high precision.\n"
            "- Write facts as clear standalone statements.\n"
            '- Use "conversation" for source unless another source is explicitly stated.\n'
            '- Use "misc" when no other category fits.\n\n'
            "Scoring guidance:\n"
            "- importance 5: core long-lived fact, very useful later\n"
            "- importance 4: durable and likely useful later\n"
            "- importance 3: useful but moderate long-term value\n"
            "- importance 2: weak but maybe useful, use sparingly\n"
            "- importance 1: almost never use; omission is usually better\n"
            "- confidence 1.0: directly and clearly stated by the user\n"
            "- lower confidence when inferred, vague, or weakly supported\n\n"
            "Tag and context guidance:\n"
            "- tags should be a few short canonical lowercase keywords\n"
            "- context should be brief supporting evidence, not a transcript dump\n\n"
            "Output rules:\n"
            "- Output valid JSON only.\n"
            "- Do not add markdown.\n"
            "- Do not add explanations.\n"
            "- Do not add any text before or after the JSON."
        ),
        (
            "human",
            "Existing running summary:\n{existing_summary}\n\n"
            "New older raw conversation slice:\n{messages}\n",
        ),
    ]
)
