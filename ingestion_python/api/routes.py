"""
API routes for the ingestion pipeline
"""

import os
import asyncio
import uuid
import time
import json
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Form, File, UploadFile, HTTPException, BackgroundTasks, Request

from api.models import UploadResponse, JobStatusResponse, HealthResponse, FilesListResponse, ChunksResponse
from services.ingestion_service import IngestionService
from services.maverick_captioner import _normalize_caption
from utils.logger import get_logger

logger = get_logger("INGESTION_ROUTES", __name__)

# Create router
router = APIRouter()

# Global services (will be injected)
rag = None
embedder = None
captioner = None
ingestion_service = None

def initialize_services(rag_store, embedder_client, captioner_client):
    """Initialize services"""
    global rag, embedder, captioner, ingestion_service
    rag = rag_store
    embedder = embedder_client
    captioner = captioner_client
    ingestion_service = IngestionService(rag_store, embedder_client, captioner_client)

@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    mongodb_connected = rag is not None
    return HealthResponse(
        ok=mongodb_connected,
        mongodb_connected=mongodb_connected
    )

@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Form(...),
    project_id: str = Form(...),
    files: List[UploadFile] = File(...),
    replace_filenames: Optional[str] = Form(None),
    rename_map: Optional[str] = Form(None),
):
    """
    Upload and process files
    
    This endpoint mirrors the main system's upload functionality exactly.
    """
    if not rag:
        raise HTTPException(500, detail="MongoDB connection not available")
    
    job_id = str(uuid.uuid4())
    
    # File limits (same as main system)
    max_files = int(os.getenv("MAX_FILES_PER_UPLOAD", "15"))
    max_mb = int(os.getenv("MAX_FILE_MB", "50"))
    
    if len(files) > max_files:
        raise HTTPException(400, detail=f"Too many files. Max {max_files} allowed per upload.")
    
    # Parse replace/rename directives (same as main system)
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
    
    # Preload files (same as main system)
    preloaded_files = []
    for uf in files:
        raw = await uf.read()
        if len(raw) > max_mb * 1024 * 1024:
            raise HTTPException(400, detail=f"{uf.filename} exceeds {max_mb} MB limit")
        eff_name = rename_dict.get(uf.filename, uf.filename)
        preloaded_files.append((eff_name, raw))
    
    # Initialize job status (same as main system)
    from app import app
    app.state.jobs[job_id] = {
        "created_at": time.time(),
        "total": len(preloaded_files),
        "completed": 0,
        "status": "processing",
        "last_error": None,
    }
    
    # Background processing (mirrors main system exactly)
    async def _process_all():
        for idx, (fname, raw) in enumerate(preloaded_files, start=1):
            try:
                # Handle file replacement (same as main system)
                if fname in replace_set:
                    try:
                        rag.db["chunks"].delete_many({"user_id": user_id, "project_id": project_id, "filename": fname})
                        rag.db["files"].delete_many({"user_id": user_id, "project_id": project_id, "filename": fname})
                        logger.info(f"[{job_id}] Replaced prior data for {fname}")
                    except Exception as de:
                        logger.warning(f"[{job_id}] Replace delete failed for {fname}: {de}")
                
                logger.info(f"[{job_id}] ({idx}/{len(preloaded_files)}) Parsing {fname} ({len(raw)} bytes)")
                
                # Extract pages (same as main system)
                from helpers.pages import _extract_pages
                pages = _extract_pages(fname, raw)
                
                # Process images with captions (same as main system)
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
                
                # Merge captions into text (same as main system)
                for p, caps in zip(pages, captions):
                    if caps:
                        normalized = [ _normalize_caption(c) for c in caps if c ]
                        if normalized:
                            p["text"] = (p.get("text", "") + "\n\n" + "\n".join([f"[Image] {c}" for c in normalized])).strip()
                
                # Build cards (same as main system)
                from utils.ingestion.chunker import build_cards_from_pages
                cards = await build_cards_from_pages(pages, filename=fname, user_id=user_id, project_id=project_id)
                logger.info(f"[{job_id}] Built {len(cards)} cards for {fname}")
                
                # Generate embeddings (same as main system)
                embeddings = embedder.embed([c["content"] for c in cards])
                for c, vec in zip(cards, embeddings):
                    c["embedding"] = vec
                
                # Store in MongoDB (same as main system)
                rag.store_cards(cards)
                
                # Create file summary (same as main system)
                from utils.service.summarizer import cheap_summarize
                full_text = "\n\n".join(p.get("text", "") for p in pages)
                file_summary = await cheap_summarize(full_text, max_sentences=6)
                rag.upsert_file_summary(user_id=user_id, project_id=project_id, filename=fname, summary=file_summary)
                
                logger.info(f"[{job_id}] Completed {fname}")
                
                # Update job progress (same as main system)
                job = app.state.jobs.get(job_id)
                if job:
                    job["completed"] = idx
                    job["status"] = "processing" if idx < job.get("total", 0) else "completed"
                    
            except Exception as e:
                logger.error(f"[{job_id}] Failed processing {fname}: {e}")
                job = app.state.jobs.get(job_id)
                if job:
                    job["last_error"] = str(e)
                    job["completed"] = idx
            finally:
                await asyncio.sleep(0)
        
        # Finalize job (same as main system)
        logger.info(f"[{job_id}] Ingestion complete for {len(preloaded_files)} files")
        job = app.state.jobs.get(job_id)
        if job:
            job["status"] = "completed"
    
    background_tasks.add_task(_process_all)
    
    return UploadResponse(
        job_id=job_id,
        status="processing",
        total_files=len(preloaded_files)
    )

@router.get("/upload/status", response_model=JobStatusResponse)
async def upload_status(job_id: str):
    """Get upload job status"""
    from app import app
    job = app.state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, detail="Job not found")
    
    progress = (job["completed"] / job["total"]) * 100 if job["total"] > 0 else 0
    
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        total=job["total"],
        completed=job["completed"],
        progress=progress,
        last_error=job.get("last_error"),
        created_at=job["created_at"]
    )

@router.get("/files", response_model=FilesListResponse)
async def list_files(user_id: str, project_id: str):
    """List files for a project (compatible with main system)"""
    if not rag:
        raise HTTPException(500, detail="MongoDB connection not available")
    
    files = rag.list_files(user_id, project_id)
    return FilesListResponse(
        files=[{"filename": f["filename"], "summary": f["summary"]} for f in files],
        filenames=[f["filename"] for f in files]
    )

@router.get("/files/chunks", response_model=ChunksResponse)
async def get_file_chunks(user_id: str, project_id: str, filename: str, limit: int = 20):
    """Get chunks for a specific file (compatible with main system)"""
    if not rag:
        raise HTTPException(500, detail="MongoDB connection not available")
    
    chunks = rag.get_file_chunks(user_id, project_id, filename, limit)
    return ChunksResponse(chunks=chunks)
