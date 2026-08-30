"""Generate a bar chart from ragas EvaluationResult.

Usage (after running test_evaluation_runs):
    from ragas import evaluate
    from tests.generate_rag_plot import plot_result
    plot_result(result_0_2, out_path="rag_results.png")
"""

from pathlib import Path

def plot_result(result, out_path="tests/fixtures/rag_results.png"):
    import matplotlib.pyplot as plt
    import pandas as pd

    df = result.to_pandas() if hasattr(result, "to_pandas") else pd.DataFrame(result)
    # Pick metric columns
    metrics = [c for c in df.columns if c in {
        "faithfulness", "answer_relevancy", "context_recall",
        "context_precision", "answer_correctness"
    }]
    scores = df[metrics].mean().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    colors = ["#10b981" if s >= 0.6 else "#f59e0b" if s >= 0.5 else "#ef4444" for s in scores]
    bars = ax.barh(scores.index, scores.values, color=colors)
    ax.set_xlim(0, 1)
    ax.axvline(0.60, color="#64748b", linestyle="--", label="threshold 0.6")
    ax.set_xlabel("Score (0–1)")
    ax.set_title("Campus Saathi RAG Metrics — ragas 0.2.x")
    for bar in bars:
        w = bar.get_width()
        ax.annotate(f"{w:.2f}", xy=(w, bar.get_y() + bar.get_height()/2),
                    xytext=(3, 0), textcoords="offset points",
                    ha="left", va="center", fontsize=9)
    ax.legend(loc="lower right")
    plt.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150)
    print(f"📊 Plotted to {out_path}")
