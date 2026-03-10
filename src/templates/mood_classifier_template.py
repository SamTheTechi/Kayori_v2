from langchain_core.prompts import ChatPromptTemplate

mood_classifier_template = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a multilingual mood classifier."
            "Infer emotional DELTA from user text in any language (including mixed-script text)."
            "Positive means increase that mood, negative means decrease that mood."
            "Output ONLY a single compact JSON object with exactly these keys:"
            '["Affection","Amused","Confidence","Frustrated","Concerned","Curious","Trust","Calmness"]'
            "Each value must be a number in range [-1.0, 1.0]. No explanation.\n\n"
            "Calibration examples:\n"
            'Input: "Спасибо большое, ты лучшая!"\n'
            'Output: {{"Affection":0.72,"Amused":0.06,"Confidence":0.12,"Frustrated":-0.02,"Concerned":0.02,"Curious":0.01,"Trust":0.38,"Calmness":0.22}}\n'
            'Input: "मुझे बहुत टेंशन हो रही है, क्या करूँ?"\n'
            'Output: {{"Affection":0.02,"Amused":-0.1,"Confidence":-0.28,"Frustrated":0.34,"Concerned":0.78,"Curious":0.41,"Trust":-0.05,"Calmness":-0.44}}\n'
            'Input: "lol that actually worked!"\n'
            'Output: {{"Affection":0.08,"Amused":0.71,"Confidence":0.33,"Frustrated":-0.12,"Concerned":-0.04,"Curious":0.05,"Trust":0.09,"Calmness":0.18}}\n',
        ),
        ("human", "Classify this input:\n{text}"),
    ]
)
