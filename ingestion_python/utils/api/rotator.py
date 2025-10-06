# ────────────────────────────── utils/rotator.py ──────────────────────────────
import os
import itertools
from ..logger import get_logger
from typing import Optional

import httpx

logger = get_logger("ROTATOR", __name__)


class APIKeyRotator:
    """
    Round-robin API key rotator.
    - Loads keys from env vars with given prefix (e.g., GEMINI_API_1..6)
    - get_key() returns current key
    - rotate() moves to next key
    - on HTTP 401/429/5xx you should call rotate() and retry (bounded)
    """
    def __init__(self, prefix: str, max_slots: int = 6):
        self.keys = []
        for i in range(1, max_slots + 1):
            v = os.getenv(f"{prefix}{i}")
            if v:
                self.keys.append(v.strip())
        if not self.keys:
            logger.warning(f"No API keys found for prefix {prefix}. Calls will likely fail.")
            self._cycle = itertools.cycle([""])
        else:
            self._cycle = itertools.cycle(self.keys)
        self.current = next(self._cycle)

    def get_key(self) -> Optional[str]:
        return self.current

    def rotate(self) -> Optional[str]:
        self.current = next(self._cycle)
        logger.info("Rotated API key.")
        return self.current


async def robust_post_json(url: str, headers: dict, payload: dict, rotator: APIKeyRotator, max_retries: int = 6):
    """
    POST JSON with simple retry+rotate on 401/403/429/5xx.
    Returns json response.
    """
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(url, headers=headers, json=payload)
                logger.info(f"[ROTATOR] HTTP {r.status_code} response from {url}")
                
                if r.status_code in (401, 403, 429) or (500 <= r.status_code < 600):
                    logger.warning(f"HTTP {r.status_code} from provider. Rotating key and retrying ({attempt+1}/{max_retries})")
                    logger.warning(f"Response body: {r.text}")
                    rotator.rotate()
                    continue
                r.raise_for_status()
                
                response_data = r.json()
                logger.info(f"[ROTATOR] Successfully parsed JSON response with keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Not a dict'}")
                return response_data
        except Exception as e:
            logger.warning(f"Request error: {e}. Rotating and retrying ({attempt+1}/{max_retries})")
            logger.warning(f"Request details - URL: {url}, Headers: {headers}")
            rotator.rotate()
    raise RuntimeError("Provider request failed after retries.")