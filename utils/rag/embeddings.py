# ────────────────────────────── utils/embeddings.py ──────────────────────────────
import os
from typing import List
import requests

from utils.logger import get_logger


logger = get_logger("EMBED", __name__)


class EmbeddingClient:
    """Embedding client that calls external embedding service via HTTP.

    Expects environment variable EMBEDDER_BASE_URL pointing at an API with:
      POST /embed {"texts": [..]} -> {"vectors": [[..], ...], "model": "..."}
    """

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or os.getenv("EMBEDDER_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            logger.warning("EMBEDDER_BASE_URL not set; embedding calls will fail.")

    def embed(self, texts: List[str]) -> List[list]:
        if not texts:
            return []
        if not self.base_url:
            raise RuntimeError("EMBEDDER_BASE_URL not configured")
        url = f"{self.base_url}/embed"
        try:
            resp = requests.post(url, json={"texts": texts}, timeout=60)
            if resp.status_code >= 400:
                raise RuntimeError(f"Embedding API error {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            vectors = data.get("vectors") or []
            return vectors
        except Exception as e:
            logger.warning(f"Embedding API failed: {e}")
            raise