# https://binkhoale1812-edsummariser.hf.space/
import os, io, re, uuid, json, time, logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import asyncio

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# MongoDB imports
from pymongo.errors import PyMongoError, ConnectionFailure, ServerSelectionTimeoutError

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

# ────────────────────────────── Response Models ──────────────────────────────
class ProjectResponse(BaseModel):
    project_id: str
    user_id: str
    name: str
    description: str
    created_at: str
    updated_at: str

class ProjectsListResponse(BaseModel):
    projects: List[ProjectResponse]

class ChatMessageResponse(BaseModel):
    user_id: str
    project_id: str
    role: str
    content: str
    timestamp: float
    created_at: str

class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageResponse]

class MessageResponse(BaseModel):
    message: str

class UploadResponse(BaseModel):
    job_id: str
    status: str
    total_files: Optional[int] = None

class FileSummaryResponse(BaseModel):
    filename: str
    summary: str

class ChatAnswerResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    relevant_files: Optional[List[str]] = None

class HealthResponse(BaseModel):
    ok: bool

class ReportResponse(BaseModel):
    filename: str
    report_markdown: str
    sources: List[Dict[str, Any]]

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

# In-memory job tracker (for progress queries)
app.state.jobs = {}


# ────────────────────────────── Global Clients ──────────────────────────────
# API rotators (round robin + auto failover on quota errors)
gemini_rotator = APIKeyRotator(prefix="GEMINI_API_", max_slots=5)
nvidia_rotator = APIKeyRotator(prefix="NVIDIA_API_", max_slots=5)

# Captioner + Embeddings (lazy init inside classes)
captioner = BlipCaptioner()
embedder = EmbeddingClient(model_name=os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))

# Mongo / RAG store
try:
    rag = RAGStore(mongo_uri=os.getenv("MONGO_URI"), db_name=os.getenv("MONGO_DB", "studybuddy"))
    # Test the connection
    rag.client.admin.command('ping')
    logger.info("[APP] MongoDB connection successful")
    ensure_indexes(rag)
    logger.info("[APP] MongoDB indexes ensured")
except Exception as e:
    logger.error(f"[APP] Failed to initialize MongoDB/RAG store: {str(e)}")
    logger.error(f"[APP] MONGO_URI: {os.getenv('MONGO_URI', 'Not set')}")
    logger.error(f"[APP] MONGO_DB: {os.getenv('MONGO_DB', 'studybuddy')}")
    # Create a dummy RAG store for now - this will cause errors but prevents the app from crashing
    rag = None


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
@app.post("/projects/create", response_model=ProjectResponse)
async def create_project(user_id: str = Form(...), name: str = Form(...), description: str = Form("")):
    """Create a new project for a user"""
    try:
        if not rag:
            raise HTTPException(500, detail="Database connection not available")
            
        if not name.strip():
            raise HTTPException(400, detail="Project name is required")
        
        if not user_id.strip():
            raise HTTPException(400, detail="User ID is required")
        
        project_id = str(uuid.uuid4())
        current_time = datetime.now(timezone.utc)
        
        project = {
            "project_id": project_id,
            "user_id": user_id,
            "name": name.strip(),
            "description": description.strip(),
            "created_at": current_time,
            "updated_at": current_time
        }
        
        logger.info(f"[PROJECT] Creating project {name} for user {user_id}")
        
        # Insert the project
        try:
            result = rag.db["projects"].insert_one(project)
            logger.info(f"[PROJECT] Created project {name} with ID {project_id}, MongoDB result: {result.inserted_id}")
        except PyMongoError as mongo_error:
            logger.error(f"[PROJECT] MongoDB error creating project: {str(mongo_error)}")
            raise HTTPException(500, detail=f"Database error: {str(mongo_error)}")
        except Exception as db_error:
            logger.error(f"[PROJECT] Database error creating project: {str(db_error)}")
            raise HTTPException(500, detail=f"Database error: {str(db_error)}")
        
        # Return a properly formatted response
        response = ProjectResponse(
            project_id=project_id,
            user_id=user_id,
            name=name.strip(),
            description=description.strip(),
            created_at=current_time.isoformat(),
            updated_at=current_time.isoformat()
        )
        
        logger.info(f"[PROJECT] Successfully created project {name} for user {user_id}")
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"[PROJECT] Error creating project: {str(e)}")
        logger.error(f"[PROJECT] Error type: {type(e)}")
        logger.error(f"[PROJECT] Error details: {e}")
        raise HTTPException(500, detail=f"Failed to create project: {str(e)}")


@app.get("/projects", response_model=ProjectsListResponse)
async def list_projects(user_id: str):
    """List all projects for a user"""
    projects_cursor = rag.db["projects"].find(
        {"user_id": user_id}
    ).sort("updated_at", -1)
    
    projects = []
    for project in projects_cursor:
        projects.append(ProjectResponse(
            project_id=project["project_id"],
            user_id=project["user_id"],
            name=project["name"],
            description=project.get("description", ""),
            created_at=project["created_at"].isoformat() if isinstance(project["created_at"], datetime) else str(project["created_at"]),
            updated_at=project["updated_at"].isoformat() if isinstance(project["updated_at"], datetime) else str(project["updated_at"])
        ))
    
    return ProjectsListResponse(projects=projects)


@app.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, user_id: str):
    """Get a specific project (with user ownership check)"""
    project = rag.db["projects"].find_one(
        {"project_id": project_id, "user_id": user_id}
    )
    if not project:
        raise HTTPException(404, detail="Project not found")
    
    return ProjectResponse(
        project_id=project["project_id"],
        user_id=project["user_id"],
        name=project["name"],
        description=project.get("description", ""),
        created_at=project["created_at"].isoformat() if isinstance(project["created_at"], datetime) else str(project["created_at"]),
        updated_at=project["updated_at"].isoformat() if isinstance(project["updated_at"], datetime) else str(project["updated_at"])
    )


@app.delete("/projects/{project_id}", response_model=MessageResponse)
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
    return MessageResponse(message="Project deleted successfully")


# ────────────────────────────── Chat Sessions ──────────────────────────────
@app.post("/chat/save", response_model=MessageResponse)
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
        "created_at": datetime.now(timezone.utc)
    }
    
    rag.db["chat_sessions"].insert_one(message)
    return MessageResponse(message="Chat message saved")


@app.get("/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(user_id: str, project_id: str, limit: int = 100):
    """Get chat history for a project"""
    messages_cursor = rag.db["chat_sessions"].find(
        {"user_id": user_id, "project_id": project_id}
    ).sort("timestamp", 1).limit(limit)
    
    messages = []
    for message in messages_cursor:
        messages.append(ChatMessageResponse(
            user_id=message["user_id"],
            project_id=message["project_id"],
            role=message["role"],
            content=message["content"],
            timestamp=message["timestamp"],
            created_at=message["created_at"].isoformat() if isinstance(message["created_at"], datetime) else str(message["created_at"])
        ))
    
    return ChatHistoryResponse(messages=messages)


@app.delete("/chat/history", response_model=MessageResponse)
async def delete_chat_history(user_id: str, project_id: str):
    try:
        rag.db["chat_sessions"].delete_many({"user_id": user_id, "project_id": project_id})
        logger.info(f"[CHAT] Cleared history for user {user_id} project {project_id}")
        # Also clear in-memory LRU for this user to avoid stale context
        try:
            from memo.memory import MemoryLRU
            memory = app.state.__dict__.setdefault("memory_lru", MemoryLRU())
            memory.clear(user_id)
            logger.info(f"[CHAT] Cleared in-memory LRU for user {user_id}")
        except Exception as me:
            logger.warning(f"[CHAT] Failed to clear in-memory LRU for user {user_id}: {me}")
        return MessageResponse(message="Chat history cleared")
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to clear chat history: {str(e)}")


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
        return HTMLResponse("<h1>StudyBuddy</h1><p>Static files not found.</p>")
    return FileResponse(index_path)


@app.post("/upload", response_model=UploadResponse)
async def upload_files(
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Form(...),
    project_id: str = Form(...),
    files: List[UploadFile] = File(...),
    replace_filenames: Optional[str] = Form(None),  # JSON array of filenames to replace
    rename_map: Optional[str] = Form(None),         # JSON object {original: newname}
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

    # Basic upload policy limits
    max_files = int(os.getenv("MAX_FILES_PER_UPLOAD", "15"))
    max_mb = int(os.getenv("MAX_FILE_MB", "50"))
    if len(files) > max_files:
        raise HTTPException(400, detail=f"Too many files. Max {max_files} allowed per upload.")

    # Parse replace/rename directives
    replace_set = set()
    try:
        if replace_filenames:
            replace_set = set(json.loads(replace_filenames))
    except Exception:
        pass
    rename_dict: Dict[str, str] = {}
    try:
        if rename_map:
            rename_dict = json.loads(rename_map)
    except Exception:
        pass

    preloaded_files = []
    for uf in files:
        raw = await uf.read()
        if len(raw) > max_mb * 1024 * 1024:
            raise HTTPException(400, detail=f"{uf.filename} exceeds {max_mb} MB limit")
        # Apply rename if present
        eff_name = rename_dict.get(uf.filename, uf.filename)
        preloaded_files.append((eff_name, raw))

    # Initialize job status
    app.state.jobs[job_id] = {
        "created_at": time.time(),
        "total": len(preloaded_files),
        "completed": 0,
        "status": "processing",
        "last_error": None,
    }

    # Single background task: process files sequentially with isolation
    async def _process_all():
        for idx, (fname, raw) in enumerate(preloaded_files, start=1):
            try:
                # If instructed to replace this filename, remove previous data first
                if fname in replace_set:
                    try:
                        rag.db["chunks"].delete_many({"user_id": user_id, "project_id": project_id, "filename": fname})
                        rag.db["files"].delete_many({"user_id": user_id, "project_id": project_id, "filename": fname})
                        logger.info(f"[{job_id}] Replaced prior data for {fname}")
                    except Exception as de:
                        logger.warning(f"[{job_id}] Replace delete failed for {fname}: {de}")
                logger.info(f"[{job_id}] ({idx}/{len(preloaded_files)}) Parsing {fname} ({len(raw)} bytes)")

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
                                logger.warning(f"[{job_id}] Caption error in {fname}: {e}")
                        captions.append(caps)
                else:
                    captions = [[] for _ in pages]

                # Merge captions into text
                for p, caps in zip(pages, captions):
                    if caps:
                        p["text"] = (p.get("text", "") + "\n\n" + "\n".join([f"[Image] {c}" for c in caps])).strip()

                # Build cards
                cards = await build_cards_from_pages(pages, filename=fname, user_id=user_id, project_id=project_id)
                logger.info(f"[{job_id}] Built {len(cards)} cards for {fname}")

                # Embed & store
                embeddings = embedder.embed([c["content"] for c in cards])
                for c, vec in zip(cards, embeddings):
                    c["embedding"] = vec

                rag.store_cards(cards)

                # File-level summary (cheap extractive)
                full_text = "\n\n".join(p.get("text", "") for p in pages)
                file_summary = await cheap_summarize(full_text, max_sentences=6)
                rag.upsert_file_summary(user_id=user_id, project_id=project_id, filename=fname, summary=file_summary)
                logger.info(f"[{job_id}] Completed {fname}")
                # Update job progress
                job = app.state.jobs.get(job_id)
                if job:
                    job["completed"] = idx
                    job["status"] = "processing" if idx < job.get("total", 0) else "completed"
            except Exception as e:
                logger.error(f"[{job_id}] Failed processing {fname}: {e}")
                job = app.state.jobs.get(job_id)
                if job:
                    job["last_error"] = str(e)
                    job["completed"] = idx  # count as completed attempt
            finally:
                # Yield control between files to keep loop responsive
                await asyncio.sleep(0)

        logger.info(f"[{job_id}] Ingestion complete for {len(preloaded_files)} files")
        # Finalize job status
        job = app.state.jobs.get(job_id)
        if job:
            job["status"] = "completed"

    background_tasks.add_task(_process_all)
    return UploadResponse(job_id=job_id, status="processing", total_files=len(preloaded_files))


@app.get("/upload/status")
async def upload_status(job_id: str):
    job = app.state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, detail="Job not found")
    percent = 0
    if job.get("total"):
        percent = int(round((job.get("completed", 0) / job.get("total", 1)) * 100))
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "completed": job.get("completed"),
        "total": job.get("total"),
        "percent": percent,
        "last_error": job.get("last_error"),
        "created_at": job.get("created_at"),
    }


@app.get("/files")
async def list_project_files(user_id: str, project_id: str):
    """Return stored filenames and summaries for a project."""
    files = rag.list_files(user_id=user_id, project_id=project_id)
    # Ensure filenames list
    filenames = [f.get("filename") for f in files if f.get("filename")]
    return {"files": files, "filenames": filenames}


@app.delete("/files", response_model=MessageResponse)
async def delete_file(user_id: str, project_id: str, filename: str):
    """Delete a file summary and associated chunks for a project."""
    try:
        rag.db["files"].delete_many({"user_id": user_id, "project_id": project_id, "filename": filename})
        rag.db["chunks"].delete_many({"user_id": user_id, "project_id": project_id, "filename": filename})
        logger.info(f"[FILES] Deleted file {filename} for user {user_id} project {project_id}")
        return MessageResponse(message="File deleted")
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to delete file: {str(e)}")


@app.get("/cards")
def list_cards(user_id: str, project_id: str, filename: Optional[str] = None, limit: int = 50, skip: int = 0):
    """List cards for a project"""
    cards = rag.list_cards(user_id=user_id, project_id=project_id, filename=filename, limit=limit, skip=skip)
    # Ensure all cards are JSON serializable
    serializable_cards = []
    for card in cards:
        serializable_card = {}
        for key, value in card.items():
            if key == '_id':
                serializable_card[key] = str(value)  # Convert ObjectId to string
            elif isinstance(value, datetime):
                serializable_card[key] = value.isoformat()  # Convert datetime to ISO string
            else:
                serializable_card[key] = value
        serializable_cards.append(serializable_card)
    # Sort cards by topic_name
    return {"cards": serializable_cards}


@app.get("/file-summary", response_model=FileSummaryResponse)
def get_file_summary(user_id: str, project_id: str, filename: str):
    doc = rag.get_file_summary(user_id=user_id, project_id=project_id, filename=filename)
    if not doc:
        raise HTTPException(404, detail="No summary found for that file.")
    return FileSummaryResponse(filename=filename, summary=doc.get("summary", ""))


@app.post("/report", response_model=ReportResponse)
async def generate_report(
    user_id: str = Form(...),
    project_id: str = Form(...),
    filename: str = Form(...),
    outline_words: int = Form(200),
    report_words: int = Form(1200),
    instructions: str = Form("")
):
    """
    Generate a Markdown report for a single document using a lightweight CoT:
    1) Gemini Flash: create a structured outline based on file summary + top chunks
    2) Gemini Pro: expand into a full report with citations
    """
    logger.info("[REPORT] User Q/report: %s", trim_text(instructions, 15).replace("\n", " "))
    # Validate file exists
    files_list = rag.list_files(user_id=user_id, project_id=project_id)
    filenames_ci = {f.get("filename", "").lower(): f.get("filename") for f in files_list}
    eff_name = filenames_ci.get(filename.lower(), filename)
    doc_sum = rag.get_file_summary(user_id=user_id, project_id=project_id, filename=eff_name)
    if not doc_sum:
        raise HTTPException(404, detail="No summary found for that file.")

    # Retrieve top-k chunks for this file
    q_vec = embedder.embed([f"Comprehensive report for {eff_name}"])[0]
    hits = rag.vector_search(user_id=user_id, project_id=project_id, query_vector=q_vec, k=8, filenames=[eff_name])
    if not hits:
        # Fall back to summary-only report
        hits = []

    # Build context
    contexts = []
    sources_meta = []
    for h in hits:
        doc = h["doc"]
        contexts.append(f"[{doc.get('topic_name','Topic')}] {trim_text(doc.get('content',''), 2000)}")
        sources_meta.append({
            "filename": doc.get("filename"),
            "topic_name": doc.get("topic_name"),
            "page_span": doc.get("page_span"),
            "score": float(h.get("score", 0.0)),
            "chunk_id": str(doc.get("_id", ""))
        })
    context_text = "\n\n---\n\n".join(contexts) if contexts else ""
    file_summary = doc_sum.get("summary", "")

    # Chain-of-thought style two-step with Gemini
    from utils.router import GEMINI_MED, GEMINI_PRO
    
    # Step 1: Content filtering and relevance assessment based on user instructions
    if instructions.strip():
        filter_sys = (
            "You are an expert content analyst. Given the user's specific instructions and the document content, "
            "identify which sections/chunks are MOST relevant to their request. "
            "Return a JSON object with this structure: {\"relevant_chunks\": [\"chunk_id_1\", \"chunk_id_2\"], \"focus_areas\": [\"key topic 1\", \"key topic 2\"]}"
        )
        filter_user = f"USER_INSTRUCTIONS: {instructions}\n\nDOCUMENT_SUMMARY: {file_summary}\n\nAVAILABLE_CHUNKS:\n{context_text}\n\nIdentify only the chunks that directly address the user's specific request."
        
        try:
            selection_filter = {"provider": "gemini", "model": os.getenv("GEMINI_MED", "gemini-2.5-flash")}
            filter_response = await generate_answer_with_model(selection_filter, filter_sys, filter_user, gemini_rotator, nvidia_rotator)
            # Try to parse the filter response to get relevant chunks
            import json
            try:
                filter_data = json.loads(filter_response)
                relevant_chunk_ids = filter_data.get("relevant_chunks", [])
                focus_areas = filter_data.get("focus_areas", [])
                logger.info(f"[REPORT] Content filtering identified {len(relevant_chunk_ids)} relevant chunks and focus areas: {focus_areas}")
                # Filter context to only relevant chunks
                if relevant_chunk_ids and hits:
                    filtered_hits = [h for h in hits if str(h["doc"].get("_id", "")) in relevant_chunk_ids]
                    if filtered_hits:
                        hits = filtered_hits
                        logger.info(f"[REPORT] Filtered context from {len(hits)} chunks to {len(filtered_hits)} relevant chunks")
            except json.JSONDecodeError:
                logger.warning(f"[REPORT] Could not parse filter response, using all chunks: {filter_response}")
        except Exception as e:
            logger.warning(f"[REPORT] Content filtering failed: {e}")
    
    # Step 2: Create focused outline based on user instructions
    sys_outline = (
        "You are an expert technical writer. Create a focused, hierarchical outline for a report based on the user's specific instructions and the MATERIALS. "
        "The outline should directly address what the user asked for. Output as Markdown bullet list only. Keep it within about {} words."
    ).format(max(100, outline_words))
    
    instruction_context = f"USER_REQUEST: {instructions}\n\n" if instructions.strip() else ""
    user_outline = f"{instruction_context}MATERIALS:\n\n[FILE_SUMMARY from {eff_name}]\n{file_summary}\n\n[DOC_CONTEXT]\n{context_text}"

    try:
        # Step 1: Outline with Flash/Med
        selection_outline = {"provider": "gemini", "model": os.getenv("GEMINI_MED", "gemini-2.5-flash")}
        outline_md = await generate_answer_with_model(selection_outline, sys_outline, user_outline, gemini_rotator, nvidia_rotator)
    except Exception as e:
        logger.warning(f"Report outline failed: {e}")
        outline_md = "# Report Outline\n\n- Introduction\n- Key Topics\n- Conclusion"

    # Step 3: Generate focused report based on user instructions and filtered content
    instruction_focus = f"FOCUS ON: {instructions}\n\n" if instructions.strip() else ""
    sys_report = (
        "You are an expert report writer. Write a focused, comprehensive Markdown report that directly addresses the user's specific request. "
        "Using the OUTLINE and MATERIALS:\n"
        "- Structure the report to answer exactly what the user asked for\n"
        "- Use clear section headings\n"
        "- Keep content factual and grounded in the provided materials\n"
        f"- Include brief citations like (source: {eff_name}, topic) - use the actual filename provided\n"
        "- If the user asked for a specific section/topic, focus heavily on that\n"
        f"- Target length ~{max(600, report_words)} words\n"
        "- Ensure the report directly fulfills the user's request"
    )
    user_report = f"{instruction_focus}OUTLINE:\n{outline_md}\n\nMATERIALS:\n[FILE_SUMMARY from {eff_name}]\n{file_summary}\n\n[DOC_CONTEXT]\n{context_text}"

    try:
        selection_report = {"provider": "gemini", "model": os.getenv("GEMINI_PRO", "gemini-2.5-pro")}
        report_md = await generate_answer_with_model(selection_report, sys_report, user_report, gemini_rotator, nvidia_rotator)
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        report_md = outline_md + "\n\n" + file_summary

    return ReportResponse(filename=eff_name, report_markdown=report_md, sources=sources_meta)


@app.post("/chat", response_model=ChatAnswerResponse)
async def chat(
    user_id: str = Form(...), 
    project_id: str = Form(...), 
    question: str = Form(...), 
    k: int = Form(6)
):
    # Add timeout protection to prevent hanging
    import asyncio
    try:
        return await asyncio.wait_for(_chat_impl(user_id, project_id, question, k), timeout=120.0)
    except asyncio.TimeoutError:
        logger.error("[CHAT] Chat request timed out after 120 seconds")
        return ChatAnswerResponse(
            answer="Sorry, the request took too long to process. Please try again with a simpler question.",
            sources=[],
            relevant_files=[]
        )

async def _chat_impl(
    user_id: str, 
    project_id: str, 
    question: str, 
    k: int
):
    """
    RAG chat that answers ONLY from uploaded materials.
    - Preload all filenames + summaries; use NVIDIA to classify file relevance to question (true/false)
    - Restrict vector search to relevant files (fall back to all if none)
    - Bring in recent chat memory: last 3 via NVIDIA relevance; remaining 17 via semantic search
    - After answering, summarize (q,a) via NVIDIA and store into LRU (last 20)
    """
    import sys
    from memo.memory import MemoryLRU
    from memo.history import summarize_qa_with_nvidia, files_relevance, related_recent_and_semantic_context
    from utils.router import NVIDIA_SMALL  # reuse default name
    memory = app.state.__dict__.setdefault("memory_lru", MemoryLRU())
    logger.info("[CHAT] User Q/chat: %s", trim_text(question, 15).replace("\n", " "))

    # 0) Detect any filenames mentioned in the question (e.g., JADE.pdf)
    #    Supports .pdf, .docx, and .doc for detection purposes
    # Only capture contiguous tokens ending with extension (no spaces) to avoid swallowing prompt text
    mentioned = set([m.group(0).strip() for m in re.finditer(r"\b[^\s/\\]+?\.(?:pdf|docx|doc)\b", question, re.IGNORECASE)])
    if mentioned:
        logger.info(f"[CHAT] Detected mentioned filenames in question: {list(mentioned)}")

    # 0a) If the question explicitly asks for a summary/about of a single mentioned file, return its summary directly
    if mentioned and (re.search(r"\b(summary|summarize|about|overview)\b", question, re.IGNORECASE)):
        # Prefer direct summary when exactly one file is referenced
        if len(mentioned) == 1:
            fn = next(iter(mentioned))
            doc = rag.get_file_summary(user_id=user_id, project_id=project_id, filename=fn)
            if doc:
                return ChatAnswerResponse(
                    answer=doc.get("summary", ""),
                    sources=[{"filename": fn, "file_summary": True}]
                )
            # If not found with the same casing, try case-insensitive match against stored filenames
            files_ci = rag.list_files(user_id=user_id, project_id=project_id)
            match = next((f["filename"] for f in files_ci if f.get("filename", "").lower() == fn.lower()), None)
            if match:
                doc = rag.get_file_summary(user_id=user_id, project_id=project_id, filename=match)
                if doc:
                    return ChatAnswerResponse(
                        answer=doc.get("summary", ""),
                        sources=[{"filename": match, "file_summary": True}]
                    )
        # If multiple files are referenced with summary intent, proceed to relevance flow below
        
    # 1) Preload file list + summaries
    files_list = rag.list_files(user_id=user_id, project_id=project_id)  # [{filename, summary}]

    # 1a) Normalize mentioned filenames against the user's library (case-insensitive)
    filenames_ci_map = {f.get("filename", "").lower(): f.get("filename") for f in files_list if f.get("filename")}
    mentioned_normalized = []
    for mfn in mentioned:
        key = mfn.lower()
        if key in filenames_ci_map:
            mentioned_normalized.append(filenames_ci_map[key])
    if mentioned and not mentioned_normalized and files_list:
        # Try looser match: contained filenames ignoring spaces
        norm = {f.get("filename", "").lower().replace(" ", ""): f.get("filename") for f in files_list if f.get("filename")}
        for mfn in mentioned:
            key2 = mfn.lower().replace(" ", "")
            if key2 in norm:
                mentioned_normalized.append(norm[key2])
    if mentioned_normalized:
        logger.info(f"[CHAT] Normalized mentions to stored filenames: {mentioned_normalized}")

    # 1b) Ask NVIDIA to mark relevance per file
    try:
        relevant_map = await files_relevance(question, files_list, nvidia_rotator)
        relevant_files = [fn for fn, ok in relevant_map.items() if ok]
        logger.info(f"[CHAT] NVIDIA relevant files: {relevant_files}")
    except Exception as e:
        logger.warning(f"[CHAT] NVIDIA relevance failed, defaulting to all files: {e}")
        relevant_files = [f.get("filename") for f in files_list if f.get("filename")]

    # 1c) Ensure any explicitly mentioned files in the question are included
    #     This safeguards against model misclassification
    if mentioned_normalized:
        extra = [fn for fn in mentioned_normalized if fn not in relevant_files]
        relevant_files.extend(extra)
        if extra:
            logger.info(f"[CHAT] Forced-include mentioned files into relevance: {extra}")

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
    logger.info(f"[CHAT] Starting vector search with relevant_files={relevant_files}")
    q_vec = embedder.embed([question])[0]
    hits = rag.vector_search(
        user_id=user_id,
        project_id=project_id,
        query_vector=q_vec,
        k=k,
        filenames=relevant_files if relevant_files else None
    )
    logger.info(f"[CHAT] Vector search returned {len(hits) if hits else 0} hits")
    if not hits:
        logger.info(f"[CHAT] No hits with relevance filter. relevant_files={relevant_files}")
        # Retry 1: if we have explicit mentions, try restricting only to them
        if mentioned_normalized:
            hits = rag.vector_search(
                user_id=user_id,
                project_id=project_id,
                query_vector=q_vec,
                k=k,
                filenames=mentioned_normalized
            )
            logger.info(f"[CHAT] Retry with mentioned files only → hits={len(hits) if hits else 0}")
        # Retry 2: if still empty, try without any filename restriction
        if not hits:
            hits = rag.vector_search(
                user_id=user_id,
                project_id=project_id,
                query_vector=q_vec,
                k=k,
                filenames=None
            )
            logger.info(f"[CHAT] Retry with all files → hits={len(hits) if hits else 0}")
        # If still no hits, and we have mentioned files, try returning their summaries if present
        if not hits and mentioned_normalized:
            fsum_map = {f["filename"]: f.get("summary", "") for f in files_list}
            summaries = [fsum_map.get(fn, "") for fn in mentioned_normalized]
            summaries = [s for s in summaries if s]
            if summaries:
                answer = ("\n\n---\n\n").join(summaries)
                return ChatAnswerResponse(
                    answer=answer,
                    sources=[{"filename": fn, "file_summary": True} for fn in mentioned_normalized],
                    relevant_files=mentioned_normalized
                )
        if not hits:
            # Last resort: use summaries from relevant files if we didn't have explicit mentions normalized
            candidates = mentioned_normalized or relevant_files or []
            if candidates:
                fsum_map = {f["filename"]: f.get("summary", "") for f in files_list}
                summaries = [fsum_map.get(fn, "") for fn in candidates]
                summaries = [s for s in summaries if s]
                if summaries:
                    answer = ("\n\n---\n\n").join(summaries)
                    logger.info(f"[CHAT] Falling back to file-level summaries for: {candidates}")
                    return ChatAnswerResponse(
                        answer=answer,
                        sources=[{"filename": fn, "file_summary": True} for fn in candidates],
                        relevant_files=candidates
                    )
            return ChatAnswerResponse(
                answer="I don't know based on your uploaded materials. Try uploading more sources or rephrasing the question.",
                sources=[],
                relevant_files=relevant_files or mentioned_normalized
            )
        # If we get here, we have hits, so continue with normal flow
    # Compose context
    contexts = []
    sources_meta = []
    for h in hits:
        doc = h["doc"]
        score = h["score"]
        contexts.append(f"[{doc.get('topic_name','Topic')}] {trim_text(doc.get('content',''), 2000)}")
        sources_meta.append({
            "filename": doc.get("filename"),
            "topic_name": doc.get("topic_name"),
            "page_span": doc.get("page_span"),
            "score": float(score),
            "chunk_id": str(doc.get("_id", ""))  # Convert ObjectId to string
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
        "Write concise, clear explanations with citations like (source: actual_filename, topic).\n"
        "Use the exact filename as provided in the context, not placeholders.\n"
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
    logger.info(f"[CHAT] Generating answer with {selection['provider']} {selection['model']}")
    try:
        answer = await generate_answer_with_model(
            selection=selection,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini_rotator=gemini_rotator,
            nvidia_rotator=nvidia_rotator
        )
        logger.info(f"[CHAT] Answer generated successfully, length: {len(answer)}")
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
    return ChatAnswerResponse(answer=answer, sources=sources_meta, relevant_files=relevant_files)


@app.get("/healthz", response_model=HealthResponse)
def health():
    return HealthResponse(ok=True)


@app.get("/test-db")
async def test_database():
    """Test database connection and basic operations"""
    try:
        if not rag:
            return {
                "status": "error",
                "message": "RAG store not initialized",
                "error_type": "RAGStoreNotInitialized"
            }
            
        # Test basic connection
        rag.client.admin.command('ping')
        
        # Test basic insert/query
        test_collection = rag.db["test_collection"]
        test_doc = {"test": True, "timestamp": datetime.now(timezone.utc)}
        result = test_collection.insert_one(test_doc)
        
        # Test query
        found = test_collection.find_one({"_id": result.inserted_id})
        
        # Clean up
        test_collection.delete_one({"_id": result.inserted_id})
        
        return {
            "status": "success",
            "message": "Database connection and operations working correctly",
            "test_id": str(result.inserted_id),
            "found_doc": str(found["_id"]) if found else None
        }
        
    except Exception as e:
        logger.error(f"[TEST-DB] Database test failed: {str(e)}")
        return {
            "status": "error",
            "message": f"Database test failed: {str(e)}",
            "error_type": str(type(e))
        }


@app.get("/rag-status")
async def rag_status():
    """Check the status of the RAG store"""
    if not rag:
        return {
            "status": "error",
            "message": "RAG store not initialized",
            "rag_available": False
        }
    
    try:
        # Test connection
        rag.client.admin.command('ping')
        return {
            "status": "success",
            "message": "RAG store is available and connected",
            "rag_available": True,
            "database": rag.db.name,
            "collections": {
                "chunks": rag.chunks.name,
                "files": rag.files.name
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"RAG store connection failed: {str(e)}",
            "rag_available": False,
            "error": str(e)
        }

# Local dev
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)