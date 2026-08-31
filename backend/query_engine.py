"""QueryEngine (ADR-0001): the RAG chain on LangChain + OpenRouter/Groq.

Flow: detect language + translate to English -> similarity search in
the Knowledge Base -> if missing, fallback to WebSearchTool (Firecrawl search
on iiitdwd.ac.in) -> answer grounded in retrieved context, replied in the
user's language. Model: openrouter/free (or groq/compound-mini) via the
plain langchain-openai client pointed at OpenRouter/Groq OpenAI-compatible base URL.
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# --- LLM provider: OpenRouter (free) if OPENROUTER_API_KEY set, else Groq ---
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Use env LLM_MODEL if set, else auto: openrouter/free for OpenRouter, groq/compound-mini for Groq
DEFAULT_GROQ_MODEL = "groq/compound-mini"
DEFAULT_OPENROUTER_MODEL = "openrouter/free"

# phrases that indicate the LLM found no answer in the provided context
_MISSING_PHRASES = [
    "does not include",
    "doesn't include",
    "does not contain",
    "doesn't contain",
    "not include",
    "not contain",
    "not provided",
    "are not provided",
    "is not provided",
    "missing from the context",
    "not in the provided context",
    "not in the context",
    "no information",
    "no specific information",
    "no specific",
    "no relevant",
    "couldn't find",
    "could not find",
    "not available",
    "not found",
    "don't have",
    "do not have",
    "is not available",
    "provided information",
    "information you shared",
    "sorry, but",
    "only mentions",
    "general note",
]

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
    def __init__(self, knowledge_base, web_search_tool=None):
        # Prefer OpenRouter if key present, else Groq — keeps backward compat
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        groq_key = os.getenv("GROQ_API_KEY")
        if openrouter_key:
            api_key = openrouter_key
            base_url = os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL)
            model = os.getenv("LLM_MODEL", DEFAULT_OPENROUTER_MODEL)
            # OpenRouter benefits from extra headers (optional but recommended)
            default_headers = {
                "HTTP-Referer": os.getenv("OPENROUTER_REFERRER", "https://campus-saathi.local"),
                "X-Title": os.getenv("OPENROUTER_TITLE", "Campus Saathi"),
            }
        elif groq_key:
            api_key = groq_key
            base_url = os.getenv("GROQ_BASE_URL", GROQ_BASE_URL)
            model = os.getenv("LLM_MODEL", DEFAULT_GROQ_MODEL)
            default_headers = None
        else:
            raise ValueError("OPENROUTER_API_KEY or GROQ_API_KEY must be set in environment variables")

        self.knowledge_base = knowledge_base
        self.web_search_tool = web_search_tool  # injected for tests; lazy otherwise
        self.last_web_search: dict | None = None
        self.llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.1,
            default_headers=default_headers,
        )
        # keep model/base for debugging
        self.llm_model = model
        self.llm_base_url = base_url
        self.translate_chain = TRANSLATE_PROMPT | self.llm | StrOutputParser()
        self.answer_chain = ANSWER_PROMPT | self.llm | StrOutputParser()

    def _is_missing_answer(self, answer: str) -> bool:
        low = (answer or "").lower().replace("’", "'").replace("‘", "'").replace("`", "'")
        if any(phrase in low for phrase in _MISSING_PHRASES):
            if low.count("provided information") and not any(
                neg in low for neg in ["does not", "doesn't", "doesn", "not include", "not contain", "missing", "sorry", "not available", "not found", "couldn"]
            ):
                return False
            return True
        return False

    def _get_web_search_tool(self):
        if self.web_search_tool is not None:
            return self.web_search_tool
        try:
            from backend.web_search import WebSearchTool

            self.web_search_tool = WebSearchTool()
            return self.web_search_tool
        except Exception as e:
            print(f"WebSearchTool init failed: {e}")
            return None

    def process_query(self, user_query: str, history: list[dict] = None) -> tuple[str, list[str], dict]:
        """
        Returns (answer, sources, web_search) where web_search is
        {"used": bool, "query": str, "urls": list[str]}.
        Backward compat: callers unpacking 2 values still work via len check.
        """
        try:
            # Step 1: detect language and translate to English
            english_query, language = self._translate(user_query)

            # Step 2: retrieve context from the Knowledge Base with sources
            context_chunks, source_filenames = self.knowledge_base.search_with_sources(
                english_query[:1000]
            )

            # Build conversation context from recent history (last 5 pairs)
            history_str = ""
            if history and len(history) > 0:
                recent = history[-5:]
                pairs = []
                for h in recent:
                    role = h.get("role", "user")
                    content = h.get("content", "")
                    label = "User" if role == "user" else "Assistant"
                    pairs.append(f"{label}: {content}")
                history_str = "Past conversation:\n" + "\n".join(pairs) + "\n\n"

            current_date = datetime.now(ZoneInfo("Asia/Kolkata")).strftime(
                "%A, %Y-%m-%d %H:%M %Z"
            )

            def _generate(context_list: list[str]) -> str:
                full_context = "\n\n".join(context_list)
                if history_str:
                    full_context = history_str + full_context
                return self.answer_chain.invoke(
                    {
                        "context": full_context,
                        "question": user_query,
                        "language": language,
                        "current_date": current_date,
                    }
                )

            # Step 3: try Knowledge Base first
            web_search_info: dict = {"used": False, "query": english_query, "urls": []}
            self.last_web_search = web_search_info

            if context_chunks:
                kb_answer = _generate(context_chunks)
                if not self._is_missing_answer(kb_answer):
                    unique_sources = list(dict.fromkeys(source_filenames))
                    self.last_web_search = {"used": False, "query": english_query, "urls": []}
                    return (
                        kb_answer or "Sorry, something went wrong. Please try again later.",
                        unique_sources,
                        self.last_web_search,
                    )
                print(f"KB miss detected for '{english_query}', falling back to web search")
            else:
                print(f"No KB chunks for '{english_query}', trying web search")

            # Step 4: fallback to WebSearchTool (Firecrawl on iiitdwd.ac.in)
            web_tool = self._get_web_search_tool()
            if web_tool is None:
                self.last_web_search = {"used": False, "query": english_query, "urls": []}
                return (
                    "I couldn't find this information in the uploaded documents and also not on the IIIT Dharwad website (iiitdwd.ac.in). Please try rephrasing or contact the admin.",
                    [],
                    self.last_web_search,
                )

            web_search_info["used"] = True
            self.last_web_search = web_search_info
            try:
                web_chunks, web_urls = web_tool.search_and_scrape(english_query)
            except Exception as e:
                print(f"Web search failed: {e}")
                web_chunks, web_urls = [], []

            web_search_info["urls"] = web_urls
            self.last_web_search = web_search_info

            if not web_chunks:
                msg = (
                    "I couldn't find this information in the uploaded documents and "
                    "also not on the IIIT Dharwad website (iiitdwd.ac.in). "
                    "Please try rephrasing your question or contact the administration at info@iiitdwd.ac.in."
                )
                if language.lower() not in ("english", "en"):
                    try:
                        msg = self.answer_chain.invoke(
                            {
                                "context": "Translate the following message to " + language + ": " + msg,
                                "question": "Translate to " + language,
                                "language": language,
                                "current_date": current_date,
                            }
                        )
                    except Exception:
                        pass
                return msg, [], web_search_info

            web_answer = _generate(web_chunks)
            if self._is_missing_answer(web_answer):
                msg = (
                    "I checked the uploaded documents and searched the IIIT Dharwad website "
                    f"(iiitdwd.ac.in) for '{english_query}' but couldn't find relevant information. "
                    "Please try rephrasing or contact the administration."
                )
                if language.lower() not in ("english", "en"):
                    try:
                        msg = self.answer_chain.invoke(
                            {
                                "context": "Translate to " + language + ": " + msg,
                                "question": "Translate",
                                "language": language,
                                "current_date": current_date,
                            }
                        )
                    except Exception:
                        pass
                return msg, web_urls, web_search_info

            return web_answer or "Sorry, something went wrong. Please try again later.", web_urls, web_search_info

        except Exception as exc:
            print(f"CRITICAL ERROR in QueryEngine: {exc}")
            self.last_web_search = {"used": False, "query": user_query, "urls": []}
            return (
                "Sorry, the assistant can't reach its AI service right now. "
                "Please try again later.",
                [],
                self.last_web_search,
            )

    def _translate(self, user_query: str) -> tuple[str, str]:
        """Returns (english_query, detected_language); falls back to the original."""
        # Fast path: skip LLM for plain ascii English (saves ~1.5s, fixes "time bahut lag rha").
        # Generic — no hardcoded topic list. If text is ascii, assume English.
        try:
            stripped = user_query.strip()
            if stripped and re.match(r"^[\x00-\x7F]+$", stripped) and len(stripped) <= 300:
                # ascii-only queries are English (Hindi/other scripts would be unicode)
                return user_query, "English"
        except Exception:
            pass
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
