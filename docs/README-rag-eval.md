
## RAG Evaluation (interview / quality gate)

We use `ragas` (v0.2.15, pinned) with 5 standard RAG metrics on the real `QueryEngine` + Qdrant pipeline.

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
# 1) Load env (GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY)
dotenv run -- .venv/bin/python3 -m pytest tests/test_rag_ragas.py -v -s

# 2) Full gate (slow — calls Groq judge ~30 times for 5 questions)
dotenv run -- .venv/bin/python3 -m pytest tests/test_rag_ragas.py::TestRagEvaluation::test_evaluation_passes_thresholds -v -s -m slow
```

### What's tested

- `tests/fixtures/rag_evals.json` — 5 questions from your real PDFs (Fee Structure, Bus Schedule, Mess Menu, Academic Calendar).
- `tests/ragas_harness_simple.py` — connects `QueryEngine.process_query()` to `ragas.evaluate()`.
- `tests/test_rag_ragas.py` — asserts dataset built, metrics computed, scores printed, thresholds passed.

### Notes

- Ragas needs an LLM judge; we use Groq (`openai/gpt-oss-120b`) via `ChatOpenAI` (0.2.x) / `llm_factory` (0.4.x).
- Qdrant collection `campus_saathi` must have ingested docs (run admin upload / `scripts/live_check.py` first).
- For graphical output, import `tests.generate_rag_plot.plot_result` after evaluating.
