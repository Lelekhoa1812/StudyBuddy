# ────────────────────────────── memo/conversation.py ──────────────────────────────
"""
Conversation Management Orchestrator

Main conversation manager that coordinates session management,
context retrieval, and memory consolidation for natural conversation flow.
"""

from typing import List, Dict, Any, Tuple, Optional
import os

from utils.logger import get_logger
from utils.rag.embeddings import EmbeddingClient

logger = get_logger("CONVERSATION_MANAGER", __name__)

class ConversationManager:
    """
    Main conversation manager that orchestrates all conversation-related functionality.
    """
    
    def __init__(self, memory_system, embedder: EmbeddingClient):
        self.memory_system = memory_system
        self.embedder = embedder
        
        # Initialize sub-managers
        from memo.sessions import get_session_manager
        from memo.retrieval import get_retrieval_manager
        from memo.consolidation import get_consolidation_manager
        
        self.session_manager = get_session_manager()
        self.retrieval_manager = get_retrieval_manager(memory_system, embedder)
        self.consolidation_manager = get_consolidation_manager(memory_system, embedder)
    
    async def get_smart_context(self, user_id: str, question: str, 
                              nvidia_rotator=None, project_id: Optional[str] = None,
                              conversation_mode: str = "chat") -> Tuple[str, str, Dict[str, Any]]:
        """
        Get intelligent context for conversation with enhanced memory planning.
        
        Args:
            user_id: User identifier
            question: Current question/instruction
            nvidia_rotator: NVIDIA API rotator for AI enhancement
            project_id: Project context
            conversation_mode: "chat" or "report"
            
        Returns:
            Tuple of (recent_context, semantic_context, metadata)
        """
        try:
            return await self.retrieval_manager.get_smart_context(
                user_id, question, nvidia_rotator, project_id, conversation_mode
            )
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Smart context failed: {e}")
            return "", "", {"error": str(e)}
    
    async def get_enhancement_context(self, user_id: str, question: str, 
                                    nvidia_rotator=None, project_id: Optional[str] = None) -> Tuple[str, str, Dict[str, Any]]:
        """Get context specifically optimized for enhancement requests"""
        try:
            return await self.retrieval_manager.get_enhancement_context(
                user_id, question, nvidia_rotator, project_id
            )
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Enhancement context failed: {e}")
            return "", "", {"error": str(e)}
    
    async def consolidate_memories(self, user_id: str, nvidia_rotator=None) -> Dict[str, Any]:
        """Consolidate and prune memories to prevent information overload"""
        try:
            return await self.consolidation_manager.consolidate_memories(user_id, nvidia_rotator)
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Memory consolidation failed: {e}")
            return {"consolidated": 0, "pruned": 0, "error": str(e)}
    
    async def handle_context_switch(self, user_id: str, new_question: str, 
                                  nvidia_rotator=None) -> Dict[str, Any]:
        """Handle context switching when user changes topics"""
        try:
            return await self.session_manager.detect_context_switch(user_id, new_question, nvidia_rotator)
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Context switch handling failed: {e}")
            return {"is_context_switch": False, "confidence": 0.0, "error": str(e)}
    
    def get_conversation_insights(self, user_id: str) -> Dict[str, Any]:
        """Get insights about the user's conversation patterns"""
        try:
            return self.session_manager.get_conversation_insights(user_id)
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Failed to get conversation insights: {e}")
            return {"error": str(e)}
    
    def clear_session(self, user_id: str):
        """Clear conversation session for user"""
        try:
            self.session_manager.clear_session(user_id)
            logger.info(f"[CONVERSATION_MANAGER] Cleared session for user {user_id}")
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Failed to clear session: {e}")
    
    def reset_all(self, user_id: str, project_id: str = None) -> Dict[str, Any]:
        """Reset all conversation-related components for a user"""
        try:
            results = {
                "session_cleared": False,
                "memory_cleared": False,
                "errors": []
            }
            
            # Clear session
            try:
                self.session_manager.clear_session(user_id)
                results["session_cleared"] = True
                logger.info(f"[CONVERSATION_MANAGER] Cleared session for user {user_id}")
            except Exception as e:
                error_msg = f"Failed to clear session: {e}"
                results["errors"].append(error_msg)
                logger.warning(f"[CONVERSATION_MANAGER] {error_msg}")
            
            # Clear memory using core memory system
            try:
                clear_results = self.memory_system.clear_all_memory(user_id, project_id)
                results["memory_cleared"] = clear_results.get("legacy_cleared", False) and clear_results.get("session_cleared", False)
                if clear_results.get("errors"):
                    results["errors"].extend(clear_results["errors"])
                logger.info(f"[CONVERSATION_MANAGER] Cleared memory for user {user_id}, project {project_id}")
            except Exception as e:
                error_msg = f"Failed to clear memory: {e}"
                results["errors"].append(error_msg)
                logger.warning(f"[CONVERSATION_MANAGER] {error_msg}")
            
            return results
            
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Failed to reset all for user {user_id}: {e}")
            return {
                "session_cleared": False,
                "memory_cleared": False,
                "errors": [f"Critical error: {e}"]
            }


# ────────────────────────────── Global Instance ──────────────────────────────

_conversation_manager: Optional[ConversationManager] = None

def get_conversation_manager(memory_system=None, embedder: EmbeddingClient = None) -> ConversationManager:
    """Get the global conversation manager instance"""
    global _conversation_manager
    
    if _conversation_manager is None:
        if not memory_system:
            from memo.core import get_memory_system
            memory_system = get_memory_system()
        if not embedder:
            from utils.rag.embeddings import EmbeddingClient
            embedder = EmbeddingClient()
        
        _conversation_manager = ConversationManager(memory_system, embedder)
        logger.info("[CONVERSATION_MANAGER] Global conversation manager initialized")
    
    return _conversation_manager

# def reset_conversation_manager():
#     """Reset the global conversation manager (for testing)"""
#     global _conversation_manager
#     _conversation_manager = None