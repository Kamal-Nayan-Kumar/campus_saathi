.PHONY: rag-eval rag-plot

rag-eval:
	@echo "Running RAG evaluation (needs GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY)"
	dotenv run -- .venv/bin/python3 -m pytest tests/test_rag_ragas.py -v -s -m slow || true

rag-plot:
	@echo "Generating RAG metrics plot"
	PYTHONPATH=. .venv/bin/python3 -c "from tests.generate_rag_plot import plot_result; import pandas as pd; df=pd.read_csv('tests/fixtures/rag_real_scores.csv'); plot_result(type('R',(),{'to_pandas':lambda s:df})(),'tests/fixtures/rag_results.png'); print('Plot updated.')"
