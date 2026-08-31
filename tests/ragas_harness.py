"""Ragas evaluation harness — runs the real QueryEngine and feeds ragas.

Architecture:
  QueryEngine (real) -> captures (retrieved_contexts, response, question)
                    -> ragas evaluates all five standard metrics.

Run with:
    pytest tests/test_rag_ragas.py -v -s

Requires GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY environment variables.
Expects at least one document ingested in Qdrant (e.g. Fee Structure.pdf).
"""

from __future__ import annotations

# Compat: langchain 1.x removed .verbose / .debug which core 0.x references
import langchain
if not hasattr(langchain, "verbose"): langchain.verbose = False
if not hasattr(langchain, "llm_cache"): langchain.llm_cache = None
if not hasattr(langchain, "debug"): langchain.debug = False

import json
import os
from pathlib import Path
from typing import Any

from backend.query_engine import QueryEngine
from backend.vector_store import KnowledgeBase


# ── Groq judge (used by ragas to score each metric) ──────────────────────────

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
JUDGE_MODEL = "openai/gpt-oss-120b"


def _make_judge_llm() -> Any:
    """Build a Groq-backed judge LLM for ragas.

    Supports both ragas 0.4 (llm_factory with client) and 0.2 (ChatOpenAI).
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set — cannot create judge LLM")
    os.environ["OPENAI_API_KEY"] = api_key

    # Try ragas 0.4 path first (Instructor LLM)
    try:
        from ragas.llms import llm_factory
        import inspect

        sig = inspect.signature(llm_factory)
        if "client" in sig.parameters:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
            return llm_factory(JUDGE_MODEL, client=client)
        else:
            # ragas 0.2 style llm_factory(base_url=...)
            return llm_factory(JUDGE_MODEL, base_url=GROQ_BASE_URL)
    except Exception:
        # Fallback to plain ChatOpenAI (ragas 0.2 will inject it)
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=JUDGE_MODEL, api_key=api_key, base_url=GROQ_BASE_URL, temperature=0.1
        )


# ── Embedding model (for answer_relevancy — cosine similarity of question↔answer) ──

def _make_embeddings() -> Any:
    """Ragas embeddings — modern factory for 0.4, HuggingFace for 0.2."""
    try:
        from ragas.embeddings.base import embedding_factory

        return embedding_factory(
            "huggingface",
            model="sentence-transformers/all-MiniLM-L6-v2",
        )
    except Exception:
        from langchain_community.embeddings import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


# ── Harness ─────────────────────────────────────────────────────────────────

class RagEvalHarness:
    """Runs the real RAG pipeline for a set of eval questions, then evaluates
    all five ragas metrics against the captured (question, contexts, answer,
    ground_truth) tuples."""

    def __init__(self):
        self.kb = KnowledgeBase()
        self.engine = QueryEngine(self.kb)
        self.judge_llm = _make_judge_llm()
        self.embeddings = _make_embeddings()
        self._results: list[dict] = []

    def _translate(self, query: str) -> tuple[str, str]:
        """Re-use the engine's translate chain to get English query + language."""
        raw = self.engine.translate_chain.invoke({"query": query})
        clean = raw.replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(clean)
            return data.get("translation", query), data.get("detected_language", "English")
        except Exception:
            return query, "English"

    def run(self, eval_file: str | Path | list[dict]) -> Any:
        """
        Execute the RAG pipeline for every entry in the eval file.

        Returns a ``datasets.Dataset`` with columns:
            user_input       — original question
            retrieved_contexts — list[str] chunks from Qdrant
            response         — answer from Groq
            ground_truth     — expected answer
        """
        if isinstance(eval_file, (str, Path)):
            raw = Path(eval_file).read_text()
            eval_rows = json.loads(raw)
        else:
            eval_rows = eval_file

        records = []
        for row in eval_rows:
            question = row["question"]
            ground_truth = row["ground_truth"]

            english_query, _ = self._translate(question)
            chunks, _ = self.kb.search_with_sources(english_query[:1000], limit=5)
            _res = self.engine.process_query(question, history=None)
            # handle 2- or 3-tuple (new web_search info)
            if isinstance(_res, tuple) and len(_res) == 3:
                answer, _, _ = _res
            else:
                answer, _ = _res

            records.append({
                "user_input": question,
                "retrieved_contexts": chunks,
                "response": answer,
                "ground_truth": ground_truth,
            })

        self._results = records
        from datasets import Dataset
        return Dataset.from_list(records)

    def evaluate(self, dataset: Any) -> Any:
        """Run ragas evaluate() with five standard metrics.

        Handles both ragas 0.4 (collections) and 0.2 (flat) APIs.
        """
        # Try modern 0.4 collections API
        try:
            from ragas import evaluate
            from ragas.metrics.collections import (
                faithfulness, answer_relevancy, context_recall,
                context_precision, answer_correctness,
            )

            metrics = [
                faithfulness.Faithfulness(llm=self.judge_llm),
                answer_relevancy.AnswerRelevancy(llm=self.judge_llm, embeddings=self.embeddings),
                context_recall.ContextRecall(llm=self.judge_llm),
                context_precision.ContextPrecision(llm=self.judge_llm),
                answer_correctness.AnswerCorrectness(llm=self.judge_llm, embeddings=self.embeddings),
            ]
            print(f"\n🧪 Running ragas 0.4 evaluate() on {len(dataset)} questions ...")
            return evaluate(
                dataset,
                metrics=metrics,
                raise_exceptions=False,
                allow_nest_asyncio=True,
            )
        except Exception:
            pass

        # Fallback 0.2 API
        from ragas import evaluate as eval02
        from ragas.metrics import (
            faithfulness, answer_relevancy, context_recall,
            context_precision, answer_correctness,
        )

        for m in [faithfulness, answer_relevancy, context_recall, context_precision, answer_correctness]:
            m.llm = self.judge_llm
        answer_relevancy.embeddings = self.embeddings
        answer_correctness.embeddings = self.embeddings

        print(f"\n🧪 Running ragas 0.2 evaluate() on {len(dataset)} questions ...")
        return eval02(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_recall, context_precision, answer_correctness],
            llm=self.judge_llm,
            embeddings=self.embeddings,
            raise_exceptions=False,
        )


# ── Threshold-based assertions ────────────────────────────────────────────────

THRESHOLDS = {
    "faithfulness":       0.60,   # answer must be grounded in retrieved context
    "answer_relevancy":   0.65,   # answer must actually answer the question
    "context_recall":     0.55,   # retrieved chunks must contain ground truth
    "context_precision":  0.60,   # retrieved chunks must be relevant to question
    "answer_correctness": 0.50,   # answer must match ground truth overall
}


def _score_to_float(raw: Any) -> float:
    """Coerce a ragas score value to float, handling NaN/None."""
    try:
        if raw is None:
            return 0.0
        import math
        val = float(raw)
        if math.isnan(val):
            return 0.0
        return val
    except (TypeError, ValueError):
        return 0.0


def assert_metrics(result: Any) -> None:
    """Fail fast with a clear report if any metric is below threshold.

    Ragas returns an EvaluationResult — we extract scores via .to_pandas().
    """
    print("\n📊 RAG Evaluation Results")
    print("   " + "-" * 56)

    scores: dict[str, list[float]] = {}
    if hasattr(result, "to_pandas"):
        df = result.to_pandas()
        for col in df.columns:
            if col in THRESHOLDS:
                scores[col] = [_score_to_float(v) for v in df[col].tolist()]
    elif hasattr(result, "scores"):
        for k, v in result.scores.items():
            if k in THRESHOLDS:
                scores[k] = [_score_to_float(x) for x in v] if isinstance(v, list) else [_score_to_float(v)]

    all_passed = True
    for metric, threshold in THRESHOLDS.items():
        vals = scores.get(metric, [])
        if not vals:
            print(f"   ⚠  {metric:<22} — no score returned")
            continue
        score = sum(vals) / len(vals)
        status = "✅ PASS" if score >= threshold else "❌ FAIL"
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"   {status}  {metric:<22} {score:.3f}  [{bar}]  (threshold={threshold})")
        if score < threshold:
            all_passed = False

    print("   " + "-" * 56)
    if not all_passed:
        failed = [
            m for m, t in THRESHOLDS.items()
            if scores.get(m) and (sum(scores[m]) / len(scores[m])) < t
        ]
        raise AssertionError(
            f"RAG evaluation FAILED — metrics below threshold: {failed}\n"
            "Fix the pipeline and re-run: pytest tests/test_rag_ragas.py -v -s"
        )
    print("   ✅ All metrics above threshold.\n")
