---
title: EdSummariser
emoji: 📚 
colorFrom: inigo
colorTo: blue
sdk: docker
sdk_version: latest
pinned: false
license: apache-2.0
short_description: Ed-Assistant summary your learning journey with Agentic RAG
---

### StudyBuddy RAG

An end-to-end RAG (Retrieval-Augmented Generation) app for studying from your own documents. Upload PDF/DOCX files, the app extracts text and images, captions images, chunks into semantic "cards", embeds and stores them in MongoDB, and serves a chat endpoint that answers strictly from your uploaded materials. Includes a lightweight chat-memory feature to improve context continuity, cost-aware model routing, and robust provider retries.

## Features

- **Document ingestion**: PDF/DOCX parsing (PyMuPDF, python-docx), image extraction and BLIP-based captions
- **Semantic chunking**: heuristic heading/size-based chunker
- **Embeddings**: Sentence-Transformers (all-MiniLM-L6-v2 by default) with random fallback when unavailable
- **Vector search**: MongoDB Atlas Vector Search (optional) or local cosine fallback
- **RAG chat**: cost-aware routing between Gemini and NVIDIA endpoints
- **Chat memory**: per-user LRU of recent QA summaries; history and semantic retrieval to augment context
- **Summarization**: cheap extractive summaries via sumy with naive fallback
- **Centralized logging**: tagged loggers per module, e.g., [APP], [RAG], [CHUNKER]
- **Simple UI**: static frontend under `static/`

## Prerequisites

- Python 3.10+
- MongoDB instance (local or Atlas). Collections are created automatically
- Optional: NVIDIA and/or Gemini API keys for model calls
- Optional but recommended: a virtual environment

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

## Quickstart (Local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export MONGO_URI="mongodb://localhost:27017"
uvicorn app:app --reload
```

Open UI: `http://localhost:8000/static/`

Health: `http://localhost:8000/healthz`

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

Logging: Logs are sent to stdout at INFO level, tagged per module, e.g., `[APP]`, `[RAG]`. See `utils/logger.py`.

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

## API Overview

- GET `/` → serves `static/index.html`
- POST `/upload` (multipart form-data)
  - fields: `user_id` (str), `files` (one or more PDF/DOCX)
  - response: `{ job_id, status: "processing" }`; ingestion proceeds in background
- GET `/cards`
  - params: `user_id` (str), `filename` (optional), `limit` (int), `skip` (int)
  - returns stored cards without embeddings
- GET `/file-summary`
  - params: `user_id`, `filename`
  - returns `{ filename, summary }`
- POST `/chat` (form-urlencoded)
  - fields: `user_id`, `question`, `k` (int, default 6)
  - logic:
    - If question matches "what is <file> about?": returns file summary
    - Else: classify relevant files via NVIDIA, augment with chat memory context, run vector search (restricted to relevant files if any), select model, generate answer, store QA summary in LRU
  - returns `{ answer, sources }` (and `relevant_files` when no hits)

Example cURL:

```bash
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'user_id=user1' \
  --data-urlencode 'question=Summarize reinforcement learning from the uploaded notes.'
```

Upload example:

```bash
curl -X POST http://localhost:8000/upload \
  -H 'Content-Type: multipart/form-data' \
  -F 'user_id=user1' \
  -F 'files=@/path/to/file1.pdf' \
  -F 'files=@/path/to/file2.docx'
```

List cards:

```bash
curl 'http://localhost:8000/cards?user_id=user1&limit=10'
```

## MongoDB Atlas Vector Index (optional)

If using Atlas Vector Search, create an index (UI or API) similar to:

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

Set `ATLAS_VECTOR=1` and `MONGO_VECTOR_INDEX` accordingly.

Schema overview:

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

## Logging and Observability

- Logs are tagged by module via `utils/logger.py`:
  - [APP] app lifecycle, ingestion, chat flow
  - [RAG] storage, vector search
  - [EMBED] embedding model loads and fallbacks
  - [CAPTION] BLIP model loads and captioning
  - [ROUTER]/[ROTATOR] model routing and retry/rotation events
  - [CHUNKER]/[SUM]/[COMMON]/[PARSER] module-specific messages
- Change verbosity by setting the root logger level in code if needed

## Performance and Cost Tips

- Disable image captioning if CPU-bound by short-circuiting in `utils/caption.py` (return "")
- Use smaller `k` in `/chat` for fewer chunks
- Prefer NVIDIA_SMALL for simple questions (already default via router)
- If Atlas Vector is unavailable, local cosine search samples up to 2000 docs; tune in `utils/rag.py`
- Run with `--workers` and consider a process manager for production

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

MIT (or your preferred license). Replace this section if needed.


