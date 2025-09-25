import os, logging
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from utils.logger import get_logger
from utils.api.rotator import APIKeyRotator
from utils.ingestion.caption import BlipCaptioner
from utils.rag.embeddings import EmbeddingClient
from utils.rag.rag import RAGStore, ensure_indexes
from utils.analytics import init_analytics


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
    
    # Initialize analytics tracker
    init_analytics(rag.client, os.getenv("MONGO_DB", "studybuddy"))
    logger.info("[APP] Analytics tracker initialized")
except Exception as e:
    logger.error(f"[APP] Failed to initialize MongoDB/RAG store: {str(e)}")
    logger.error(f"[APP] MONGO_URI: {os.getenv('MONGO_URI', 'Not set')}")
    logger.error(f"[APP] MONGO_DB: {os.getenv('MONGO_DB', 'studybuddy')}")
    # Create a dummy RAG store for now - this will cause errors but prevents the app from crashing
    rag = None


