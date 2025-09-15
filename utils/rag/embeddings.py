# ────────────────────────────── utils/embeddings.py ──────────────────────────────
import os
from typing import List
import numpy as np
from ..logger import get_logger

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None


logger = get_logger("EMBED", __name__)


class EmbeddingClient:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None

    def _lazy(self):
        if self.model is None and SentenceTransformer is not None:
            logger.info(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)

    def embed(self, texts: List[str]) -> List[list]:
        self._lazy()
        if self.model is None:
            # Fallback: extremely naive hashing -> NOT for production, but keeps code running without deps
            logger.warning("SentenceTransformer unavailable; using random fallback embeddings.")
            return [list(np.random.default_rng(hash(t) % (2**32)).normal(size=384).astype("float32")) for t in texts]
        vecs = self.model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        return [v.tolist() for v in vecs]