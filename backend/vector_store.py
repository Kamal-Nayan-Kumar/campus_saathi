"""Knowledge Base: Qdrant collection with server-side embeddings (ADR-0001).

One point per document chunk. Payload contract:
    {"filename": str, "chunk_index": int, "content": str}
`filename` + `chunk_index` power list/delete; `content` feeds generation.
Embeddings are computed by Qdrant Cloud Inference
(sentence-transformers/all-MiniLM-L6-v2) -- no local embedding model.
"""

import os
import uuid

from qdrant_client import QdrantClient
from qdrant_client import models

COLLECTION_NAME = "campus_saathi"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2 dimension


class KnowledgeBase:
    """Thin adapter over Qdrant Cloud. Swap providers by editing this file only."""

    def __init__(self):
        url = os.getenv("QDRANT_URL")
        api_key = os.getenv("QDRANT_API_KEY")
        if not url or not api_key:
            raise ValueError("QDRANT_URL and QDRANT_API_KEY must be set")

        # cloud_inference=True -> embeddings run on Qdrant Cloud, not locally
        self.client = QdrantClient(url=url, api_key=api_key, cloud_inference=True)
        self._ensure_collection()

    def _ensure_collection(self):
        if not self.client.collection_exists(COLLECTION_NAME):
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )
        # Required for payload-filtered deletes on filename
        if "filename" not in (self.client.get_collection(COLLECTION_NAME).payload_schema or {}):
            self.client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="filename",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    def upsert_chunks(self, filename: str, chunks: list[str]) -> int:
        """Ingest one document's chunks; embeddings computed server-side."""
        points = [
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=models.Document(text=chunk, model=EMBED_MODEL),
                payload={"filename": filename, "chunk_index": i, "content": chunk},
            )
            for i, chunk in enumerate(chunks)
        ]
        if points:
            self.client.upsert(collection_name=COLLECTION_NAME, points=points)
        return len(points)

    def search(self, query_text: str, limit: int = 5) -> list[str]:
        """Return the content of the top-k chunks most similar to the query."""
        result = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=models.Document(text=query_text, model=EMBED_MODEL),
            limit=limit,
            with_payload=True,
        )
        return [hit.payload.get("content", "") for hit in result.points]

    def search_with_sources(self, query_text: str, limit: int = 5) -> tuple[list[str], list[str]]:
        """Return (content_chunks, filenames) from the top-k most similar chunks."""
        result = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=models.Document(text=query_text, model=EMBED_MODEL),
            limit=limit,
            with_payload=True,
        )
        chunks = []
        sources = []
        for hit in result.points:
            payload = hit.payload or {}
            chunks.append(payload.get("content", ""))
            sources.append(payload.get("filename", "unknown"))
        return chunks, sources

    def list_documents(self) -> list[dict]:
        """Aggregate all points by filename -> [{filename, chunks}]."""
        counts: dict[str, int] = {}
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=COLLECTION_NAME,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                name = point.payload.get("filename", "unknown")
                counts[name] = counts.get(name, 0) + 1
            if offset is None:
                break
        return [{"filename": name, "chunks": n} for name, n in sorted(counts.items())]

    def delete_document(self, filename: str) -> bool:
        """Remove every chunk of a document via payload filter. True if any existed."""
        filename_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="filename",
                    match=models.MatchValue(value=filename),
                )
            ]
        )
        count = self.client.count(
            collection_name=COLLECTION_NAME,
            count_filter=filename_filter,
            exact=True,
        ).count
        if count == 0:
            return False
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.FilterSelector(filter=filename_filter),
        )
        return True
