"""
RAG Evaluation — ragas metrics on the real pipeline.

Usage:
    pytest tests/test_rag_ragas.py -v -s

Requires: GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY set in .env
         + at least one document ingested in Qdrant.
"""

import os

import pytest

from tests.ragas_harness import RagEvalHarness

THRESHOLDS = {
    "faithfulness": 0.60,
    "answer_relevancy": 0.65,
    "context_recall": 0.55,
    "context_precision": 0.60,
    "answer_correctness": 0.50,
}


def _score(raw) -> float:
    try:
        if raw is None:
            return 0.0
        import math

        v = float(raw)
        return 0.0 if math.isnan(v) else v
    except (TypeError, ValueError):
        return 0.0


def print_result(result):
    """Print a pretty bar-chart of scores vs thresholds."""
    print("\n📊  RAG Evaluation Results")
    print("   " + "-" * 58)
    scores = {}
    if hasattr(result, "to_pandas"):
        df = result.to_pandas()
        for col in df.columns:
            if col in THRESHOLDS:
                scores[col] = [_score(v) for v in df[col].tolist()]
    all_passed = True
    for metric, threshold in THRESHOLDS.items():
        vals = scores.get(metric, [])
        if not vals:
            print(f"   ⚠  {metric:<22} — no score")
            continue
        avg = sum(vals) / len(vals)
        ok = "✅" if avg >= threshold else "❌"
        bar = "█" * int(avg * 20) + "░" * (20 - int(avg * 20))
        print(f"   {ok}  {metric:<22} {avg:.3f}  [{bar}]  min={threshold}")
        if avg < threshold:
            all_passed = False
    print("   " + "-" * 58)
    print(f"   {'✅ All above threshold' if all_passed else '❌ Some below threshold'}\n")
    return all_passed


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="class")
def harness():
    return RagEvalHarness()


@pytest.fixture(scope="class")
def dataset(harness):
    return harness.run("tests/fixtures/rag_evals.json")


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not os.getenv("GROQ_API_KEY"), reason="GROQ_API_KEY missing")
@pytest.mark.skipif(
    not os.getenv("QDRANT_URL") or not os.getenv("QDRANT_API_KEY"),
    reason="Qdrant credentials missing",
)
class TestRagEvaluation:
    def test_dataset_built(self, harness):
        ds = harness.run("tests/fixtures/rag_evals.json")
        assert len(ds) == 5
        assert all(
            c in ds.column_names
            for c in ["user_input", "retrieved_contexts", "response", "ground_truth"]
        )
        non_empty = [r for r in ds["retrieved_contexts"] if r]
        assert len(non_empty) > 0, "Qdrant returned no chunks — ingest docs first"

    def test_evaluation_runs(self, harness, dataset):
        result = harness.evaluate(dataset)
        assert result is not None
        assert hasattr(result, "scores") or hasattr(result, "to_pandas")

    def test_scores_printed(self, harness, dataset):
        result = harness.evaluate(dataset)
        passed = print_result(result)
        # Don't assert pass here — let the threshold gate test handle that
        assert result is not None

    @pytest.mark.slow
    def test_evaluation_passes_thresholds(self, harness, dataset):
        result = harness.evaluate(dataset)
        passed = print_result(result)
        assert passed, "RAG metrics below threshold — fix pipeline and re-run"
