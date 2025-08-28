# ────────────────────────────── memo/memory.py ──────────────────────────────
from collections import deque, defaultdict
from typing import List, Dict

class MemoryLRU:
    """
    Per-user LRU-like memory of the last N (default 20) summarized chat sessions.
    Each item is a single string in the format: "q: ...\na: ..."
    """
    def __init__(self, capacity: int = 20):
        self.capacity = capacity
        self._store: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.capacity))

    def add(self, user_id: str, qa_summary: str):
        self._store[user_id].append(qa_summary)

    def recent(self, user_id: str, n: int = 3) -> List[str]:
        d = self._store[user_id]
        if not d:
            return []
        # Return last n in recency order (most recent first)
        return list(d)[-n:][::-1]

    def rest(self, user_id: str, skip_n: int = 3) -> List[str]:
        d = self._store[user_id]
        if not d:
            return []
        # Everything except the most recent `skip_n`, oldest first
        return list(d)[:-skip_n] if len(d) > skip_n else []

    def all(self, user_id: str) -> List[str]:
        return list(self._store[user_id])

    def clear(self, user_id: str) -> None:
        """
        Clear all cached summaries for the given user.
        """
        if user_id in self._store:
            self._store[user_id].clear()
