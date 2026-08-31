"""WebSearchTool — on-demand fallback via Firecrawl search + scrape.

Used by QueryEngine when the Knowledge Base has no answer.
Does NOT upsert into Qdrant; context is ephemeral for that query only.

Flow: search(query, include_domains=[iiitdwd.ac.in]) -> scrape top 2 URLs
      in parallel -> split markdown -> return chunks + source URLs.
"""

from __future__ import annotations

import concurrent.futures
import os
import re
import time

from langchain_text_splitters import RecursiveCharacterTextSplitter

_PDF_RE = re.compile(r"https?://[^\s\)\]\"'<>]+\.pdf", re.IGNORECASE)


class WebSearchTool:
    def __init__(self, api_key: str | None = None, target_url: str | None = None):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY")
        self.target_url = target_url or os.getenv("COLLEGE_WEBSITE_URL", "https://iiitdwd.ac.in")
        # domain for include_domains filter, e.g. iiitdwd.ac.in
        self.domain = self.target_url.replace("https://", "").replace("http://", "").split("/")[0].strip("/")
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        self._client = None

    def _get_client(self):
        if not self.api_key:
            return None
        if self._client is None:
            from firecrawl import Firecrawl

            self._client = Firecrawl(api_key=self.api_key)
        return self._client

    def _optimize_query(self, query: str) -> str:
        """Generic 'know where' — compress vague queries into tight keywords.

        e.g. 'tell me about placement this year' -> 'IIIT Dharwad placement 2026'
        No hardcoded topic — works for placement, scholarship, fee, hostel, etc.
        """
        q_low = query.lower().strip()
        # generic filler that makes Firecrawl rank homepage over the right page
        filler = {"tell","me","about","please","can","you","what","is","the","for","this","that","a","an","give","show","i","want","to","know","details","information","of","on","in","my","we","us"}
        tokens = [t for t in re.split(r"[^a-z0-9]+", q_low) if t and t not in filler]
        if not tokens:
            return query.strip()

        # resolve 'this year' / 'current year' -> actual year so search ranks yearly page
        has_year_word = "this year" in q_low or "current year" in q_low or "latest" in q_low
        has_explicit_year = any(re.match(r"20\d{2}", t) for t in tokens)
        if has_year_word and not has_explicit_year:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            year = str(datetime.now(ZoneInfo("Asia/Kolkata")).year)
            # keep position near relevant token if possible — just append
            tokens.append(year)

        cleaned = " ".join(tokens[:8])
        if "iiit" not in cleaned and "dharwad" not in cleaned:
            cleaned = "IIIT Dharwad " + cleaned
        return cleaned

    def search_and_scrape(
        self, query: str, limit: int = 5, scrape_limit: int = 2
    ) -> tuple[list[str], list[str]]:
        """Search iiitdwd.ac.in and scrape top hits — optimized for speed.

        Flow: search (find the right page) then parallel scrape. This mirrors
        "first know where the answer lives, then visit that page" so we don't
        wait 3-5 sequential scrapes.

        Returns (chunks, urls). Empty if search fails or no hits.
        """
        client = self._get_client()
        if not client:
            print("WebSearchTool: FIRECRAWL_API_KEY missing, skipping")
            return [], []

        # 1. Search with domain filter (the "where" step)
        # Optimize vague queries like "tell me about placement this year" -> tight keywords
        search_query = self._optimize_query(query)
        if search_query != query:
            print(f"WebSearchTool query optimized: '{query}' -> '{search_query}'")
        t0 = time.time()
        try:
            res = client.search(search_query, limit=limit, include_domains=[self.domain])
            web_results = getattr(res, "web", None) or []
        except Exception as e:
            print(f"WebSearchTool search failed: {e}")
            return [], []

        if not web_results:
            return [], []

        # 2. Scrape top N urls in parallel (the "visit that page" step)
        urls = []
        for r in web_results[:scrape_limit]:
            url = getattr(r, "url", None) or (r.get("url") if isinstance(r, dict) else None)
            if url:
                urls.append(url)

        if not urls:
            return [], []

        def _scrape_one(url: str) -> tuple[str, str] | None:
            try:
                doc = client.scrape_url(url, formats=["markdown"], only_main_content=True)
                data = doc.model_dump() if hasattr(doc, "model_dump") else {}
                markdown = (data.get("markdown") or "").strip()
                if not markdown:
                    return None
                return (url, markdown)
            except Exception as e:
                print(f"WebSearchTool scrape {url} failed: {e}")
                return None

        # parallel — cuts 6-12s sequential to ~2-4s
        results: list[tuple[str, str]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(urls)) as ex:
            fut_to_url = {ex.submit(_scrape_one, u): u for u in urls}
            for fut in concurrent.futures.as_completed(fut_to_url):
                r = fut.result()
                if r:
                    results.append(r)

        # keep original search ranking order
        order = {u: i for i, u in enumerate(urls)}
        results.sort(key=lambda x: order.get(x[0], 99))

        chunks: list[str] = []
        scraped_urls: list[str] = []
        all_markdowns: list[str] = []
        for url, markdown in results:
            all_markdowns.append(markdown)
            split = self.splitter.split_text(markdown)
            for ch in split[:3]:  # max 3 chunks per page
                chunks.append(ch)
            scraped_urls.append(url)

        t_search_done = time.time()
        print(f"WebSearchTool search+scrape {len(scraped_urls)} pages in {t_search_done - t0:.1f}s")

        # If we scraped a link-list page (e.g. /scholarship/), also scrape PDFs linked from it
        # This fixes SC/ST not appearing in search results but linked from the landing page.
        if all_markdowns:
            combined = "\n".join(all_markdowns)
            pdf_links = _PDF_RE.findall(combined)
            # keep only iiitdwd pdfs, dedup, not already scraped
            seen = set(scraped_urls)
            candidates: list[str] = []
            for link in pdf_links:
                link = link.rstrip(".,)")
                if link in seen:
                    continue
                if "iiitdwd.ac.in" not in link:
                    continue
                if link not in candidates:
                    candidates.append(link)

            # Rank PDFs by relevance to query (so SC query gets SC pdf, not just first 2)
            q_low = query.lower()
            # keep tokens like sc, st, obc, ebc, pwd which are 2-3 chars but meaningful
            stop = {"what","is","the","for","and","are","available","student","students","scholarship","scholarships","available","about","from"}
            tokens = [t for t in re.split(r"[^a-z0-9]+", q_low) if t and t not in stop]
            def pdf_score(url: str) -> int:
                u = url.lower()
                s = 0
                for tok in tokens:
                    if tok in u:
                        s += 2 if len(tok) <= 3 else 1  # boost short category tokens like sc, st
                # bonus for exact category strings
                if "sc_" in u and "sc" in tokens: s += 3
                if "st_" in u and "st" in tokens: s += 3
                if "obc" in u and "obc" in tokens: s += 3
                if "pwd" in u and "pwd" in tokens: s += 3
                return s
            candidates.sort(key=pdf_score, reverse=True)
            # Only scrape the single best-matching PDF (extra PDFs are slow and rarely needed)
            extra_pdfs = candidates[:1]
            if extra_pdfs:
                def _scrape_pdf(pdf_url: str) -> tuple[str, str] | None:
                    try:
                        doc = client.scrape_url(pdf_url, formats=["markdown"], only_main_content=True)
                        data = doc.model_dump() if hasattr(doc, "model_dump") else {}
                        markdown = (data.get("markdown") or "").strip()
                        if not markdown:
                            return None
                        return (pdf_url, markdown)
                    except Exception as e:
                        print(f"WebSearchTool extra PDF {pdf_url} failed: {e}")
                        return None

                with concurrent.futures.ThreadPoolExecutor(max_workers=len(extra_pdfs)) as ex:
                    pdf_results = list(ex.map(_scrape_pdf, extra_pdfs))
                for r in pdf_results:
                    if not r:
                        continue
                    pdf_url, markdown = r
                    split = self.splitter.split_text(markdown)
                    for ch in split[:3]:
                        chunks.append(ch)
                    scraped_urls.append(pdf_url)
                    print(f"WebSearchTool extra PDF scraped: {pdf_url}")

        return chunks, scraped_urls
