from langchain_core.prompts import ChatPromptTemplate


episodic_strength_template = ChatPromptTemplate.from_messages([
    ("system",
     "Score long-term memory importance for this episode. "
     "Return strength in [0,1], where 1 means highly important for future personalization."
     ),
    ("human",
     "summary: {summary}\n"
     "context: {context}\n"
     "source: {source}\n"
     "emotion: {emotion}\n"
     "salience_1_to_5: {salience}\n"
     ),
])
