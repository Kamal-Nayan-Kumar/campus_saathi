"""Run real ragas evaluation and generate artifacts.

Produces:
  - tests/fixtures/rag_real_scores.csv  (raw per-question scores)
  - tests/fixtures/rag_results.png      (bar chart)

No hardcoded scores. Requires GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY.
Run with: dotenv run -- .venv-eval/bin/python scripts/run_rag_eval.py
"""

import sys

sys.path.insert(0, ".")

from dotenv import load_dotenv

load_dotenv()

from tests.ragas_harness import RagEvalHarness
from tests.generate_rag_plot import plot_result

print("Building dataset from tests/fixtures/rag_evals.json ...")
h = RagEvalHarness()
ds = h.run("tests/fixtures/rag_evals.json")
print(f"Dataset: {len(ds)} rows, columns: {ds.column_names}")

print("\nEvaluating with ragas (this calls Groq judge, ~60s) ...")
result = h.evaluate(ds)

if hasattr(result, "to_pandas"):
    df = result.to_pandas()
    print("\n📊 REAL RAGAS SCORES")
    print("-" * 55)
    for col in df.columns:
        try:
            avg = df[col].mean()
            print(f"  {col:<22} {avg:.3f}")
        except Exception:
            pass
    out_csv = "tests/fixtures/rag_real_scores.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nSaved CSV -> {out_csv}")

    out_png = "tests/fixtures/rag_results.png"
    plot_result(result, out_path=out_png)
    print(f"Saved plot -> {out_png}")
else:
    print("Result has no to_pandas")
    print(result.scores if hasattr(result, "scores") else "N/A")
