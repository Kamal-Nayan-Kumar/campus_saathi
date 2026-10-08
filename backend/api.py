"""HTTP API + Portal serving (ADR-0003).

All routes read their collaborators (QueryEngine, PDFProcessor, KnowledgeBase,
WebsiteCrawler) from ``app.state``, so tests can inject fakes through the HTTP seam only.

API contract:
    POST   /api/chat                     {message} -> {answer}
    POST   /api/admin/documents          multipart file -> {filename, chunks}
    GET    /api/admin/documents          -> {documents: [{filename, chunks}]}
    DELETE /api/admin/documents/{filename}            -> removes that file's chunks
    GET    /api/admin/misses             -> questions the Knowledge Base couldn't answer
    DELETE /api/admin/misses             -> clear that log
    POST   /api/admin/website/crawl      -> crawl iiitdwd.ac.in via Firecrawl
    GET    /api/admin/website/status     -> crawl status & website docs
    DELETE /api/admin/website            -> remove all website:* docs

Portals are served same-origin at /student and /admin — no CORS config.
"""

import os

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.miss_log import MissLog
from backend.pdf_processor import PDFProcessor
from backend.query_engine import QueryEngine
from backend.vector_store import KnowledgeBase
from backend.website_crawler import WebsiteCrawler

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


def get_website_crawler(request: Request) -> WebsiteCrawler:
    def build():
        return WebsiteCrawler(knowledge_base=get_knowledge_base(request))
    return _get_state(request, "website_crawler", build)


def get_miss_log(request: Request) -> MissLog:
    return _get_state(request, "miss_log", MissLog)


# --- Schemas ---

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []  # list of {role: "user"|"assistant", content: str}, last 5 max


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []
    # ADR-0004: no runtime web search. A miss is logged for the admin instead.
    missed: bool = False
    miss_count: int | None = None


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
        result = engine.process_query(message, payload.history)
        # Backward compat: process_query may return 2 or 3 values
        if isinstance(result, tuple) and len(result) == 3:
            answer, sources, miss = result
        elif isinstance(result, tuple) and len(result) == 2:
            answer, sources = result
            miss = {"missed": False, "query": None, "count": None}
        else:
            answer, sources = result[0], result[1]
            miss = {"missed": False, "query": None, "count": None}
        miss = miss or {"missed": False, "query": None, "count": None}
    except ValueError as exc:  # missing configuration
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:  # adapter failed at request time
        raise HTTPException(
            status_code=503,
            detail="The assistant can't reach its AI service right now. Please try again later.",
        )
    return ChatResponse(
        answer=answer,
        sources=sources,
        missed=bool(miss.get("missed")),
        miss_count=miss.get("count"),
    )


@router.post("/api/admin/documents", response_model=DocumentResponse)
def upload_document(request: Request, file: UploadFile):
    lower = (file.filename or "").lower()
    allowed = (".pdf", ".xlsx", ".xls", ".txt", ".md", ".docx", ".doc")
    if not lower.endswith(allowed):
        raise HTTPException(status_code=400, detail="Only PDF, Excel, Word (.docx), text (.txt, .md) files are supported.")

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


# --- Unanswered questions (ADR-0004) ---

class MissResponse(BaseModel):
    query: str
    language: str | None = None
    count: int = 1
    first_seen: str
    last_seen: str


class MissListResponse(BaseModel):
    misses: list[MissResponse] = []
    total_queries: int = 0


@router.get("/api/admin/misses", response_model=MissListResponse)
def list_misses(request: Request, limit: int = 20):
    """What students asked that the Knowledge Base couldn't answer.

    This is the replacement for runtime web search: instead of the student
    path scraping iiitdwd.ac.in per miss, the admin sees the demand and
    decides what to crawl or upload.
    """
    log = get_miss_log(request)
    return MissListResponse(
        misses=[MissResponse(**m) for m in log.list_misses(limit)],
        total_queries=log.total_queries(),
    )


@router.delete("/api/admin/misses")
def clear_misses(request: Request):
    log = get_miss_log(request)
    return {"status": "cleared", "entries": log.clear()}


# --- Website crawl (Firecrawl, iiitdwd.ac.in) ---

class CrawlRequest(BaseModel):
    limit: int = 20
    url: str | None = None


class CrawlResponse(BaseModel):
    target: str
    pages: int
    chunks: int
    urls: list[str] = []
    deleted: int = 0
    timestamp: str


class WebsiteStatusResponse(BaseModel):
    target: str
    total_pages: int
    total_chunks: int
    documents: list[DocumentResponse]
    last_crawl: dict | None = None


@router.get("/api/admin/website/status", response_model=WebsiteStatusResponse)
def website_status(request: Request):
    try:
        crawler = get_website_crawler(request)
        status = crawler.get_status()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Status failed: {exc}")
    return WebsiteStatusResponse(
        target=status["target"],
        total_pages=status["total_pages"],
        total_chunks=status["total_chunks"],
        documents=[DocumentResponse(**d) for d in status["documents"]],
        last_crawl=status["last_crawl"],
    )


@router.post("/api/admin/website/crawl", response_model=CrawlResponse)
def crawl_website(payload: CrawlRequest | None, request: Request):
    limit = 20
    if payload and payload.limit:
        limit = max(1, min(50, payload.limit))
    if payload and payload.url:
        # allow override via payload, but validate iiitdwd domain
        if "iiitdwd.ac.in" not in payload.url:
            raise HTTPException(status_code=400, detail="Only iiitdwd.ac.in can be crawled")
    try:
        crawler = get_website_crawler(request)
        if payload and payload.url:
            crawler.target_url = payload.url
        result = crawler.crawl(limit=limit, delete_old=True)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Crawl failed: {exc}")
    return CrawlResponse(**result)


@router.delete("/api/admin/website")
def delete_website(request: Request):
    try:
        crawler = get_website_crawler(request)
        deleted = crawler._delete_existing()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"status": "deleted", "deleted": deleted}


def mount_portals(app, frontend_dir: str | None = None) -> None:
    """Serve the two single-page portals same-origin (no CORS)."""
    base = frontend_dir or os.path.join(os.path.dirname(__file__), os.pardir, "frontend")
    student_dir = os.path.join(base, "student")
    admin_dir = os.path.join(base, "admin")
    if os.path.isdir(student_dir):
        app.mount("/student", StaticFiles(directory=student_dir, html=True), name="student")
    if os.path.isdir(admin_dir):
        app.mount("/admin", StaticFiles(directory=admin_dir, html=True), name="admin")
