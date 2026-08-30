# Campus Saathi

**RAG-powered campus assistant for IIIT Dharwad — ask in any language, get grounded answers from college documents.**

Two web portals + two Telegram bots. One RAG pipeline, one Knowledge Base.

### Live Demo

**App:** https://campus-saathi-system.onrender.com

| Portal | Link |
|---|---|
| Student — ask questions | [campus-saathi-system.onrender.com/student/](https://campus-saathi-system.onrender.com/student/) |
| Admin — upload & manage documents | [campus-saathi-system.onrender.com/admin/](https://campus-saathi-system.onrender.com/admin/) |

Telegram: Student Bot & Admin Bot (webhook via `WEBHOOK_URL`)

---

## Screenshots

| Student Portal | Admin Portal | Telegram Bot |
|---|---|---|
| ![Student Portal](docs/screenshots/student-portal.png) | ![Admin Portal](docs/screenshots/admin-portal.png) | ![Telegram Bot](docs/screenshots/telegram-bot.png) |

> Add 3 images to `docs/screenshots/` with the names above. Recommended size: 1280x720.

---

## What it does

- **Student** asks a question in any language → answer in the same language, grounded in ingested PDFs. No hallucination.
- **Admin** uploads a PDF → parsed, chunked, embedded, and searchable in seconds. Can list and delete documents.
- Same RAG pipeline serves **Web and Telegram** — no duplicate logic.

---

## Architecture

```mermaid
flowchart TD
    A[Admin Uploads PDF] --> B[Firecrawl /parse<br/>PDF to Markdown]
    B --> C[RecursiveCharacterTextSplitter<br/>1000 / 150 overlap]
    C --> D[(Qdrant Cloud<br/>all-MiniLM-L6-v2<br/>384d)]

    E[Student Question<br/>Any Language] --> F[LangChain Chain<br/>Groq gpt-oss-120b]
    F -->|Translate + Retrieve| D
    D -->|Top-K Chunks| F
    F --> G[Grounded Answer<br/>Same Language]

    D --- H[FastAPI Server]
    H --- I[Student Portal<br>/student]
    H --- J[Admin Portal<br>/admin]
    H --- K[Telegram Bots x2<br/>Webhooks]

    style D fill:#6C5CE7,stroke:#fff,color:#fff
    style F fill:#00B894,stroke:#fff,color:#fff
    style H fill:#0984E3,stroke:#fff,color:#fff
```

<details>
<summary><b>Prompt to generate a polished image (for ChatGPT / Gemini)</b></summary>

Copy-paste this into ChatGPT image generation:

```
Create a modern, clean cloud architecture diagram for a RAG application called "Campus Saathi - IIIT Dharwad".

Style: Minimal, isometric or flat, white background, use rounded rectangles, soft shadows, tech colors (violet for vector DB, green for LLM, blue for server).

Show 3 flows:
1. INGESTION FLOW (left): Admin Portal / Telegram Admin Bot -> Uploads PDF -> Firecrawl API (PDF to Markdown) -> LangChain RecursiveCharacterTextSplitter (1000/150) -> Qdrant Cloud Vector DB (with all-MiniLM-L6-v2 384d embeddings, show payload: filename, chunk_index, content)
2. QUERY FLOW (right): Student Portal / Telegram Student Bot -> Asks question in any language -> LangChain + Groq gpt-oss-120b (Translate -> Vector Search -> Generate Answer) -> Qdrant Cloud (retrieve top-k chunks) -> Grounded Answer in same language
3. SERVER (center bottom): FastAPI server connecting everything, serving Student Portal at /student, Admin Portal at /admin, and 2 Telegram Webhooks. Deploy on Render (single origin, no CORS).

Label tech stack clearly. Title at top: "Campus Saathi - RAG Architecture". Add small legend at bottom. Make it interview-ready and suitable for README.
```

Save the image as `docs/screenshots/architecture.png` and add `![Architecture](docs/screenshots/architecture.png)` above the mermaid if you prefer an image.

</details>

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| RAG Framework | **LangChain** | Chain + text splitting |
| LLM | **Groq** `openai/gpt-oss-120b` | Fast, open-weight, OpenAI-compatible API |
| Vector DB | **Qdrant Cloud** | Managed, server-side embeddings |
| Embeddings | `all-MiniLM-L6-v2` (384d) via Qdrant Inference | No local model to host |
| PDF Parsing | **Firecrawl** `/parse` | Clean markdown output |
| Backend | **FastAPI** + **python-telegram-bot** | Webhooks + portals on one origin |
| Frontend | HTML/CSS/vanilla JS | No build step, zero dependencies |
| Deploy | **Render** | Single service for API + portals + bots |

---

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | `{message}` → `{answer}` |
| `POST` | `/api/admin/documents` | Upload PDF → `{filename, chunks}` |
| `GET` | `/api/admin/documents` | List all documents |
| `DELETE` | `/api/admin/documents/{filename}` | Delete a document |

Portals: `/student` and `/admin` (same origin). Telegram webhooks: `POST /student-webhook` and `POST /admin-webhook`.

---

## Project Structure

```
campus_saathi/
├── main.py                 # FastAPI app + lifespan (bots, webhooks)
├── student_bot.py          # Student Telegram bot
├── admin_bot.py            # Admin Telegram bot
├── backend/
│   ├── api.py              # Routes + portal mounting
│   ├── vector_store.py     # Qdrant adapter (KnowledgeBase)
│   ├── pdf_processor.py    # Firecrawl + chunking + upsert
│   ├── query_engine.py     # LangChain RAG chain on Groq
│   └── website_crawler.py  # College site crawler (Firecrawl)
├── frontend/
│   ├── student/index.html
│   └── admin/index.html
├── tests/                  # HTTP-seam tests (faked adapters, no live keys)
├── scripts/live_check.py   # Manual check against real services
├── documents/              # Sample PDFs
├── requirements.txt
└── Procfile                # Render: web: python main.py
```

External services are behind small adapters — swapping a provider touches one file.

---

## Local Setup

**Prereqs:** Python 3.14, Qdrant Cloud cluster, Groq key, Firecrawl key, 2 Telegram bot tokens.

```bash
git clone https://github.com/Kamal-Nayan-Kumar/campus_saathi.git
cd campus_saathi

uv venv --python 3.14
source .venv/bin/activate
uv pip install -r requirements.txt

cp .env.example .env
# fill: TELEGRAM_*_TOKEN, WEBHOOK_URL, GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY, FIRECRAWL_API_KEY

python main.py
# → http://localhost:8000/student/  http://localhost:8000/admin/
```

Leave `WEBHOOK_URL` empty for local-only testing. Set it to your public URL (ngrok / Render) to enable Telegram bots.

---

## Testing

```bash
pytest -q          # 11 tests, no live keys needed
```

Tests use FastAPI `TestClient` with faked adapters. Covers chat, upload, list, delete, and error states.

---

## Deployment

Deployed on **Render** via `Procfile`. Auto-deploy on `master`.