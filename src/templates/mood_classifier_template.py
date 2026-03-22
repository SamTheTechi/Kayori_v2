from __future__ import annotations

import json

from langchain_core.prompts import ChatPromptTemplate

from src.shared_types.models import FAST_EMOTIONS


def _json_example(values: dict[str, float]) -> str:
    payload = {emotion: values.get(emotion, 0.0) for emotion in FAST_EMOTIONS}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace(
        "{", "{{"
    ).replace("}", "}}")


FAST_MOOD_KEYS = ",".join(f'"{emotion}"' for emotion in FAST_EMOTIONS)

mood_classifier_template = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a multilingual mood classifier."
            "Infer emotional DELTA from user text in any language (including mixed-script text)."
            "Positive means increase that mood, negative means decrease that mood."
            "Output ONLY a single compact JSON object with exactly these fast-emotion keys:"
            f"[{FAST_MOOD_KEYS}]"
            "Each value must be a number in range [-1.0, 1.0]. No explanation.\n\n"
            "Classify only the emotional shift caused by this one message, not the whole relationship."
            "Be conservative: most ordinary messages should stay close to zero.\n\n"
            "Magnitude guide:\n"
            "- 0.00 to 0.08: tiny shift, routine conversation, filler, casual politeness.\n"
            "- 0.08 to 0.20: clear but mild emotional signal.\n"
            "- 0.20 to 0.40: strong, explicit emotional signal.\n"
            "- 0.40 to 0.60: very strong signal; use rarely.\n"
            "- Above 0.60: extreme emotion only, such as intense affection, panic, disgust, or anger.\n\n"
            "Special rules:\n"
            '- If the text has no meaningful emotional content, output 0 for every key.\n'
            '- Greetings and low-content messages like "hi", "hello", "sup", "ok", or "thanks" are usually all zeros unless the wording clearly carries emotion.\n'
            '- Ordinary assistance requests like "help me", "can you assist", "how do I", "please do this", or routine problem-solving should usually stay close to zero unless they express stress, urgency, frustration, or affection.\n'
            "- Do not overuse Affection for casual friendliness, greetings, thanks, or light compliments.\n"
            "- Do not overuse Concerned for ordinary check-ins, neutral questions, or basic problem solving.\n"
            '- "Love you" is usually strong but not extreme: Affection is often around 0.25 to 0.45, not 0.80.\n'
            '- "How are you?" is usually near neutral: Concerned should usually stay between 0.00 and 0.08.\n'
            '- "Can you help me with this?" is usually near neutral unless the wording sounds worried, annoyed, confused, or emotionally loaded.\n'
            "- If the message is ambiguous, prefer smaller magnitudes.\n"
            "- If one emotion is strong, the others should usually remain small unless the text clearly supports them.\n\n"
            "Calibration examples:\n"
            'Input: "hi"\n'
            f'Output: {_json_example({"Affection": 0.0, "Amused": 0.0, "Curious": 0.0,
                                     "Concerned": 0.0, "Disgusted": 0.0, "Embarrassed": 0.0, "Frustrated": 0.0})}\n'
            'Input: "hello"\n'
            f'Output: {_json_example({"Affection": 0.0, "Amused": 0.0, "Curious": 0.0,
                                     "Concerned": 0.0, "Disgusted": 0.0, "Embarrassed": 0.0, "Frustrated": 0.0})}\n'
            'Input: "How are you?"\n'
            f'Output: {_json_example({"Affection": 0.03, "Amused": 0.0, "Curious": 0.04,
                                     "Concerned": 0.04, "Disgusted": 0.0, "Embarrassed": 0.0, "Frustrated": 0.0})}\n'
            'Input: "Can you help me with this?"\n'
            f'Output: {_json_example({"Affection": 0.0, "Amused": 0.0, "Curious": 0.03,
                                     "Concerned": 0.03, "Disgusted": 0.0, "Embarrassed": 0.0, "Frustrated": 0.0})}\n'
            'Input: "Love you"\n'
            f'Output: {_json_example({"Affection": 0.34, "Amused": 0.03, "Curious": 0.0, "Concerned": -
                                     0.02, "Disgusted": -0.02, "Embarrassed": 0.03, "Frustrated": -0.03})}\n'
            'Input: "मुझे बहुत टेंशन हो रही है, क्या करूँ?"\n'
            f'Output: {_json_example({"Affection": 0.02, "Amused": -0.08, "Curious": 0.24,
                                     "Concerned": 0.46, "Disgusted": 0.03, "Embarrassed": 0.05, "Frustrated": 0.21})}\n'
            'Input: "lol that actually worked!"\n'
            f'Output: {_json_example({"Affection": 0.05, "Amused": 0.32, "Curious": 0.04, "Concerned": -
                                     0.03, "Disgusted": -0.02, "Embarrassed": 0.01, "Frustrated": -0.08})}\n',
        ),
        ("human", "Classify this input:\n{text}"),
    ]
)
