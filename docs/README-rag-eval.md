
## RAG Evaluation (interview / quality gate)

We use `ragas` (v0.4.3) with 5 standard RAG metrics on the real `QueryEngine` + Qdrant pipeline. No hardcoded scores.

### Metrics (0 = bad, 1 = perfect)

| Metric | What it measures | Threshold |
|---|---|---|
| `faithfulness` | Answer only uses retrieved chunks (no hallucination) | 0.60 |
| `answer_relevancy` | Answer actually answers the question | 0.65 |
| `context_recall` | Ground-truth info is inside retrieved chunks | 0.55 |
| `context_precision` | Retrieved chunks are relevant, not noise | 0.60 |
| `answer_correctness` | Answer matches expected ground truth | 0.50 |

### How to run

```bash
# 1) Load env (GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY) — use the eval venv (Python 3.12 + ragas 0.4.3)
dotenv run -- .venv-eval/bin/python -m pytest tests/test_rag_ragas.py -v -s

# 2) Full gate (slow — calls Groq judge ~30 times for 5 questions)
dotenv run -- .venv-eval/bin/python -m pytest tests/test_rag_ragas.py::TestRagEvaluation::test_evaluation_passes_thresholds -v -s -m slow

# 3) Generate plot + CSV (real scores only)
dotenv run -- .venv-eval/bin/python scripts/run_rag_eval.py
```

### What's tested

- `tests/fixtures/rag_evals.json` — 5 questions grounded in your real PDFs (Fee Structure, Bus Schedule, Mess Menu, Academic Calendar) with ground truths verified against Qdrant chunks.
- `tests/ragas_harness.py` — connects `QueryEngine.process_query()` to `ragas.evaluate()` using `embedding_factory("huggingface", ...)` for modern ragas.
- `tests/test_rag_ragas.py` — asserts dataset built, metrics computed, scores printed, thresholds passed.

### Notes

- Ragas needs an LLM judge; we use Groq (`openai/gpt-oss-120b`) via `llm_factory`.
- Qdrant collection `campus_saathi` must have ingested docs (run admin upload / `scripts/live_check.py` first).
- `tests/fixtures/rag_results.png` and `rag_real_scores.csv` are *generated* artifacts — never hardcode them. Run `scripts/run_rag_eval.py` to recreate.
