---
title: EdSummariser
emoji: 📚 
colorFrom: red
colorTo: indigo
sdk: docker
sdk_version: latest
pinned: false
license: apache-2.0
short_description: Ed-Assistant summary your learning journey with Agentic RAG
---

### StudyBuddy (EdSummariser)
[Live demo](https://binkhoale1812-edsummariser.hf.space)

StudyBuddy is an end-to-end Retrieval-Augmented Generation (RAG) app for learning from your own documents. 

- Ingestion: PDF/DOCX parse → optional image captions → chunk to cards → embed → store.
- Retrieval: filename detection → per-file relevance classification (NVIDIA) → vector search (Mongo Atlas or local cosine) with retries and summary fallbacks.
- Reasoning: context-only answering; per-user recent-memory mixing (classification + semantic); key rotation and robust HTTP for LLMs.

### Key Endpoints (FastAPI)

- Auth: `POST /auth/signup`, `POST /auth/login`
- Projects: `POST /projects/create`, `GET /projects`, `GET /projects/{id}`, `DELETE /projects/{id}`
- Upload: `POST /upload`, `GET /upload/status`
- Data: `GET /files`, `GET /file-summary`, `GET /cards`
- Chat: `POST /chat` → `{ answer, sources, relevant_files }`
- Report: `POST /report` (Gemini CoT filter + write), `POST /report/pdf`
- Health: `GET /healthz`, `GET /rag-status`, `GET /test-db`

High level flow:
1) Upload PDF/DOCX → parse pages → extract images → BLIP captions → merge → chunk into cards → embed → store.
2) Chat request → detect any filenames in the question → preload filenames + summaries.
3) NVIDIA marks per-file relevance. Any filenames explicitly mentioned are always included.
4) Vector search restricted to relevant files. If no hits: retry with mentioned files only, then with all files. If still no hits but summaries exist, return those summaries.
5) Compose answer with strict guardrails to “answer from context only.” Summarize the Q/A and store in per-user LRU memory.

## Project Structure

```text
app.py                  # FastAPI app, routes, chat/report flows, ingestion orchestration
static/                 # Minimal UI (index.html, styles, scripts)
memo/                   # Memory system (LRU + helpers)
utils/
  api/                  # Model router, key rotator
  ingestion/            # Parsing, captioning, chunking
  rag/                  # Embeddings + RAG store (Mongo + vector search)
  service/              # Summarizer, PDF generation (dark IDE-like code blocks)
  logger.py             # Tagged logging
Dockerfile
requirements.txt
```

### Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export MONGO_URI="mongodb://localhost:27017"
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Open: `http://localhost:8000/static/`  •  Health: `GET /healthz`

### Configuration

- MONGO_URI (required), MONGO_DB (default: studybuddy)
- ATLAS_VECTOR=1 to enable Atlas Vector Search, MONGO_VECTOR_INDEX (default: vector_index)
- EMBED_MODEL (default: sentence-transformers/all-MiniLM-L6-v2)
- NVIDIA_API_1..5, GEMINI_API_1..5 (key rotation); model overrides via GEMINI_SMALL|MED|PRO, NVIDIA_SMALL

### Retrieval Strategy (concise)

1) Detect mentioned filenames (e.g., `JADE.pdf`).
2) Classify file relevance (NVIDIA) and restrict search.
3) Vector search → on empty hits, retry with mentions-only → all files → fallback to file-level summaries.
4) Answer from context only; store compact memory summaries.

### Notes

- PDF export renders code blocks with a dark IDE-like theme and lightweight syntax highlighting; control characters are stripped to avoid square artifacts.
- CORS is open for the demo UI; restrict for production.

### Docs

[Report Generation](https://huggingface.co/spaces/BinKhoaLe1812/EdSummariser/blob/main/report.pdf)

[Memo Dir](https://huggingface.co/spaces/BinKhoaLe1812/EdSummariser/blob/main/memo/README.md)

[Utils Dir](https://huggingface.co/spaces/BinKhoaLe1812/EdSummariser/blob/main/utils/README.md)

[Routes Dir](https://huggingface.co/spaces/BinKhoaLe1812/EdSummariser/blob/main/routes/README.md)

[Agent Assignment](https://huggingface.co/spaces/BinKhoaLe1812/EdSummariser/blob/main/AGENT_ASNM.md)

### License

Apache-2.0