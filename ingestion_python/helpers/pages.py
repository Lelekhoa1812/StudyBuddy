import os
from typing import List, Dict, Any
from fastapi import HTTPException
from utils.ingestion.parser import parse_pdf_bytes, parse_docx_bytes

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


