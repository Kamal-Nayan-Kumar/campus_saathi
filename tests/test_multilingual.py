"""Multilingual contract — one question per language, live services.

The pipeline must: detect the language -> translate to English -> retrieve
from the KB -> answer in the language the user actually used. Hinglish is the
tricky case: it is ASCII, so a naive "ASCII == English" fast path skips
translation and retrieval misses.

Requires real keys (GROQ/OPENROUTER + QDRANT). Run with:
    .venv/bin/dotenv run -- .venv/bin/python -m pytest tests/test_multilingual.py -v -s
"""

import os

import pytest

from backend.query_engine import QueryEngine
from backend.vector_store import KnowledgeBase


def _has_live_keys() -> bool:
    return bool(
        os.getenv("GROQ_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    ) and bool(os.getenv("QDRANT_URL") and os.getenv("QDRANT_API_KEY"))


requires_live = pytest.mark.skipif(
    not _has_live_keys(),
    reason="needs GROQ/OPENROUTER + QDRANT keys to hit live services",
)


@pytest.fixture(scope="module")
def engine():
    return QueryEngine(knowledge_base=KnowledgeBase())


# (label, question, expected_in_answer, must_not_be_miss)
CASES = [
    ("English", "What is the fee for 3rd semester?", ["1,52,500", "152500"], True),
    ("Hindi", "तीसरे सेमेस्टर की फीस क्या है?", ["1,52,500", "152500"], True),
    ("Kannada", "3ನೇ ಸೆಮಿಸ್ಟರ್‌ನ ಶುಲ್ಕ ಎಷ್ಟು?", ["1,52,500", "152500"], True),
    ("Hinglish", "3rd semester ki fees kitni hai?", ["1,52,500", "152500"], True),
    ("Hinglish-casual", "Mujhe 3rd semester ka fee batao yaar", ["1,52,500", "152500"], True),
]


def _norm(text: str) -> str:
    text = text.lower()
    for ch in "*_#>|,":
        text = text.replace(ch, "" if ch == "," else " ")
    for ch in ("\u00a0", "\u2009", "\u200b", "\u2019", "\u2018"):
        text = text.replace(ch, "'" if ch in ("\u2019", "\u2018") else " ")
    return " ".join(text.split())


@requires_live
@pytest.mark.parametrize("label,question,facts,expect_hit", CASES)
def test_question_answered_in_its_own_language(engine, label, question, facts, expect_hit):
    answer, sources, extra = engine.process_query(question)
    assert answer, f"{label}: empty answer"

    if expect_hit:
        # must NOT be the not-found reply
        assert "could not find" not in answer.lower(), (
            f"{label}: wrongly reported a miss -> {answer!r}"
        )
        # the grounded figure must appear (comma/space/case-insensitive)
        norm = _norm(answer)
        assert any(_norm(f) in norm for f in facts), (
            f"{label}: expected one of {facts} in answer:\n{answer}"
        )
    print(f"\n[{label}] Q: {question}\nA: {answer[:200]}")


@requires_live
def test_answer_language_matches_question_language(engine):
    """Hindi/Kannada questions must get Hindi/Kannada answers, not English."""
    devanagari = "तीसरे सेमेस्टर की फीस क्या है?"
    kannada = "3ನೇ ಸೆಮಿಸ್ಟರ್‌ನ ಶುಲ್ಕ ಎಷ್ಟು?"

    answer, _, _ = engine.process_query(devanagari)
    # contains Devanagari script -> answered in Hindi
    assert any("ऀ" <= ch <= "ॿ" for ch in answer), (
        f"Hindi question got a non-Hindi answer: {answer[:200]}"
    )

    answer, _, _ = engine.process_query(kannada)
    assert any("ಀ" <= ch <= "೿" for ch in answer), (
        f"Kannada question got a non-Kannada answer: {answer[:200]}"
    )
    print("\n[language-match] Hindi/Kannada answers are in the right scripts")


@requires_live
def test_unanswerable_is_honest_in_any_language(engine):
    """A KB miss must be reported honestly, whatever the language.

    The engine's `missed` flag is computed from English phrases only, so a
    Hindi/Kannada refusal can slip through as missed=False while still being
    perfectly honest. So assert two things that hold in any language:
      1. the answer is a refusal, not a fabrication (no invented hours)
      2. no source is cited for a claim the corpus cannot back
    """
    import re

    for label, q in [("English", "When does the library open?"), ("Hindi", "लाइब्रेरी कब खुलती है?")]:
        answer, sources, extra = engine.process_query(q)
        assert answer
        # a fabricated answer would state opening hours (e.g. "9 AM", "09:00")
        assert not re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", answer.lower()), (
            f"{label}: miss fabricated hours -> {answer!r}"
        )
        # an honest miss never cites a source for an answer it can't give
        assert all(s == "" for s in sources), (
            f"{label}: miss cited sources {sources}"
        )
        print(f"\n[miss] Q: {q}\nA: {answer[:160]}")


@requires_live
def test_hinglish_is_not_treated_as_english(engine):
    """Hinglish is ASCII — the old fast path assumed ASCII == English."""
    q = "3rd semester ki fees kitni hai?"
    english_query, language = engine._translate(q)
    # must NOT short-circuit to "English" on the ASCII fast path
    assert language.lower() != "english", (
        f"Hinglish was classified as English: {english_query!r} / {language!r}"
    )
    print(f"\n[hinglish] detected={language!r} -> {english_query!r}")
