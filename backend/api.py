"""HTTP API + Portal serving (ADR-0003).

All routes read their collaborators (QueryEngine, PDFProcessor, KnowledgeBase)
from ``app.state``, so tests can inject fakes through the HTTP seam only.

API contract:
    POST   /api/chat                     {message} -> {answer}
    POST   /api/admin/documents          multipart PDF -> {filename, chunks}
    GET    /api/admin/documents          -> {documents: [{filename, chunks}]}
    DELETE /api/admin/documents/{filename}            -> removes that file's chunks

Portals are served same-origin at /student and /admin — no CORS config.
"""

import os

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.pdf_processor import PDFProcessor
from backend.query_engine import QueryEngine
from backend.vector_store import KnowledgeBase

router = APIRouter()


# --- Lazy production wiring (tests replace these on app.state) ---

def _get_state(request: Request, key: str, factory):
    value = getattr(request.app.state, key, None)
    if value is None:
        value = factory()
        setattr(request.app.state, key, value)
    return value


def get_query_engine(request: Request) -> QueryEngine:
    def build():
        return QueryEngine(knowledge_base=get_knowledge_base(request))
    return _get_state(request, "query_engine", build)


def get_pdf_processor(request: Request) -> PDFProcessor:
    def build():
        return PDFProcessor(knowledge_base=get_knowledge_base(request))
    return _get_state(request, "pdf_processor", build)


def get_knowledge_base(request: Request) -> KnowledgeBase:
    return _get_state(request, "knowledge_base", KnowledgeBase)


# --- Schemas ---

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str


class DocumentResponse(BaseModel):
    filename: str
    chunks: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


# --- Routes ---

@router.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message must not be empty.")
    try:
        engine = get_query_engine(request)
        answer = engine.process_query(message)
    except ValueError as exc:  # missing configuration
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:  # adapter failed at request time
        raise HTTPException(
            status_code=503,
            detail="The assistant can't reach its AI service right now. Please try again later.",
        )
    return ChatResponse(answer=answer)


@router.post("/api/admin/documents", response_model=DocumentResponse)
def upload_document(request: Request, file: UploadFile):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    processor = get_pdf_processor(request)
    try:
        chunks = processor.process_and_ingest(file_bytes, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ingestion failed: {exc}")
    return DocumentResponse(filename=file.filename, chunks=chunks)


@router.get("/api/admin/documents", response_model=DocumentListResponse)
def list_documents(request: Request):
    try:
        kb = get_knowledge_base(request)
    except ValueError as exc:  # missing configuration
        raise HTTPException(status_code=503, detail=str(exc))
    return DocumentListResponse(
        documents=[DocumentResponse(**doc) for doc in kb.list_documents()]
    )


@router.delete("/api/admin/documents/{filename}")
def delete_document(filename: str, request: Request):
    try:
        kb = get_knowledge_base(request)
    except ValueError as exc:  # missing configuration
        raise HTTPException(status_code=503, detail=str(exc))
    if not kb.delete_document(filename):
        raise HTTPException(status_code=404, detail=f"'{filename}' not found.")
    return {"status": "deleted", "filename": filename}


def mount_portals(app, frontend_dir: str | None = None) -> None:
    """Serve the two single-page portals same-origin (no CORS)."""
    base = frontend_dir or os.path.join(os.path.dirname(__file__), os.pardir, "frontend")
    student_dir = os.path.join(base, "student")
    admin_dir = os.path.join(base, "admin")
    if os.path.isdir(student_dir):
        app.mount("/student", StaticFiles(directory=student_dir, html=True), name="student")
    if os.path.isdir(admin_dir):
        app.mount("/admin", StaticFiles(directory=admin_dir, html=True), name="admin")
