"""
Pydantic models for the ingestion pipeline API
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel

# Response models (same as main system)
class UploadResponse(BaseModel):
    job_id: str
    status: str
    total_files: Optional[int] = None

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    total: int
    completed: int
    progress: float
    last_error: Optional[str] = None
    created_at: float

class HealthResponse(BaseModel):
    ok: bool
    mongodb_connected: bool
    service: str = "ingestion_pipeline"

class FileResponse(BaseModel):
    filename: str
    summary: str

class FilesListResponse(BaseModel):
    files: List[FileResponse]
    filenames: List[str]

class ChunksResponse(BaseModel):
    chunks: List[Dict[str, Any]]
