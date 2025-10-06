# ────────────────────────────── utils/embeddings.py ──────────────────────────────
import os
from typing import List
import numpy as np
import httpx
from ..logger import get_logger


logger = get_logger("EMBED", __name__)


class EmbeddingClient:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", api_url: str | None = None):
        self.model_name = model_name
        self.api_url = api_url or os.getenv("EMBEDDER_URL")

    def embed(self, texts: List[str]) -> List[list]:
        if not texts:
            return []

        if not self.api_url:
            logger.warning("EMBEDDER_URL not set; using random fallback embeddings.")
            return [list(np.random.default_rng(hash(t) % (2**32)).normal(size=384).astype("float32")) for t in texts]

        url = self.api_url.rstrip("/") + "/embed"
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json={"texts": texts})
                resp.raise_for_status()
                data = resp.json()
                vectors = data.get("vectors")
                if not isinstance(vectors, list):
                    raise ValueError("Invalid response: 'vectors' field missing or not a list")
                return vectors
        except Exception as e:
            logger.error(f"Embedding API call failed: {e}; falling back to random embeddings.")
            return [list(np.random.default_rng(hash(t) % (2**32)).normal(size=384).astype("float32")) for t in texts]