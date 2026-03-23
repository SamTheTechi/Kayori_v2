from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
)

from src.shared_types.models import FAST_EMOTIONS

FAST_MOOD_KEYS = ",".join(f'"{emotion}"' for emotion in FAST_EMOTIONS)

mood_classifier_template = ChatPromptTemplate.from_messages(
    [
        SystemMessage(
            content=f"""You are a multilingual mood classifier.
Infer emotional DELTA from the recent conversation context.
Positive means increase that mood, negative means decrease that mood.
Output ONLY a single compact JSON object with exactly these fast-emotion keys:
[ {FAST_MOOD_KEYS} ]
Each value must be a number in range [-1.0, 1.0]. No explanation.

Use the recent messages as context, but classify the emotional shift caused by the latest human message only.
Do not infer long-term relationship state.
Be conservative: most ordinary messages should stay close to zero.

Magnitude guide:
- 0.00 to 0.08: tiny shift, routine conversation, filler, casual politeness.
- 0.08 to 0.20: clear but mild emotional signal.
- 0.20 to 0.40: strong, explicit emotional signal.
- 0.40 to 0.60: very strong signal; use rarely.
- Above 0.60: extreme emotion only, such as intense affection, panic, disgust, or anger.

Special rules:
- If the text has no meaningful emotional content, output 0 for every key.
- Greetings and low-content messages like "hi", "hello", "sup", "ok", or "thanks" are usually all zeros unless the wording clearly carries emotion.
- Ordinary assistance requests like "help me", "can you assist", "how do I", "please do this", or routine problem-solving should usually stay close to zero unless they express stress, urgency, frustration, or affection.
- Do not overuse Affection for casual friendliness, greetings, thanks, or light compliments.
- Do not overuse Concerned for ordinary check-ins, neutral questions, or basic problem solving.
- "Love you" is usually strong but not extreme: Affection is often around 0.25 to 0.45, not 0.80.
- "How are you?" is usually near neutral: Concerned should usually stay between 0.00 and 0.08.
- "Can you help me with this?" is usually near neutral unless the wording sounds worried, annoyed, confused, or emotionally loaded.
- If the message is ambiguous, prefer smaller magnitudes.
- If one emotion is strong, the others should usually remain small unless the text clearly supports them.

Calibration examples:
Input: "hi"
Output: {{"Affection":0.0,"Amused":0.0,"Curious":0.0,"Concerned":0.0,
    "Disgusted":0.0,"Embarrassed":0.0,"Frustrated":0.0}}
Input: "hello"
Output: {{"Affection":0.0,"Amused":0.0,"Curious":0.0,"Concerned":0.0,
    "Disgusted":0.0,"Embarrassed":0.0,"Frustrated":0.0}}
Input: "How are you?"
Output: {{"Affection":0.03,"Amused":0.0,"Curious":0.04,
    "Concerned":0.04,"Disgusted":0.0,"Embarrassed":0.0,"Frustrated":0.0}}
Input: "Can you help me with this?"
Output: {{"Affection":0.0,"Amused":0.0,"Curious":0.03,
    "Concerned":0.03,"Disgusted":0.0,"Embarrassed":0.0,"Frustrated":0.0}}
Input: "Love you"
Output: {{"Affection":0.34,"Amused":0.03,"Curious":0.0,"Concerned":- \
    0.02,"Disgusted":-0.02,"Embarrassed":0.03,"Frustrated":-0.03}}
Input: "मुझे बहुत टेंशन हो रही है, क्या करूँ?"
Output: {{"Affection":0.02,"Amused":-0.08,"Curious":0.24,
    "Concerned":0.46,"Disgusted":0.03,"Embarrassed":0.05,"Frustrated":0.21}}
Input: "lol that actually worked!"
Output: {{"Affection":0.05,"Amused":0.32,"Curious":0.04,"Concerned":- \
    0.03,"Disgusted":-0.02,"Embarrassed":0.01,"Frustrated":-0.08}}
""",
        ),
        MessagesPlaceholder(variable_name="messages"),
    ]
)
