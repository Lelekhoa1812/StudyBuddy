# ────────────────────────────── memo/legacy.py ──────────────────────────────
"""
Legacy Memory System

In-memory LRU system for backward compatibility.
"""

from collections import deque, defaultdict
from typing import List, Dict

from utils.logger import get_logger

logger = get_logger("LEGACY_MEMORY", __name__)

class MemoryLRU:
    """Legacy in-memory LRU system for backward compatibility"""
    
    def __init__(self, capacity: int = 20):
        self.capacity = capacity
        self._store: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.capacity))

    def add(self, user_id: str, qa_summary: str):
        """Add a Q&A summary to the user's memory"""
        self._store[user_id].append(qa_summary)
        logger.debug(f"[LEGACY_MEMORY] Added memory for user {user_id}")

    def recent(self, user_id: str, n: int = 3) -> List[str]:
        """Get the most recent n memories for a user"""
        d = self._store[user_id]
        if not d:
            return []
        # Return last n in recency order (most recent first)
        return list(d)[-n:][::-1]

    def rest(self, user_id: str, skip_n: int = 3) -> List[str]:
        """Get memories excluding the most recent skip_n"""
        d = self._store[user_id]
        if not d:
            return []
        # Everything except the most recent `skip_n`, oldest first
        return list(d)[:-skip_n] if len(d) > skip_n else []

    def all(self, user_id: str) -> List[str]:
        """Get all memories for a user"""
        return list(self._store[user_id])

    def clear(self, user_id: str) -> None:
        """Clear all cached summaries for the given user"""
        if user_id in self._store:
            self._store[user_id].clear()
            logger.info(f"[LEGACY_MEMORY] Cleared memories for user {user_id}")
