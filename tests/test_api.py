"""Tests for the HTTP seam: chat, upload, list, delete, portals.

External services (Groq, Qdrant, Firecrawl) are replaced by fakes injected
into app.state; assertions target HTTP responses only.
"""

from tests.fakes import BrokenQueryEngine


def test_chat_returns_answer(client):
    res = client.post("/api/chat", json={"message": "When does the library open?"})
    assert res.status_code == 200
    body = res.json()
    assert "answer" in body
    assert isinstance(body["answer"], str)
    assert len(body["answer"]) > 0


def test_chat_requires_message(client):
    res = client.post("/api/chat", json={})
    assert res.status_code == 422


def test_chat_rejects_whitespace_only_message(app, client):
    app.state.query_engine = BrokenQueryEngine()  # must not even be reached
    res = client.post("/api/chat", json={"message": "   "})
    assert res.status_code == 422


def test_chat_returns_graceful_error_when_ai_unreachable(app, client):
    app.state.query_engine = BrokenQueryEngine()
    res = client.post("/api/chat", json={"message": "When does the library open?"})
    assert res.status_code == 503
    assert "try again" in res.json()["detail"].lower()


def test_upload_pdf_returns_chunk_count_and_lists_document(client):
    pdf_bytes = b"%PDF-1.4 fake handbook content for the campus assistant"
    res = client.post(
        "/api/admin/documents",
        files={"file": ("handbook.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["filename"] == "handbook.pdf"
    assert body["chunks"] > 0

    listing = client.get("/api/admin/documents")
    assert listing.status_code == 200
    docs = listing.json()["documents"]
    assert {"filename": "handbook.pdf", "chunks": body["chunks"]} in docs


def test_upload_rejects_non_pdf_with_clear_message(client):
    res = client.post(
        "/api/admin/documents",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
    )
    assert res.status_code == 400
    assert "PDF" in res.json()["detail"]


def test_upload_rejects_empty_file(client):
    res = client.post(
        "/api/admin/documents",
        files={"file": ("blank.pdf", b"", "application/pdf")},
    )
    assert res.status_code == 400


def test_delete_removes_document_from_listing(client):
    pdf_bytes = b"%PDF-1.4 outdated syllabus content"
    client.post(
        "/api/admin/documents",
        files={"file": ("syllabus.pdf", pdf_bytes, "application/pdf")},
    )

    res = client.delete("/api/admin/documents/syllabus.pdf")
    assert res.status_code == 200

    listing = client.get("/api/admin/documents").json()["documents"]
    assert all(doc["filename"] != "syllabus.pdf" for doc in listing)


def test_delete_unknown_document_returns_404(client):
    res = client.delete("/api/admin/documents/ghost.pdf")
    assert res.status_code == 404


def test_student_portal_is_served(client):
    res = client.get("/student/")
    assert res.status_code == 200
    assert "Campus Saathi" in res.text


def test_admin_portal_is_served(client):
    res = client.get("/admin/")
    assert res.status_code == 200
    assert "Admin Portal" in res.text
