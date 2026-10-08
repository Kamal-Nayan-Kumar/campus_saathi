"""MissLog: the replacement for runtime web search (ADR-0004).

Real file-backed behavior — dedup, counts, eviction cap, torn-line recovery.
"""

import pytest

from backend.miss_log import MAX_ENTRIES, MissLog


@pytest.fixture
def log(tmp_path):
    return MissLog(path=str(tmp_path / "misses.jsonl"))


def test_records_a_query_with_count_one(log):
    entry = log.record("what is in snacks today", "English")
    assert entry["count"] == 1
    assert entry["query"] == "what is in snacks today"
    assert entry["language"] == "English"


def test_repeat_query_bumps_count_and_stays_one_entry(log):
    log.record("what is in snacks today")
    log.record("what is in snacks today")
    entry = log.record("What is in snacks today?")

    rows = log.list_misses()
    assert len(rows) == 1
    assert rows[0]["count"] == 3
    assert entry["count"] == 3
    assert log.total_queries() == 3


def test_different_queries_are_separate_entries(log):
    log.record("what is in snacks today")
    log.record("when is the bus")
    assert len(log.list_misses()) == 2
    assert log.total_queries() == 2


def test_blank_query_is_not_recorded(log):
    assert log.record("") is None
    assert log.record("   ") is None
    assert log.record(None) is None
    assert log.list_misses() == []


def test_punctuation_only_query_is_not_recorded(log):
    assert log.record("??? !!!") is None
    assert log.list_misses() == []


def test_missing_file_reads_as_empty_not_a_crash(tmp_path):
    log = MissLog(path=str(tmp_path / "never-written.jsonl"))
    assert log.list_misses() == []
    assert log.total_queries() == 0


def test_torn_line_does_not_lose_the_other_entries(log):
    log.record("first question")
    log.record("second question")
    with open(log.path, "a", encoding="utf-8") as fh:
        fh.write('{"broken": \n')  # simulate an interrupted write

    rows = log.list_misses()
    assert {r["query"] for r in rows} == {"first question", "second question"}


def test_creates_parent_directory(tmp_path):
    log = MissLog(path=str(tmp_path / "nested" / "deep" / "misses.jsonl"))
    log.record("a question")
    assert log.list_misses()[0]["query"] == "a question"


def test_clear_reports_how_many_entries_went(log):
    log.record("first question")
    log.record("second question")
    assert log.clear() == 2
    assert log.list_misses() == []
    assert log.total_queries() == 0


def test_entries_are_capped_so_the_log_cannot_grow_without_bound(tmp_path):
    log = MissLog(path=str(tmp_path / "misses.jsonl"))
    for i in range(MAX_ENTRIES + 25):
        log.record(f"question number {i}")

    rows = log.list_misses(limit=MAX_ENTRIES + 100)
    assert len(rows) == MAX_ENTRIES


def test_limit_returns_newest_first(log):
    log.record("older question")
    log.record("newer question")
    rows = log.list_misses()
    assert rows[0]["query"] == "newer question"