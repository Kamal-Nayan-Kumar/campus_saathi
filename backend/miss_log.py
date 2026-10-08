"""MissLog — what students asked for that the Knowledge Base couldn't answer.

The student path no longer searches the web (see ADR-0004). When retrieval
fails to answer, the query is recorded here so the admin can decide what to
crawl or upload. Deduplicated by normalized query so a question asked 50
times is one entry with count=50, not 50 lines.

Storage is a JSONL file, capped at MAX_ENTRIES (oldest evicted). The process
is the single writer, and the file is read-modify-written whole, so there is
no concurrency to reason about.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

DEFAULT_PATH = os.getenv("MISS_LOG_PATH", "data/misses.jsonl")
MAX_ENTRIES = 500

_NON_WORD = re.compile(r"[^a-z0-9 ]+")


def _normalize(query: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace, for dedup keying."""
    return " ".join(_NON_WORD.sub(" ", (query or "").lower()).split())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MissLog:
    def __init__(self, path: str | None = None):
        self.path = path or DEFAULT_PATH

    def _read(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        rows = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # skip a torn line rather than lose the whole log
        return rows

    def _write(self, rows: list[dict]) -> None:
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def record(self, query: str, language: str | None = None) -> dict | None:
        """Log an unanswered query, bumping count if it's a repeat. Best-effort.

        Returns the stored entry, or None if the query is empty or the write
        failed — a miss log must never break the student's answer.
        """
        query = (query or "").strip()
        if not query:
            return None

        key = _normalize(query)
        if not key:
            return None

        try:
            rows = self._read()
            now = _now()
            for row in rows:
                if row.get("key") == key:
                    row["count"] = int(row.get("count", 1)) + 1
                    row["last_seen"] = now
                    entry = row
                    break
            else:
                entry = {
                    "key": key,
                    "query": query,
                    "language": language,
                    "count": 1,
                    "first_seen": now,
                    "last_seen": now,
                }
                rows.append(entry)

            rows.sort(key=lambda r: r.get("last_seen", ""))
            self._write(rows[-MAX_ENTRIES:])
            return entry
        except OSError as exc:
            print(f"MissLog write failed: {exc}")
            return None

    def list_misses(self, limit: int = 20) -> list[dict]:
        """Most-recently-seen unanswered queries, newest first."""
        try:
            rows = self._read()
        except OSError:
            return []
        rows.sort(key=lambda r: r.get("last_seen", ""), reverse=True)
        return rows[: max(1, limit)]

    def total_queries(self) -> int:
        """Sum of counts — total student questions that went unanswered."""
        try:
            return sum(int(r.get("count", 1)) for r in self._read())
        except OSError:
            return 0

    def clear(self) -> int:
        """Empty the log. Returns how many distinct entries were removed."""
        rows = self._read()
        self._write([])
        return len(rows)