"""
Ingestion service for processing files and storing them in MongoDB
"""

import asyncio
import uuid
import time
import json
from typing import List, Dict, Any, Optional
from utils.logger import get_logger
from utils.rag.rag import RAGStore
from utils.embedding import RemoteEmbeddingClient
from services.maverick_captioner import NvidiaMaverickCaptioner, _normalize_caption
from utils.ingestion.chunker import build_cards_from_pages
from utils.service.summarizer import cheap_summarize
from helpers.pages import _extract_pages

logger = get_logger("INGESTION_SERVICE", __name__)

class IngestionService:
    """Service for processing file uploads and storing them in MongoDB"""
    
    def __init__(self, rag_store: RAGStore, embedder: RemoteEmbeddingClient, captioner: NvidiaMaverickCaptioner):
        self.rag = rag_store
        self.embedder = embedder
        self.captioner = captioner
    
    async def process_files(
        self,
        user_id: str,
        project_id: str,
        files: List[tuple],  # (filename, raw_bytes)
        replace_filenames: Optional[List[str]] = None,
        rename_map: Optional[Dict[str, str]] = None,
        job_id: Optional[str] = None
    ) -> str:
        """
        Process files and store them in MongoDB
        
        Args:
            user_id: User identifier
            project_id: Project identifier
            files: List of (filename, raw_bytes) tuples
            replace_filenames: Optional list of filenames to replace
            rename_map: Optional mapping of old names to new names
            job_id: Optional job ID for tracking
        
        Returns:
            Job ID for tracking progress
        """
        if not job_id:
            job_id = str(uuid.uuid4())
        
        replace_set = set(replace_filenames or [])
        
        for idx, (fname, raw) in enumerate(files, start=1):
            try:
                # Handle file replacement
                if fname in replace_set:
                    try:
                        self.rag.db["chunks"].delete_many({"user_id": user_id, "project_id": project_id, "filename": fname})
                        self.rag.db["files"].delete_many({"user_id": user_id, "project_id": project_id, "filename": fname})
                        logger.info(f"[{job_id}] Replaced prior data for {fname}")
                    except Exception as de:
                        logger.warning(f"[{job_id}] Replace delete failed for {fname}: {de}")
                
                logger.info(f"[{job_id}] ({idx}/{len(files)}) Parsing {fname} ({len(raw)} bytes)")
                
                # Extract pages
                pages = _extract_pages(fname, raw)
                
                # Process images with captions
                num_imgs = sum(len(p.get("images", [])) for p in pages)
                captions = []
                if num_imgs > 0:
                    for p in pages:
                        caps = []
                        for im in p.get("images", []):
                            try:
                                cap = self.captioner.caption_image(im)
                                caps.append(cap)
                            except Exception as e:
                                logger.warning(f"[{job_id}] Caption error in {fname}: {e}")
                        captions.append(caps)
                else:
                    captions = [[] for _ in pages]
                
                # Merge captions into text
                for p, caps in zip(pages, captions):
                    if caps:
                        normalized = [ _normalize_caption(c) for c in caps if c ]
                        if normalized:
                            p["text"] = (p.get("text", "") + "\n\n" + "\n".join([f"[Image] {c}" for c in normalized])).strip()
                
                # Build cards
                cards = await build_cards_from_pages(pages, filename=fname, user_id=user_id, project_id=project_id)
                logger.info(f"[{job_id}] Built {len(cards)} cards for {fname}")
                
                # Generate embeddings
                embeddings = self.embedder.embed([c["content"] for c in cards])
                for c, vec in zip(cards, embeddings):
                    c["embedding"] = vec
                
                # Store in MongoDB
                self.rag.store_cards(cards)
                
                # Create file summary
                full_text = "\n\n".join(p.get("text", "") for p in pages)
                file_summary = await cheap_summarize(full_text, max_sentences=6)
                self.rag.upsert_file_summary(user_id=user_id, project_id=project_id, filename=fname, summary=file_summary)
                
                logger.info(f"[{job_id}] Completed {fname}")
                
            except Exception as e:
                logger.error(f"[{job_id}] Failed processing {fname}: {e}")
                raise
        
        logger.info(f"[{job_id}] Ingestion complete for {len(files)} files")
        return job_id
