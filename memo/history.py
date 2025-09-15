# ────────────────────────────── memo/history.py ──────────────────────────────
"""
History Management

Functions for managing conversation history and context.
"""

from typing import List, Dict, Any, Tuple, Optional

from utils.logger import get_logger
from memo.nvidia import summarize_qa, files_relevance, related_recent_context
from memo.context import get_conversation_context, get_legacy_context, semantic_context
from utils.embeddings import EmbeddingClient

logger = get_logger("HISTORY_MANAGER", __name__)

class HistoryManager:
    """
    Enhanced history manager that provides both legacy and enhanced functionality.
    Automatically uses enhanced features when available.
    """
    
    def __init__(self, memory_system=None):
        self.memory_system = memory_system
    
    async def summarize_qa_with_nvidia(self, question: str, answer: str, nvidia_rotator) -> str:
        """Summarize Q&A using NVIDIA model (enhanced version)"""
        return await summarize_qa(question, answer, nvidia_rotator)
    
    async def files_relevance(self, question: str, file_summaries: List[Dict[str, str]], nvidia_rotator) -> Dict[str, bool]:
        """Determine file relevance using NVIDIA model (enhanced version)"""
        return await files_relevance(question, file_summaries, nvidia_rotator)
    
    async def related_recent_and_semantic_context(self, user_id: str, question: str, 
                                                embedder: EmbeddingClient, 
                                                topk_sem: int = 3) -> Tuple[str, str]:
        """Get related recent and semantic context (enhanced version)"""
        try:
            if self.memory_system and self.memory_system.is_enhanced_available():
                # Use enhanced context retrieval
                recent_context, semantic_context = await self.memory_system.get_conversation_context(
                    user_id, question
                )
                return recent_context, semantic_context
            else:
                # Fallback to original implementation
                return await get_legacy_context(user_id, question, self.memory_system, embedder, topk_sem)
        except Exception as e:
            logger.error(f"[HISTORY_MANAGER] Context retrieval failed: {e}")
            return "", ""

# ────────────────────────────── Legacy Functions (Backward Compatibility) ──────────────────────────────

async def summarize_qa_with_nvidia(question: str, answer: str, rotator) -> str:
    """
    Returns a single line block:
    q: <concise>\na: <concise>
    No extra commentary.
    """
    return await summarize_qa(question, answer, rotator)

async def files_relevance(question: str, file_summaries: List[Dict[str, str]], rotator) -> Dict[str, bool]:
    """
    Ask NVIDIA model to mark each file as relevant (true) or not (false) for the question.
    Returns {filename: bool}
    """
    return await files_relevance(question, file_summaries, rotator)

async def related_recent_and_semantic_context(user_id: str, question: str, memory, embedder: EmbeddingClient, topk_sem: int = 3) -> Tuple[str, str]:
    """
    Returns (recent_related_text, semantic_related_text).
    - recent_related_text: NVIDIA checks the last 3 summaries for direct relatedness.
    - semantic_related_text: cosine-sim search over the remaining 17 summaries (top-k).
    
    This function is maintained for backward compatibility.
    For enhanced features, use the integrated memory system.
    """
    recent3 = memory.recent(user_id, 3)
    rest17 = memory.rest(user_id, 3)

    recent_text = ""
    if recent3:
        # This would need NVIDIA processing in the calling code
        pass
    
    # Semantic over rest17
    sem_text = ""
    if rest17:
        sem_text = await semantic_context(question, rest17, embedder, topk_sem)
    
    # Return recent empty (to be filled by caller using NVIDIA), and semantic text
    return ("", sem_text)

# ────────────────────────────── Global Instance ──────────────────────────────

_history_manager: Optional[HistoryManager] = None

def get_history_manager(memory_system=None) -> HistoryManager:
    """Get the global history manager instance"""
    global _history_manager
    
    if _history_manager is None:
        _history_manager = HistoryManager(memory_system)
        logger.info("[HISTORY_MANAGER] Global history manager initialized")
    
    return _history_manager

def reset_history_manager():
    """Reset the global history manager (for testing)"""
    global _history_manager
    _history_manager = None