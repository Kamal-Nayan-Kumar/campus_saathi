"""Fakes for the adapters (Groq, Qdrant, Firecrawl, Website).

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

    def process_query(self, user_query: str, history=None) -> tuple[str, list]:
        self.last_query = user_query
        return "The central library is open from 9 AM to 8 PM on weekdays.", []

    def __call__(self, *a, **kw):
        return self.process_query(*a, **kw)


class BrokenQueryEngine:
    """Simulates the AI adapter failing at request time."""

    def process_query(self, user_query: str, history=None):
        raise RuntimeError("connection to AI service failed")


class FakeWebsiteCrawler:
    """Fake Firecrawl website crawler — ingests dummy chunks."""

    def __init__(self, knowledge_base: FakeKnowledgeBase):
        self.knowledge_base = knowledge_base
        self.target_url = "https://iiitdwd.ac.in"
        self.last_result = None

    def _delete_existing(self) -> int:
        docs = self.knowledge_base.list_documents()
        to_delete = [d["filename"] for d in docs if d["filename"].startswith("website:")]
        for f in to_delete:
            self.knowledge_base.delete_document(f)
        return len(to_delete)

    def crawl(self, limit: int = 20, delete_old: bool = True) -> dict:
        if delete_old:
            self._delete_existing()
        # simulate 2 pages of website content
        for i, url in enumerate([self.target_url, self.target_url + "/about"][: min(limit, 2)]):
            self.knowledge_base.upsert_chunks(f"website:iiitdwd.ac.in:{url}", [f"website content page {i}"])
        import datetime
        self.last_result = {
            "target": self.target_url,
            "pages": min(limit, 2),
            "chunks": min(limit, 2),
            "urls": [self.target_url],
            "deleted": 0,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        return self.last_result

    def get_status(self) -> dict:
        docs = self.knowledge_base.list_documents()
        website_docs = [d for d in docs if d["filename"].startswith("website:")]
        return {
            "target": self.target_url,
            "total_pages": len(website_docs),
            "total_chunks": sum(d["chunks"] for d in website_docs),
            "documents": website_docs,
            "last_crawl": self.last_result,
        }
