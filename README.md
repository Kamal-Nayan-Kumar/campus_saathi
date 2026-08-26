# Campus Saathi

**RAG-powered campus assistant for IIIT Dharwad — ask in any language, get grounded answers from college documents.**

Live on Render · Two web portals + two Telegram bots · Same Knowledge Base, same pipeline.

**Live Demo →** https://campus-saathi-system.onrender.com

| Portal | URL |
|---|---|
| Student — ask questions | [/student](https://campus-saathi-system.onrender.com/student/) |
| Admin — upload / manage docs | [/admin](https://campus-saathi-system.onrender.com/admin/) |
| Health | [/health](https://campus-saathi-system.onrender.com/health) |

Telegram: Student Bot & Admin Bot (webhook via `WEBHOOK_URL`)

---

## What it does

- **Student** asks a question in any language → answer comes back in the same language, grounded in ingested college PDFs (not hallucinated).
- **Admin** uploads a PDF → it is parsed, chunked, embedded, and searchable within seconds. Lists all documents and can delete outdated ones.
- Works identically on **web** and **Telegram** — both surfaces share one RAG pipeline.

Core user stories: multilingual Q&A, grounded answers, chunk count after upload, document list/delete, non-PDF rejection, upload progress & “thinking…” states, graceful error when the AI service is unreachable.

## Architecture

```
                ┌─────────────┐      ┌─────────────┐
  PDF upload →  │  Firecrawl  │      │    Groq     │
  (Admin)       │   /parse    │      │ gpt-oss-120b│
       │        │  → markdown │      │  (translate │
       ▼        └──────┬──────┘      │   + answer) │
  ┌──────────┐         │             └──────┬──────┘
  │ Recursive│         ▼                    │
  │ Character│    ┌──────────┐         ┌────▼─────┐
  │ Splitter │───→│  Qdrant  │←───────→│ LangChain│ ←── user question
  │ (LangChain)   │  Cloud   │ search  │  chain   │     (any language)
  └──────────┘    │ Inference│         └──────────┘
                  │ all-MiniLM-L6-v2
                  │ payload: filename, chunk_index, content
                  └──────────┘
         ▲                              │
         │         FastAPI              ▼
  ┌──────┴──────┐  serves  ┌──────────────────────┐
  │ Telegram    │◄────────►│  Student + Admin     │
  │ Bots (2)    │  same    │  Portals (static)    │
  └─────────────┘  modules └──────────────────────┘
```

**One Knowledge Base, one QueryEngine, three surfaces.** Bots and HTTP routes call the same `PDFProcessor` / `QueryEngine` modules. No auth (demo posture).

## Tech Stack

| Concern | Choice | Why |
|---|---|---|
| RAG framework | **LangChain** (`langchain-openai` client, no `langchain-groq`) | Resume-aligned, owns chain + splitting |
| LLM | **Groq** `openai/gpt-oss-120b` via OpenAI-compatible API | Fast inference, open-weight |
| Vector DB | **Qdrant Cloud** | Managed, free tier |
| Embeddings | **Qdrant Cloud Inference** `sentence-transformers/all-MiniLM-L6-v2` (384d, server-side, Cost: Free) | No local model to host |
| PDF parsing | **Firecrawl** `/parse` → markdown | Clean markdown, no fallback parser |
| Chunking | `RecursiveCharacterTextSplitter` (1000 / 150) | LangChain-native |
| Server | **FastAPI** + **python-telegram-bot** | Webhooks + static portals same-origin (no CORS) |
| Frontend | Plain HTML/CSS/vanilla JS, no build step | Zero `node_modules`, interviewer-friendly |
| Deploy | **Render** (Procfile) | Single origin for API + portals + bots |

> Resume line: *“RAG pipeline (LangChain, Groq’s open-weight gpt-oss-120b LLM, Qdrant Cloud vector search with server-side embeddings)”* — code matches it literally.

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | `{message}` → `{answer}` |
| `POST` | `/api/admin/documents` | multipart `file` (PDF) → `{filename, chunks}` |
| `GET` | `/api/admin/documents` | → `{documents: [{filename, chunks}]}` |
| `DELETE` | `/api/admin/documents/{filename}` | removes that file’s chunks (payload filter on `filename`) |

Portals are served at `/student` and `/admin` from the same origin.

Telegram webhooks: `POST /student-webhook` and `POST /admin-webhook`.

## Local Setup

**Prereqs:** Python 3.14, a Qdrant Cloud cluster (enable `all-MiniLM-L6-v2` in Inference tab — must show “Cost: Free”), Groq API key, Firecrawl API key, two Telegram bot tokens from @BotFather.

```bash
git clone https://github.com/Kamal-Nayan-Kumar/campus_saathi.git
cd campus_saathi

# venv
uv venv --python 3.14
source .venv/bin/activate   # or: uv pip install -r requirements.txt with VIRTUAL_ENV=.venv

uv pip install -r requirements.txt

cp .env.example .env
# fill .env: TELEGRAM_*_TOKEN, WEBHOOK_URL, GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY, FIRECRAWL_API_KEY

# run
python main.py
# → http://localhost:8000/student/  http://localhost:8000/admin/  http://localhost:8000/health
```

Set `WEBHOOK_URL` to your public URL (e.g. ngrok or Render) for Telegram bots; leave it empty for local portal-only testing.

**Live check against real services (outside test suite):**

```bash
python scripts/live_check.py path/to/any.pdf
# ingest → list → ask a grounded question → delete → PASSED
```

## Testing

Tests hit the **HTTP seam only** (FastAPI `TestClient`, faked Groq/Qdrant/Firecrawl adapters). No live keys needed.

```bash
pytest -q          # 11 tests
pytest -v
```

Covers: chat returns an answer, 422 on empty/whitespace, 503 when the AI service is unreachable, PDF upload → chunk count + appears in list, non-PDF rejected (400), empty file rejected, delete removes from listing (404 on unknown), both portals serve 200.

## Project Structure

```
.
├── main.py                 # FastAPI app, lifespan (bots + webhooks), mounts API + portals
├── student_bot.py          # Student Telegram bot — no auth, direct Q&A
├── admin_bot.py            # Admin Telegram bot — no auth, PDF ingestion
├── backend/
│   ├── api.py              # HTTP routes + same-origin portal mounting (app.state seam)
│   ├── vector_store.py     # KnowledgeBase — Qdrant Cloud Inference adapter
│   ├── pdf_processor.py    # Ingestion — Firecrawl /parse + splitter + upsert
│   └── query_engine.py     # RAG chain — LangChain on Groq (translate → retrieve → answer)
├── frontend/
│   ├── student/index.html  # Student portal — chat thread, chips, thinking/error states
│   └── admin/index.html    # Admin portal — upload, list, delete
├── tests/
│   ├── conftest.py         # app + fakes wiring
│   ├── fakes.py            # in-memory KnowledgeBase / PDFProcessor / QueryEngine
│   └── test_api.py         # HTTP-seam tests
├── scripts/live_check.py   # one-off manual check against real cloud services
├── documents/              # sample PDFs (tracked for demo)
├── requirements.txt
├── Procfile                # Render: web: python main.py
└── .env.example            # all required env vars documented
```

External services sit behind **small adapters** (`vector_store.py`, `pdf_processor.py`, `query_engine.py`) — swapping a provider touches one file.

## Deployment — Render

`Procfile` + env vars is all Render needs. Auto-deploy is on `master`.

Required env vars on Render → Environment: `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `FIRECRAWL_API_KEY`, `TELEGRAM_STUDENT_BOT_TOKEN`, `TELEGRAM_ADMIN_BOT_TOKEN`, `WEBHOOK_URL` (set to `https://<your-service>.onrender.com`).

## Notes

- No authentication anywhere — intentional demo posture. Don’t publicly link the Admin portal.
- Dense vectors only, no hybrid/BM25, no conversation memory, PDF-only, no streaming.
- Old Astra DB data was abandoned on re-embed; re-ingest documents after switching to Qdrant.

---

Built as a portfolio piece — code is meant to survive a walkthrough against the resume.
