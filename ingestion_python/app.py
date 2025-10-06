"""
Ingestion Pipeline Service

A dedicated service for processing file uploads and storing them in MongoDB Atlas.
This service mirrors the main system's file processing functionality while
running as a separate service to share the processing load.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import shared utilities (now local)
from utils.logger import get_logger
from utils.rag.rag import RAGStore, ensure_indexes
from utils.embedding import RemoteEmbeddingClient
from services.maverick_captioner import NvidiaMaverickCaptioner
from api.routes import router, initialize_services

logger = get_logger("INGESTION_PIPELINE", __name__)

# FastAPI app
app = FastAPI(title="Ingestion Pipeline", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job tracker (same as main system)
app.state.jobs = {}

# Global clients (same as main system)
try:
    rag = RAGStore(mongo_uri=os.getenv("MONGO_URI"), db_name=os.getenv("MONGO_DB", "studybuddy"))
    rag.client.admin.command('ping')
    logger.info("[INGESTION_PIPELINE] MongoDB connection successful")
    ensure_indexes(rag)
    logger.info("[INGESTION_PIPELINE] MongoDB indexes ensured")
except Exception as e:
    logger.error(f"[INGESTION_PIPELINE] Failed to initialize MongoDB: {e}")
    rag = None

embedder = RemoteEmbeddingClient()
captioner = NvidiaMaverickCaptioner()

# Initialize services
initialize_services(rag, embedder, captioner)

# Include API routes
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("INGESTION_PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
