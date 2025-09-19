from typing import List, Dict, Any, Optional
from pydantic import BaseModel


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
    sources: Optional[List[Dict[str, Any]]] = None

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


