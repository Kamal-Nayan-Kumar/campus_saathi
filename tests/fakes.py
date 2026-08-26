"""Fakes for the three external adapters (Groq, Qdrant, Firecrawl).

Tests exercise the FastAPI HTTP interface only; these stand in for the
adapters on ``app.state``. Behavior is asserted via HTTP responses.
"""


class FakeKnowledgeBase:
    """In-memory stand-in for the Qdrant-backed KnowledgeBase."""

    def __init__(self):
        self.docs: dict[str, list[str]] = {}

    def upsert_chunks(self, filename: str, chunks: list[str]) -> int:
        self.docs[filename] = list(chunks)
        return len(chunks)

    def search(self, query_text: str, limit: int = 5) -> list[str]:
        results = []
        for chunks in self.docs.values():
            results.extend(chunks)
        return results[:limit]

    def list_documents(self) -> list[dict]:
        return [
            {"filename": name, "chunks": len(chunks)}
            for name, chunks in sorted(self.docs.items())
        ]

    def delete_document(self, filename: str) -> bool:
        return self.docs.pop(filename, None) is not None


class FakePDFProcessor:
    """Skips Firecrawl/splitter; produces deterministic chunks per upload."""

    def __init__(self, knowledge_base: FakeKnowledgeBase):
        self.knowledge_base = knowledge_base

    def process_and_ingest(self, file_bytes: bytes, filename: str) -> int:
        if not file_bytes:
            raise ValueError("empty document")
        text = file_bytes.decode("utf-8", errors="ignore")
        # deterministic chunking: ~40 chars per chunk, always > 0
        chunks = [text[i : i + 40] for i in range(0, max(len(text), 1), 40)]
        if not chunks:
            raise ValueError(f"Failed to extract content from {filename}")
        return self.knowledge_base.upsert_chunks(filename, chunks)


class FakeQueryEngine:
    def __init__(self):
        self.last_query: str | None = None

    def process_query(self, user_query: str) -> str:
        self.last_query = user_query
        return "The central library is open from 9 AM to 8 PM on weekdays."
