# https://binkhoale1812-edsummariser.hf.space/
import os, io, re, uuid, json, time, logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from utils.rotator import APIKeyRotator
from utils.parser import parse_pdf_bytes, parse_docx_bytes
from utils.caption import BlipCaptioner
from utils.chunker import build_cards_from_pages
from utils.embeddings import EmbeddingClient
from utils.rag import RAGStore, ensure_indexes
from utils.router import select_model, generate_answer_with_model
from utils.summarizer import cheap_summarize
from utils.common import trim_text
from utils.logger import get_logger

# ────────────────────────────── App Setup ──────────────────────────────
logger = get_logger("APP", name="studybuddy")

app = FastAPI(title="StudyBuddy RAG", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (index.html, scripts.js, styles.css)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ────────────────────────────── Global Clients ──────────────────────────────
# API rotators (round robin + auto failover on quota errors)
gemini_rotator = APIKeyRotator(prefix="GEMINI_API_", max_slots=5)
nvidia_rotator = APIKeyRotator(prefix="NVIDIA_API_", max_slots=5)

# Captioner + Embeddings (lazy init inside classes)
captioner = BlipCaptioner()
embedder = EmbeddingClient(model_name=os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))

# Mongo / RAG store
rag = RAGStore(mongo_uri=os.getenv("MONGO_URI"), db_name=os.getenv("MONGO_DB", "studybuddy"))
ensure_indexes(rag)


# ────────────────────────────── Auth Helpers/Routes ───────────────────────────
import hashlib
import secrets


def _hash_password(password: str, salt: Optional[str] = None) -> Dict[str, str]:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000)
    return {"salt": salt, "hash": dk.hex()}


def _verify_password(password: str, salt: str, expected_hex: str) -> bool:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000)
    return secrets.compare_digest(dk.hex(), expected_hex)


@app.post("/auth/signup")
async def signup(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    if not email or not password or "@" not in email:
        raise HTTPException(400, detail="Invalid email or password")
    users = rag.db["users"]
    if users.find_one({"email": email}):
        raise HTTPException(409, detail="Email already registered")
    user_id = str(uuid.uuid4())
    hp = _hash_password(password)
    users.insert_one({
        "email": email,
        "user_id": user_id,
        "pw_salt": hp["salt"],
        "pw_hash": hp["hash"],
        "created_at": int(time.time())
    })
    logger.info(f"[AUTH] Created user {email} -> {user_id}")
    return {"email": email, "user_id": user_id}


@app.post("/auth/login")
async def login(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    users = rag.db["users"]
    doc = users.find_one({"email": email})
    if not doc:
        raise HTTPException(401, detail="Invalid credentials")
    if not _verify_password(password, doc.get("pw_salt", ""), doc.get("pw_hash", "")):
        raise HTTPException(401, detail="Invalid credentials")
    logger.info(f"[AUTH] Login {email}")
    return {"email": email, "user_id": doc.get("user_id")}


# ────────────────────────────── Project Management ───────────────────────────
@app.post("/projects/create")
async def create_project(user_id: str = Form(...), name: str = Form(...), description: str = Form("")):
    """Create a new project for a user"""
    if not name.strip():
        raise HTTPException(400, detail="Project name is required")
    
    project_id = str(uuid.uuid4())
    project = {
        "project_id": project_id,
        "user_id": user_id,
        "name": name.strip(),
        "description": description.strip(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    rag.db["projects"].insert_one(project)
    logger.info(f"[PROJECT] Created project {name} for user {user_id}")
    return project


@app.get("/projects")
async def list_projects(user_id: str):
    """List all projects for a user"""
    projects = list(rag.db["projects"].find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("updated_at", -1))
    return {"projects": projects}


@app.get("/projects/{project_id}")
async def get_project(project_id: str, user_id: str):
    """Get a specific project (with user ownership check)"""
    project = rag.db["projects"].find_one(
        {"project_id": project_id, "user_id": user_id},
        {"_id": 0}
    )
    if not project:
        raise HTTPException(404, detail="Project not found")
    return project


@app.delete("/projects/{project_id}")
async def delete_project(project_id: str, user_id: str):
    """Delete a project and all its associated data"""
    # Check ownership
    project = rag.db["projects"].find_one({"project_id": project_id, "user_id": user_id})
    if not project:
        raise HTTPException(404, detail="Project not found")
    
    # Delete project and all associated data
    rag.db["projects"].delete_one({"project_id": project_id})
    rag.db["chunks"].delete_many({"project_id": project_id})
    rag.db["files"].delete_many({"project_id": project_id})
    rag.db["chat_sessions"].delete_many({"project_id": project_id})
    
    logger.info(f"[PROJECT] Deleted project {project_id} for user {user_id}")
    return {"message": "Project deleted successfully"}


# ────────────────────────────── Chat Sessions ──────────────────────────────
@app.post("/chat/save")
async def save_chat_message(
    user_id: str = Form(...),
    project_id: str = Form(...),
    role: str = Form(...),
    content: str = Form(...),
    timestamp: Optional[float] = Form(None)
):
    """Save a chat message to the session"""
    if role not in ["user", "assistant"]:
        raise HTTPException(400, detail="Invalid role")
    
    message = {
        "user_id": user_id,
        "project_id": project_id,
        "role": role,
        "content": content,
        "timestamp": timestamp or time.time(),
        "created_at": datetime.utcnow()
    }
    
    rag.db["chat_sessions"].insert_one(message)
    return {"message": "Chat message saved"}


@app.get("/chat/history")
async def get_chat_history(user_id: str, project_id: str, limit: int = 100):
    """Get chat history for a project"""
    messages = list(rag.db["chat_sessions"].find(
        {"user_id": user_id, "project_id": project_id},
        {"_id": 0}
    ).sort("timestamp", 1).limit(limit))
    return {"messages": messages}


# ────────────────────────────── Helpers ──────────────────────────────
def _infer_mime(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def _extract_pages(filename: str, file_bytes: bytes) -> List[Dict[str, Any]]:
    mime = _infer_mime(filename)
    if mime == "application/pdf":
        return parse_pdf_bytes(file_bytes)
    elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return parse_docx_bytes(file_bytes)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")


# ────────────────────────────── Routes ──────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index():
    index_path = os.path.join("static", "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>StudyBuddy RAG</h1><p>Static files not found.</p>")
    return FileResponse(index_path)


@app.post("/upload")
async def upload_files(
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Form(...),
    project_id: str = Form(...),
    files: List[UploadFile] = File(...),
):
    """
    Ingest many files: PDF/DOCX.
    Steps:
    1) Extract text & images
    2) Caption images (BLIP base, CPU ok)
    3) Merge captions into page text
    4) Chunk into semantic cards (topic_name, summary, content + metadata)
    5) Embed with all-MiniLM-L6-v2
    6) Store in MongoDB with per-user and per-project metadata
    7) Create a file-level summary
    """
    job_id = str(uuid.uuid4())

    # Read file bytes upfront to avoid reading from closed streams in background task
    preloaded_files = []
    for uf in files:
        raw = await uf.read()
        preloaded_files.append((uf.filename, raw))

    # Process files in background   
    async def _process():
        total_cards = 0
        file_summaries = []
        for fname, raw in preloaded_files:
            logger.info(f"[{job_id}] Parsing {fname} ({len(raw)} bytes)")

            # Extract pages from file
            pages = _extract_pages(fname, raw)

            # Caption images per page (if any)
            num_imgs = sum(len(p.get("images", [])) for p in pages)
            captions = []
            if num_imgs > 0:
                for p in pages:
                    caps = []
                    for im in p.get("images", []):
                        try:
                            cap = captioner.caption_image(im)
                            caps.append(cap)
                        except Exception as e:
                            logger.warning(f"Caption error: {e}")
                    captions.append(caps)
            else:
                captions = [[] for _ in pages]

            # Merge captions into text
            for idx, p in enumerate(pages):
                if captions[idx]:
                    p["text"] = (p.get("text", "") + "\n\n" + "\n".join([f"[Image] {c}" for c in captions[idx]])).strip()

            # Build cards
            cards = build_cards_from_pages(pages, filename=fname, user_id=user_id, project_id=project_id)
            logger.info(f"[{job_id}] Built {len(cards)} cards for {fname}")

            # Embed & store
            embeddings = embedder.embed([c["content"] for c in cards])
            for c, vec in zip(cards, embeddings):
                c["embedding"] = vec

            # Store cards in MongoDB on card
            rag.store_cards(cards)
            total_cards += len(cards)

            # File-level summary (cheap extractive)
            full_text = "\n\n".join(p.get("text", "") for p in pages)
            file_summary = cheap_summarize(full_text, max_sentences=6)
            rag.upsert_file_summary(user_id=user_id, project_id=project_id, filename=fname, summary=file_summary)
            file_summaries.append({"filename": fname, "summary": file_summary})

        logger.info(f"[{job_id}] Ingestion complete. Total cards: {total_cards}")

    # Kick off processing in background to keep UI responsive
    background_tasks.add_task(_process)
    return {"job_id": job_id, "status": "processing"}


@app.get("/cards")
def list_cards(user_id: str, project_id: str, filename: Optional[str] = None, limit: int = 50, skip: int = 0):
    return rag.list_cards(user_id=user_id, project_id=project_id, filename=filename, limit=limit, skip=skip)


@app.get("/file-summary")
def get_file_summary(user_id: str, project_id: str, filename: str):
    doc = rag.get_file_summary(user_id=user_id, project_id=project_id, filename=filename)
    if not doc:
        raise HTTPException(404, detail="No summary found for that file.")
    return {"filename": filename, "summary": doc.get("summary", "")}


@app.post("/chat")
async def chat(
    user_id: str = Form(...), 
    project_id: str = Form(...), 
    question: str = Form(...), 
    k: int = Form(6)
):
    """
    RAG chat that answers ONLY from uploaded materials.
    - Preload all filenames + summaries; use NVIDIA to classify file relevance to question (true/false)
    - Restrict vector search to relevant files (fall back to all if none)
    - Bring in recent chat memory: last 3 via NVIDIA relevance; remaining 17 via semantic search
    - After answering, summarize (q,a) via NVIDIA and store into LRU (last 20)
    """
    from memo.memory import MemoryLRU
    from memo.history import summarize_qa_with_nvidia, files_relevance, related_recent_and_semantic_context
    from utils.router import NVIDIA_SMALL  # reuse default name
    memory = app.state.__dict__.setdefault("memory_lru", MemoryLRU())

    # 0) If question is about a specific file, return the file summary
    m = re.search(r"what\s+is\s+the\s+(.+?\.(pdf|docx))\s+about\??", question, re.IGNORECASE)
    # If the question is about a specific file, return the file summary
    if m:
        fn = m.group(1)
        doc = rag.get_file_summary(user_id=user_id, project_id=project_id, filename=fn)
        if doc:
            return {"answer": doc.get("summary", ""), "sources": [{"filename": fn, "file_summary": True}]}
        else:
            return {"answer": "I couldn't find a summary for that file in your library.", "sources": []}
        
    # 1) Preload file list + summaries
    files_list = rag.list_files(user_id=user_id, project_id=project_id)  # [{filename, summary}]
    # Ask NVIDIA to mark relevance per file
    relevant_map = await files_relevance(question, files_list, nvidia_rotator)
    relevant_files = [fn for fn, ok in relevant_map.items() if ok]

    # 2) Memory context: recent 3 via NVIDIA, remaining 17 via semantic
    # recent 3 related (we do a simple include-all; NVIDIA will prune by "related" selection using the same mechanism as files_relevance but here handled in history)
    recent_related, semantic_related = await related_recent_and_semantic_context(user_id, question, memory, embedder)
    # For recent_related (empty placeholder), do NVIDIA pruning now:
    recent3 = memory.recent(user_id, 3)
    if recent3:
        sys = "Pick only items that directly relate to the new question. Output the selected items verbatim, no commentary. If none, output nothing."
        numbered = [{"id": i+1, "text": s} for i, s in enumerate(recent3)]
        user = f"Question: {question}\nCandidates:\n{json.dumps(numbered, ensure_ascii=False)}\nSelect any related items and output ONLY their 'text' values concatenated."
        try:
            from utils.rotator import robust_post_json
            key = nvidia_rotator.get_key()
            url = "https://integrate.api.nvidia.com/v1/chat/completions"
            payload = {
                "model": os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct"),
                "temperature": 0.0,
                "messages": [
                    {"role": "system", "content": sys},
                    {"role": "user", "content": user},
                ]
            }
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key or ''}"}
            data = await robust_post_json(url, headers, payload, nvidia_rotator)
            recent_related = data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"Recent-related NVIDIA error: {e}")
            recent_related = ""

    # 3) RAG vector search (restricted to relevant files if any)
    q_vec = embedder.embed([question])[0]
    hits = rag.vector_search(user_id=user_id, project_id=project_id, query_vector=q_vec, k=k, filenames=relevant_files if relevant_files else None)
    if not hits:
        return {
            "answer": "I don't know based on your uploaded materials. Try uploading more sources or rephrasing the question.",
            "sources": [],
            "relevant_files": relevant_files
        }
    # Compose context
    contexts = []
    sources_meta = []
    for h in hits:
        doc = h["doc"]
        score = h["score"]
        contexts.append(f"[{doc.get('topic_name','Topic')}] {trim_text(doc.get('content',''), 1200)}")
        sources_meta.append({
            "filename": doc.get("filename"),
            "topic_name": doc.get("topic_name"),
            "page_span": doc.get("page_span"),
            "score": float(score),
            "chunk_id": str(doc.get("_id", ""))
        })
    context_text = "\n\n---\n\n".join(contexts)

    # Add file-level summaries for relevant files
    file_summary_block = ""
    if relevant_files:
        fsum_map = {f["filename"]: f.get("summary","") for f in files_list}
        lines = [f"[{fn}] {fsum_map.get(fn, '')}" for fn in relevant_files]
        file_summary_block = "\n".join(lines)
        
    # Guardrail instruction to avoid hallucination
    system_prompt = (
        "You are a careful study assistant. Answer strictly using the given CONTEXT.\n"
        "If the answer isn't in the context, say 'I don't know based on the provided materials.'\n"
        "Write concise, clear explanations with citations like (source: filename, topic).\n"
    )

    # Add recent chat context and historical similarity context
    history_block = ""
    if recent_related or semantic_related:
        history_block = "RECENT_CHAT_CONTEXT:\n" + (recent_related or "") + ("\n\nHISTORICAL_SIMILARITY_CONTEXT:\n" + semantic_related if semantic_related else "")
    composed_context = ""
    if history_block:
        composed_context += history_block + "\n\n"
    if file_summary_block:
        composed_context += "FILE_SUMMARIES:\n" + file_summary_block + "\n\n"
    composed_context += "DOC_CONTEXT:\n" + context_text

    # Compose user prompt
    user_prompt = f"QUESTION:\n{question}\n\nCONTEXT:\n{composed_context}"
    # Choose model (cost-aware)
    selection = select_model(question=question, context=composed_context)
    logger.info(f"Model selection: {selection}")
    # Generate answer with model
    try:
        answer = await generate_answer_with_model(
            selection=selection,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator
        )
    except Exception as e:
        logger.error(f"LLM error: {e}")
        answer = "I had trouble contacting the language model provider just now. Please try again."
    # After answering: summarize QA and store in memory (LRU, last 20)
    try:
        qa_sum = await summarize_qa_with_nvidia(question, answer, nvidia_rotator)
        memory.add(user_id, qa_sum)
    except Exception as e:
        logger.warning(f"QA summarize/store failed: {e}")
    # Trim for logging
    logger.info("LLM answer (trimmed): %s", trim_text(answer, 200).replace("\n", " "))
    return {"answer": answer, "sources": sources_meta}


@app.get("/healthz")
def health():
    return {"ok": True}