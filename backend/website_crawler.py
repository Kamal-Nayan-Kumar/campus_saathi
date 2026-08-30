"""Website crawl via Firecrawl -> Knowledge Base ingest.

Uses Firecrawl `map` to discover URLs under COLLEGE_WEBSITE_URL
then `batch_scrape` (or fallback scrape loop) to get markdown,
splits and upserts with filename prefix `website:iiitdwd.ac.in:`.

Refresh deletes existing website:* docs before re-ingest.
"""

import os
import time
from datetime import datetime, timezone

from firecrawl import Firecrawl
from langchain_text_splitters import RecursiveCharacterTextSplitter


DEFAULT_URL = os.getenv("COLLEGE_WEBSITE_URL", "https://iiitdwd.ac.in")
PREFIX = "website:iiitdwd.ac.in:"


class WebsiteCrawler:
    def __init__(self, knowledge_base):
        api_key = os.getenv("FIRECRAWL_API_KEY")
        if not api_key:
            raise ValueError("FIRECRAWL_API_KEY not found in environment variables")
        self.firecrawl = Firecrawl(api_key=api_key)
        self.knowledge_base = knowledge_base
        self.target_url = os.getenv("COLLEGE_WEBSITE_URL", DEFAULT_URL)
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        self.last_result: dict | None = None

    # -- helpers --

    def _delete_existing(self) -> int:
        docs = self.knowledge_base.list_documents()
        to_delete = [d["filename"] for d in docs if d["filename"].startswith("website:")]
        for fname in to_delete:
            try:
                self.knowledge_base.delete_document(fname)
            except Exception:
                pass
        return len(to_delete)

    def _discover_urls(self, limit: int) -> list[str]:
        urls: list[str] = []
        try:
            mapped = self.firecrawl.map(self.target_url, limit=limit)
            # Firecrawl map returns object with .links or dict
            raw_links = None
            if isinstance(mapped, dict):
                raw_links = mapped.get("links") or mapped.get("data") or []
            else:
                raw_links = getattr(mapped, "links", None)
                if raw_links is None:
                    raw_links = getattr(mapped, "data", None)
                if raw_links is None and hasattr(mapped, "__dict__"):
                    raw_links = []
            for item in raw_links or []:
                if isinstance(item, dict):
                    u = item.get("url") or item.get("link")
                else:
                    u = getattr(item, "url", None) or getattr(item, "link", None)
                    if not u and isinstance(item, str):
                        u = item
                if u and isinstance(u, str) and u.startswith("http"):
                    urls.append(u)
        except Exception as e:
            print(f"  map failed: {e}")

        if not urls:
            urls = [self.target_url]
        else:
            if self.target_url not in urls:
                urls.insert(0, self.target_url)
            urls = urls[:limit]
        return urls

    def _scrape_batch(self, urls: list[str]):
        # Try batch_scrape first (fast, single call)
        try:
            batch = self.firecrawl.batch_scrape(urls, formats=["markdown"], only_main_content=True)
            data = getattr(batch, "data", None)
            if data is None:
                if isinstance(batch, dict):
                    data = batch.get("data") or batch.get("results") or []
                elif isinstance(batch, list):
                    data = batch
                else:
                    data = []
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"  batch_scrape failed ({e}), fallback to per-url scrape")
            data = []
            for u in urls:
                try:
                    doc = self.firecrawl.scrape(u, formats=["markdown"], only_main_content=True)
                    data.append(doc)
                except Exception as se:
                    print(f"    scrape {u} failed: {se}")
            return data

    # -- public --

    def crawl(self, limit: int = 20, delete_old: bool = True) -> dict:
        if limit < 1:
            limit = 1
        if limit > 50:
            limit = 50

        deleted = 0
        if delete_old:
            deleted = self._delete_existing()
            if deleted:
                print(f"Deleted {deleted} old website docs")

        print(f"Crawling {self.target_url} (limit={limit}) ...")
        urls = self._discover_urls(limit)
        print(f"Discovered {len(urls)} URLs")

        data = self._scrape_batch(urls)
        print(f"Scraped {len(data)} pages")

        pages = 0
        total_chunks = 0
        ingested_urls: list[str] = []

        for doc in data:
            if isinstance(doc, dict):
                markdown = doc.get("markdown") or doc.get("content") or doc.get("markdownContent") or ""
                meta = doc.get("metadata") or {}
                url = meta.get("sourceURL") or meta.get("url") or doc.get("url") or ""
            else:
                markdown = getattr(doc, "markdown", None) or getattr(doc, "content", "") or ""
                # markdown may be under .markdown
                if not markdown and hasattr(doc, "data"):
                    markdown = getattr(doc, "markdown", "")
                meta = getattr(doc, "metadata", None) or {}
                if isinstance(meta, dict):
                    url = meta.get("sourceURL") or meta.get("url") or ""
                else:
                    url = getattr(meta, "sourceURL", "") or getattr(meta, "url", "")
                if not url:
                    url = getattr(doc, "url", "") or getattr(doc, "sourceURL", "") or ""

            markdown = (markdown or "").strip()
            if not markdown:
                continue

            safe_url = (url or f"page_{pages}").strip()
            filename = f"{PREFIX}{safe_url}"
            if len(filename) > 200:
                filename = filename[:200]

            chunks = self.splitter.split_text(markdown)
            if not chunks:
                continue
            count = self.knowledge_base.upsert_chunks(filename, chunks)
            total_chunks += count
            pages += 1
            ingested_urls.append(safe_url or filename)

        result = {
            "target": self.target_url,
            "pages": pages,
            "chunks": total_chunks,
            "urls": ingested_urls,
            "deleted": deleted,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.last_result = result
        print(f"Crawl done: {pages} pages, {total_chunks} chunks")
        return result

    def get_status(self) -> dict:
        docs = self.knowledge_base.list_documents()
        website_docs = [d for d in docs if d["filename"].startswith("website:")]
        total_chunks = sum(d["chunks"] for d in website_docs)
        return {
            "target": self.target_url,
            "total_pages": len(website_docs),
            "total_chunks": total_chunks,
            "documents": website_docs,
            "last_crawl": self.last_result,
        }
