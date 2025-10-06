import os
from typing import List

import requests

from utils.logger import get_logger


logger = get_logger("REMOTE_EMBED", __name__)


class RemoteEmbeddingClient:
    """Client to call external embedding service /embed endpoint.

    Expects env EMBED_BASE_URL, e.g. https://<space>.hf.space
    """

    def __init__(self, base_url: str | None = None, timeout: int = 60):
        self.base_url = (base_url or os.getenv("EMBED_BASE_URL", "https://binkhoale1812-embedding.hf.space")).rstrip("/")
        if not self.base_url:
            raise RuntimeError("EMBED_BASE_URL is required for RemoteEmbeddingClient")
        self.timeout = timeout

    def embed(self, texts: List[str]) -> List[list]:
        if not texts:
            return []
        url = f"{self.base_url}/embed"
        payload = {"texts": texts}
        headers = {"Content-Type": "application/json"}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            vectors = data.get("vectors", [])
            # Basic validation
            if not isinstance(vectors, list):
                raise ValueError("Invalid vectors format from remote embedder")
            return vectors
        except Exception as e:
            logger.warning(f"Remote embedding failed: {e}")
            # Fail closed with zero vectors to avoid crashes
            return [[0.0] * 384 for _ in texts]


