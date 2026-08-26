"""Ingestion pipeline (ADR-0001): Firecrawl /parse -> markdown ->
LangChain RecursiveCharacterTextSplitter -> Knowledge Base upsert.
One admin upload = one ingestion run. No fallback parser.
"""

import os

from firecrawl import Firecrawl
from langchain_text_splitters import RecursiveCharacterTextSplitter


class PDFProcessor:
    def __init__(self, knowledge_base):
        api_key = os.getenv("FIRECRAWL_API_KEY")
        if not api_key:
            raise ValueError("FIRECRAWL_API_KEY not found in environment variables")

        self.firecrawl = Firecrawl(api_key=api_key)
        self.knowledge_base = knowledge_base
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=150,
        )

    def process_and_ingest(self, file_bytes: bytes, filename: str) -> int:
        """Parse, chunk and store a PDF. Returns the number of chunks ingested."""
        print(f"Processing {filename}...")

        markdown = self._parse_pdf(file_bytes, filename)
        if not markdown or not markdown.strip():
            raise ValueError(f"Failed to extract content from {filename}")

        chunks = self.splitter.split_text(markdown)
        print(f"Split document into {len(chunks)} chunks.")

        count = self.knowledge_base.upsert_chunks(filename, chunks)
        print(f"Ingested {count} chunks from {filename} into the Knowledge Base.")
        return count

    def _parse_pdf(self, file_bytes: bytes, filename: str) -> str:
        doc = self.firecrawl.parse(
            file_bytes,
            filename=filename,
            content_type="application/pdf",
            options={"formats": ["markdown"]},
        )
        return doc.markdown or ""
