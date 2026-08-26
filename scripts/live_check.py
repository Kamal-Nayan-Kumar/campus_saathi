"""Manual live-check against real cloud services (NOT part of the test suite).

Run once after wiring real keys:
    .venv/bin/python scripts/live_check.py path/to/real.pdf

Verifies end-to-end: Firecrawl parse -> chunk -> Qdrant Cloud Inference
upsert -> Groq-grounded answer -> delete. Never prints secrets.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.pdf_processor import PDFProcessor  # noqa: E402
from backend.query_engine import QueryEngine  # noqa: E402
from backend.vector_store import KnowledgeBase  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/live_check.py <path-to-pdf>")
        sys.exit(1)
    pdf_path = sys.argv[1]
    filename = os.path.basename(pdf_path)

    missing = [
        key
        for key in ("GROQ_API_KEY", "QDRANT_URL", "QDRANT_API_KEY", "FIRECRAWL_API_KEY")
        if not os.getenv(key)
    ]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    print("1/4 Ingesting", filename)
    kb = KnowledgeBase()
    processor = PDFProcessor(knowledge_base=kb)
    with open(pdf_path, "rb") as f:
        chunks = processor.process_and_ingest(f.read(), filename)
    print(f"   -> ingested {chunks} chunks")

    docs = kb.list_documents()
    assert any(d["filename"] == filename for d in docs), "document missing from listing"
    print("2/4 Listing OK:", [d["filename"] for d in docs])

    print("3/4 Asking a question")
    engine = QueryEngine(knowledge_base=kb)
    answer = engine.process_query(
        "Summarize in one sentence what this document is about."
    )
    print("   -> answer:", answer[:300])

    print("4/4 Cleaning up")
    assert kb.delete_document(filename), "delete failed"
    print("\nLive check PASSED ✅")


if __name__ == "__main__":
    main()
