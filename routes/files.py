# routes/files.py
import os, io, json, uuid, time, asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import UploadFile, File, Form, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse

from helpers.setup import app, rag, logger, embedder, captioner
from helpers.models import UploadResponse, FileSummaryResponse, MessageResponse
from helpers.pages import _extract_pages

from utils.service.summarizer import cheap_summarize
from utils.ingestion.chunker import build_cards_from_pages
from utils.service.common import trim_text


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
    replace_filenames: Optional[str] = Form(None),
    rename_map: Optional[str] = Form(None),
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

    max_files = int(os.getenv("MAX_FILES_PER_UPLOAD", "15"))
    max_mb = int(os.getenv("MAX_FILE_MB", "50"))
    if len(files) > max_files:
        raise HTTPException(400, detail=f"Too many files. Max {max_files} allowed per upload.")

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
        eff_name = rename_dict.get(uf.filename, uf.filename)
        preloaded_files.append((eff_name, raw))

    app.state.jobs[job_id] = {
        "created_at": time.time(),
        "total": len(preloaded_files),
        "completed": 0,
        "status": "processing",
        "last_error": None,
    }

    async def _process_all():
        for idx, (fname, raw) in enumerate(preloaded_files, start=1):
            try:
                if fname in replace_set:
                    try:
                        rag.db["chunks"].delete_many({"user_id": user_id, "project_id": project_id, "filename": fname})
                        rag.db["files"].delete_many({"user_id": user_id, "project_id": project_id, "filename": fname})
                        logger.info(f"[{job_id}] Replaced prior data for {fname}")
                    except Exception as de:
                        logger.warning(f"[{job_id}] Replace delete failed for {fname}: {de}")
                logger.info(f"[{job_id}] ({idx}/{len(preloaded_files)}) Parsing {fname} ({len(raw)} bytes)")

                pages = _extract_pages(fname, raw)

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

                for p, caps in zip(pages, captions):
                    if caps:
                        p["text"] = (p.get("text", "") + "\n\n" + "\n".join([f"[Image] {c}" for c in caps])).strip()

                cards = await build_cards_from_pages(pages, filename=fname, user_id=user_id, project_id=project_id)
                logger.info(f"[{job_id}] Built {len(cards)} cards for {fname}")

                embeddings = embedder.embed([c["content"] for c in cards])
                for c, vec in zip(cards, embeddings):
                    c["embedding"] = vec

                rag.store_cards(cards)

                full_text = "\n\n".join(p.get("text", "") for p in pages)
                file_summary = await cheap_summarize(full_text, max_sentences=6)
                rag.upsert_file_summary(user_id=user_id, project_id=project_id, filename=fname, summary=file_summary)
                logger.info(f"[{job_id}] Completed {fname}")
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

        logger.info(f"[{job_id}] Ingestion complete for {len(preloaded_files)} files")
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


