# ────────────────────────────── memo/context.py ──────────────────────────────
"""
Context Management

Functions for retrieving and managing conversation context.
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional

from utils.logger import get_logger
from utils.embeddings import EmbeddingClient

logger = get_logger("CONTEXT_MANAGER", __name__)

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors"""
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return float(np.dot(a, b) / denom)

async def semantic_context(question: str, memories: List[str], embedder: EmbeddingClient, topk: int = 3) -> str:
    """
    Get semantic context from memories using cosine similarity.
    """
    if not memories:
        return ""
    
    try:
        qv = np.array(embedder.embed([question])[0], dtype="float32")
        mats = embedder.embed([s.strip() for s in memories])
        sims = [(cosine_similarity(qv, np.array(v, dtype="float32")), s) for v, s in zip(mats, memories)]
        sims.sort(key=lambda x: x[0], reverse=True)
        top = [s for (sc, s) in sims[:topk] if sc > 0.15]  # small threshold
        return "\n\n".join(top) if top else ""
    except Exception as e:
        logger.error(f"[CONTEXT_MANAGER] Semantic context failed: {e}")
        return ""

async def get_conversation_context(user_id: str, question: str, memory_system, 
                                 embedder: EmbeddingClient, topk_sem: int = 3) -> Tuple[str, str]:
    """
    Get both recent and semantic context for conversation continuity.
    Enhanced version that uses semantic similarity for better context selection.
    """
    try:
        if memory_system and memory_system.is_enhanced_available():
            # Use enhanced context retrieval
            recent_context, semantic_context = await memory_system.get_conversation_context(
                user_id, question
            )
            return recent_context, semantic_context
        else:
            # Fallback to legacy context with enhanced semantic selection
            return await get_legacy_context(user_id, question, memory_system, embedder, topk_sem)
    except Exception as e:
        logger.error(f"[CONTEXT_MANAGER] Context retrieval failed: {e}")
        return "", ""

async def get_legacy_context(user_id: str, question: str, memory_system, 
                           embedder: EmbeddingClient, topk_sem: int) -> Tuple[str, str]:
    """Get context using legacy method with enhanced semantic selection"""
    if not memory_system:
        return "", ""
    
    recent3 = memory_system.recent(user_id, 3)
    rest17 = memory_system.rest(user_id, 3)
    
    # Use semantic similarity to select most relevant recent memories
    recent_text = ""
    if recent3:
        try:
            recent_text = await semantic_context(question, recent3, embedder, 2)
        except Exception as e:
            logger.warning(f"[CONTEXT_MANAGER] Recent context selection failed: {e}")
    
    # Get semantic context from remaining memories
    sem_text = ""
    if rest17:
        sem_text = await semantic_context(question, rest17, embedder, topk_sem)
    
    return recent_text, sem_text
