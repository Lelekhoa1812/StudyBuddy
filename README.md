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
StudyBuddy is an end-to-end Retrieval-Augmented Generation (RAG) app for learning from your own documents. Upload PDF/DOCX files; the app extracts text and images, captions images, chunks content into semantic “cards,” embeds them in MongoDB, and serves a chat endpoint that answers strictly from your uploaded materials. It includes a lightweight chat-memory feature, cost-aware model routing, NVIDIA/Gemini integration, and robust key rotation/retries.

## Features

- **Document ingestion**: PDF/DOCX parsing (PyMuPDF, python-docx), image extraction, BLIP-based captions
- **Semantic chunking**: heuristic headings/size-based chunker → study cards with topic, summary, content
- **Embeddings**: Sentence-Transformers (`all-MiniLM-L6-v2`) with defensive fallbacks
- **Vector search**: MongoDB Atlas Vector Search (optional) or local cosine fallback
- **RAG chat**: cost-aware routing between NVIDIA and Gemini endpoints
- **Filename-aware questions**: detects filenames in questions (e.g., `JADE.pdf`) and prioritizes them
- **Classifier + fallbacks**: NVIDIA classifies file relevance; if retrieval is empty, the app retries (mentions-only, then all files) and finally falls back to file-level summaries
- **Chat memory**: per-user LRU of QA summaries; history relevance + semantic retrieval
- **Logging**: tagged logs per module, e.g., [APP], [RAG], [EMBED], [ROUTER]
- **Simple UI**: static frontend under `static/`

## Architecture

High level flow:
1) Upload PDF/DOCX → parse pages → extract images → BLIP captions → merge → chunk into cards → embed → store.
2) Chat request → detect any filenames in the question → preload filenames + summaries.
3) NVIDIA marks per-file relevance. Any filenames explicitly mentioned are always included.
4) Vector search restricted to relevant files. If no hits: retry with mentioned files only, then with all files. If still no hits but summaries exist, return those summaries.
5) Compose answer with strict guardrails to “answer from context only.” Summarize the Q/A and store in per-user LRU memory.

## Project Structure

```text
app.py                       # FastAPI app, routes, background ingestion, chat
utils/logger.py              # Centralized tagged logger
utils/parser.py              # PDF/DOCX parsing and image extraction
utils/caption.py             # BLIP image captioning (transformers)
utils/chunker.py             # Heuristic chunk builder
utils/embeddings.py          # Embedding client (Sentence-Transformers)
utils/rag.py                 # Mongo-backed store and vector search
utils/rotator.py             # API key rotator + robust HTTP POST helper
utils/router.py              # Model selection + LLM invocation helpers
utils/summarizer.py          # sumy-based extractive summarizer
utils/common.py              # small helpers
memo/memory.py               # per-user LRU memory store
memo/history.py              # history relevance + semantic helpers
static/                      # minimal frontend (index.html, script.js, styles.css)
Dockerfile                   # container image
requirements.txt             # Python dependencies
```

## Prerequisites
- Python 3.10+
- MongoDB (local or Atlas). Collections are created automatically
- Optional: NVIDIA and/or Gemini API keys

## Setup (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export MONGO_URI="mongodb://localhost:27017"
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Open the UI at `http://localhost:8000/static/`

Health check: `http://localhost:8000/healthz`

## Configuration

Environment variables:

- **MONGO_URI**: MongoDB connection string (required)
- **MONGO_DB**: MongoDB database name (default: studybuddy)
- **ATLAS_VECTOR**: set to "1" to enable Atlas Vector Search, else local cosine (default: 0)
- **MONGO_VECTOR_INDEX**: Atlas Search index name for vectors (default: vector_index)
- **EMBED_MODEL**: sentence-transformers model name (default: sentence-transformers/all-MiniLM-L6-v2)
- **GEMINI_API_1..5**: Gemini API keys for rotation
- **NVIDIA_API_1..5**: NVIDIA API keys for rotation
- **GEMINI_SMALL, GEMINI_MED, GEMINI_PRO**: override default Gemini models
- **NVIDIA_SMALL**: override default NVIDIA small model
- Optional logging controls: use process env like `PYTHONWARNINGS=ignore` and manage verbosity per logger if needed

Logs are emitted at INFO level to stdout with module tags. See `utils/logger.py`.

## Running (Local)

```bash
export MONGO_URI="mongodb://localhost:27017"  # or Atlas URI
uvicorn app:app --reload --workers 1 --host 0.0.0.0 --port 8000
```

Open the UI: `http://localhost:8000/static/`

Health check: `http://localhost:8000/healthz`

## Running (Docker)

Build and run:

```bash
docker build -t studybuddy-rag .
docker run --rm -p 8000:8000 \
  -e MONGO_URI="<your-mongo-uri>" \
  -e MONGO_DB="studybuddy" \
  -e NVIDIA_API_1="<nvidia-key>" \
  -e GEMINI_API_1="<gemini-key>" \
  studybuddy-rag
```

For production, consider `--restart unless-stopped` and setting `--env ATLAS_VECTOR=1` if using Atlas Vector Search.

## Usage
UI:
- Open `http://localhost:8000/static/`
- Upload PDF/DOCX
- Ask questions. You can reference filenames, e.g., “Give me a summary on `JADE.pdf` …
API:
- `GET /` → serves `static/index.html`
- `POST /upload` (multipart form-data)
  - fields: `user_id` (str), `project_id` (str), `files` (one or more PDF/DOCX)
  - response: `{ job_id, status: "processing", total_files }`; background ingestion continues
- `GET /upload/status?job_id=...` → progress
- `GET /files?user_id=&project_id=` → filenames + summaries
- `GET /file-summary?user_id=&project_id=&filename=` → `{ filename, summary }`
- `POST /chat` (form)
  - fields: `user_id`, `project_id`, `question`, `k` (default 6)
  - behavior:
    - If the question directly asks for a summary/about of a single mentioned file, returns that file’s stored summary.
    - Otherwise: NVIDIA relevance classification → vector search (restricted) → retries → summary fallback when needed.
  - returns `{ answer, sources, relevant_files }`

Example chat cURL:

```bash
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'user_id=user1' \
  -d 'project_id=demo' \
  --data-urlencode 'question=Give me a summary on JADE.pdf and setup steps'
```

Upload example:

```bash
curl -X POST http://localhost:8000/upload \
  -H 'Content-Type: multipart/form-data' \
  -F 'user_id=user1' \
  -F 'project_id=demo' \
  -F 'files=@/path/to/file1.pdf' \
  -F 'files=@/path/to/file2.docx'
```

## Data Model

- Collection `chunks` (per card):
  - `user_id`, `project_id`, `filename`, `topic_name`, `summary`, `content`, `page_span`, `card_id`, `embedding[384]`
- Collection `files` (per file):
  - `user_id`, `project_id`, `filename`, `summary`

### Atlas Vector Index (optional)

If using Atlas Vector Search, create an index similar to:

```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "embedding": {
        "type": "knnVector",
        "dimensions": 384,
        "similarity": "cosine"
      }
    }
  }
}
```

Set `ATLAS_VECTOR=1` and configure `MONGO_VECTOR_INDEX`.

### Schema overview:

- Collection `chunks` (per card):
  - `user_id` (str), `filename` (str), `topic_name` (str), `summary` (str), `content` (str)
  - `page_span` ([int, int])
  - `card_id` (slug + sequence)
  - `embedding` (float[384])
- Collection `files` (per file):
  - `user_id` (str), `filename` (str), `summary` (str)

## Notes on Models and Keys

- NVIDIA and Gemini calls use a simple key rotator. Provide one or more keys via `NVIDIA_API_1..5`, `GEMINI_API_1..5`.
- The app is defensive: if embeddings or summarization models are unavailable, it falls back to naive strategies to keep the app responsive (with reduced quality).

### Logging and Observability

- Logs are tagged by module via `utils/logger.py`:
  - [APP] app lifecycle, ingestion, chat flow
  - [RAG] storage, vector search
  - [EMBED] embedding model loads and fallbacks
  - [CAPTION] BLIP model loads and captioning
  - [ROUTER]/[ROTATOR] model routing and retry/rotation events
  - [CHUNKER]/[SUM]/[COMMON]/[PARSER] module-specific messages
- Change verbosity by setting the root logger level in code if needed

### Performance and Cost Tips

- Disable image captioning if CPU-bound by short-circuiting in `utils/caption.py` (return "")
- Use smaller `k` in `/chat` for fewer chunks
- Prefer NVIDIA_SMALL for simple questions (already default via router)
- If Atlas Vector is unavailable, local cosine search samples up to 2000 docs; tune in `utils/rag.py`
- Run with `--workers` and consider a process manager for production

#$# Retriver Functionalities

- Filename detection: regex captures tokens ending with `.pdf|.docx|.doc` in the user question; preceding prose is not captured.
- Relevance: NVIDIA classifies files by relevance to the question; any explicitly mentioned filenames are force-included.
- Retrieval: vector search is run over relevant files; on empty hits, it retries with mentions-only, then with all files.
- Fallback: if retrieval yields no chunks but file summaries exist, the app returns a composed summary response.
- Guardrails: responses are instructed to answer only from provided context and to admit when unknown.
- “I don’t know…” often means no chunks were retrieved:
  - Verify ingestion finished: `GET /upload/status`
  - Confirm files exist: `GET /files`
  - Try `GET /file-summary` to ensure summaries exist
  - Check logs around `[APP] [CHAT]` for relevance, retries, and fallbacks
- NVIDIA/Gemini API: ensure keys are set (`NVIDIA_API_1..`, `GEMINI_API_1..`). See `[ROUTER]`/`[ROTATOR]` logs.
- Atlas Vector: set `ATLAS_VECTOR=1` and ensure the index exists; otherwise local cosine fallback is used.
- Performance: disable BLIP captions in `utils/caption.py` if CPU-bound; reduce `k` in `/chat`.

## Security Notes

- CORS is currently open (`allow_origins=["*"]`) for simplicity. Restrict in production
- Validate and limit upload sizes at the reverse proxy (e.g., nginx) or add checks in `/upload`
- Secrets are passed via environment; avoid committing them


## Troubleshooting

- Missing Python packages: install via `pip install -r requirements.txt`.
- Ingestion stalls: check `[APP]` logs; large files and image captioning (BLIP) can be slow on CPU.
- No vector hits:
  - Ensure documents were embedded and stored (see `[RAG] Inserted ... cards` logs)
  - Verify `MONGO_URI` and collection contents
  - If Atlas Vector is on, confirm index exists and `ATLAS_VECTOR=1`
- NVIDIA/Gemini errors: see `[ROUTER]`/`[ROTATOR]` logs; key rotation retries transient errors.
 - PIL/transformers/torch issues on ARM Macs: ensure correct torch build or disable captioning
 - PyMuPDF font warnings: generally safe to ignore; upgrade PyMuPDF if needed

## Development

- Code style: straightforward, explicit names, tagged logging
- Frontend: simple static site in `static/`
- Extend chunking/embeddings or swap providers by editing modules in `utils/`
- Optional Makefile targets you can add:

```Makefile
run:
	uvicorn app:app --reload

docker-build:
	docker build -t studybuddy-rag .

docker-run:
	docker run --rm -p 8000:8000 -e MONGO_URI="mongodb://host.docker.internal:27017" studybuddy-rag
```

## License

**Apache-2.0**

