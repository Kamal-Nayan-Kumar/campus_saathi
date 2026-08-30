"""QueryEngine (ADR-0001): the RAG chain on LangChain + Groq.

Flow: detect language + translate to English (Groq) -> similarity search in
the Knowledge Base -> answer grounded in retrieved context, replied in the
user's language. Model: openai/gpt-oss-120b via the plain langchain-openai
client pointed at Groq's OpenAI-compatible base URL (no langchain-groq).
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL = "openai/gpt-oss-120b"

TRANSLATE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a translator.\n"
            "1. Detect the language of the user's message.\n"
            "2. Translate it to English.\n"
            '3. Reply ONLY with JSON: {{"translation": "...", "detected_language": "..."}}',
        ),
        ("human", "{query}"),
    ]
)

ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful assistant for a college.\n"
            "Answer the user's question based strictly on the provided context.\n"
            "Respond in this language: {language}.\n"
            "Current date and time in Asia/Kolkata (use to resolve 'today', 'tomorrow', 'yesterday', weekday names): {current_date}.\n"
            "If the question is about 'today', use the date above to pick the correct weekday from the context (e.g., Monday-Sunday menu).\n"
            "Use INR (Indian Rupees) for all monetary values.\n"
            "If the info is missing from the context, say so politely in {language}.",
        ),
        ("human", "Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"),
    ]
)


class QueryEngine:
    def __init__(self, knowledge_base):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables")

        self.knowledge_base = knowledge_base
        self.llm = ChatOpenAI(
            model=MODEL,
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            temperature=0.1,
        )
        self.translate_chain = TRANSLATE_PROMPT | self.llm | StrOutputParser()
        self.answer_chain = ANSWER_PROMPT | self.llm | StrOutputParser()

    def process_query(self, user_query: str, history: list[dict] = None) -> tuple[str, list[str]]:
        """
        Returns (answer, sources) where sources is a list of unique filenames
        that contributed to the answer.
        """
        try:
            # Step 1: detect language and translate to English
            english_query, language = self._translate(user_query)

            # Step 2: retrieve context from the Knowledge Base with sources
            context_chunks, source_filenames = self.knowledge_base.search_with_sources(
                english_query[:1000]
            )
            if not context_chunks:
                return (
                    "I couldn't find any relevant documents to answer your question.",
                    [],
                )

            # Build conversation context from recent history (last 5 pairs)
            history_str = ""
            if history and len(history) > 0:
                # Last 5 in chronological order (oldest first in string)
                recent = history[-5:]
                pairs = []
                for h in recent:
                    role = h.get("role", "user")
                    content = h.get("content", "")
                    label = "User" if role == "user" else "Assistant"
                    pairs.append(f"{label}: {content}")
                history_str = "Past conversation:\n" + "\n".join(pairs) + "\n\n"

            # Step 3: generate a grounded answer in the user's language
            # Inject current date for 'today' resolution (Asia/Kolkata)
            current_date = datetime.now(ZoneInfo("Asia/Kolkata")).strftime(
                "%A, %Y-%m-%d %H:%M %Z"
            )
            full_context = ("\n\n".join(context_chunks))
            if history_str:
                full_context = history_str + full_context
            answer = self.answer_chain.invoke(
                {
                    "context": full_context,
                    "question": user_query,
                    "language": language,
                    "current_date": current_date,
                }
            )
            # Deduplicate sources while preserving order
            unique_sources = list(dict.fromkeys(source_filenames))
            return answer or "Sorry, something went wrong. Please try again later.", unique_sources
        except Exception as exc:
            print(f"CRITICAL ERROR in QueryEngine: {exc}")
            return (
                "Sorry, the assistant can't reach its AI service right now. "
                "Please try again later.",
                [],
            )

    def _translate(self, user_query: str) -> tuple[str, str]:
        """Returns (english_query, detected_language); falls back to the original."""
        try:
            raw = self.translate_chain.invoke({"query": user_query})
            clean = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            return data.get("translation", user_query), data.get(
                "detected_language", "English"
            )
        except Exception as exc:
            print(f"Translation failed, using original query: {exc}")
            return user_query, "English"
