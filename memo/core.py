# ────────────────────────────── memo/core.py ──────────────────────────────
"""
Core Memory System

Main memory system that provides both legacy and enhanced functionality.
"""

import os
import asyncio
from typing import List, Dict, Any, Optional, Tuple

from utils.logger import get_logger
from utils.embeddings import EmbeddingClient
from memo.legacy import MemoryLRU
from memo.persistent import PersistentMemory

logger = get_logger("CORE_MEMORY", __name__)

class MemorySystem:
    """
    Main memory system that provides both legacy and enhanced functionality.
    Automatically uses enhanced features when MongoDB is available.
    """
    
    def __init__(self, mongo_uri: str = None, db_name: str = "studybuddy"):
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.db_name = db_name
        
        # Initialize legacy memory system (always available)
        self.legacy_memory = MemoryLRU()
        
        # Initialize enhanced memory system if MongoDB is available
        self.enhanced_available = False
        self.enhanced_memory = None
        self.embedder = None
        
        try:
            self.embedder = EmbeddingClient()
            self.enhanced_memory = PersistentMemory(self.mongo_uri, self.db_name, self.embedder)
            self.enhanced_available = True
            logger.info("[CORE_MEMORY] Enhanced memory system initialized")
        except Exception as e:
            logger.warning(f"[CORE_MEMORY] Enhanced memory system unavailable: {e}")
            self.enhanced_available = False
        
        logger.info(f"[CORE_MEMORY] Initialized with enhanced_available={self.enhanced_available}")
    
    # ────────────────────────────── Core Memory Operations ──────────────────────────────
    
    def add(self, user_id: str, qa_summary: str):
        """Add a Q&A summary to memory (backward compatibility)"""
        try:
            # Add to legacy memory
            self.legacy_memory.add(user_id, qa_summary)
            
            # Also add to enhanced memory if available
            if self.enhanced_available:
                # Extract question and answer from summary
                lines = qa_summary.split('\n')
                question = ""
                answer = ""
                
                for line in lines:
                    if line.strip().lower().startswith('q:'):
                        question = line.strip()[2:].strip()
                    elif line.strip().lower().startswith('a:'):
                        answer = line.strip()[2:].strip()
                
                if question and answer:
                    asyncio.create_task(self._add_enhanced_memory(user_id, question, answer))
            
            logger.debug(f"[CORE_MEMORY] Added memory for user {user_id}")
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to add memory: {e}")
    
    def recent(self, user_id: str, n: int = 3) -> List[str]:
        """Get recent memories (backward compatibility)"""
        return self.legacy_memory.recent(user_id, n)
    
    def rest(self, user_id: str, skip_n: int = 3) -> List[str]:
        """Get remaining memories excluding recent ones (backward compatibility)"""
        return self.legacy_memory.rest(user_id, skip_n)
    
    def all(self, user_id: str) -> List[str]:
        """Get all memories for a user (backward compatibility)"""
        return self.legacy_memory.all(user_id)
    
    def clear(self, user_id: str) -> None:
        """Clear all memories for a user (backward compatibility)"""
        self.legacy_memory.clear(user_id)
        
        # Also clear enhanced memory if available
        if self.enhanced_available:
            try:
                self.enhanced_memory.clear_user_memories(user_id)
                logger.info(f"[CORE_MEMORY] Cleared enhanced memory for user {user_id}")
            except Exception as e:
                logger.warning(f"[CORE_MEMORY] Failed to clear enhanced memory: {e}")
    
    def is_enhanced_available(self) -> bool:
        """Check if enhanced memory features are available"""
        return self.enhanced_available
    
    # ────────────────────────────── Enhanced Features ──────────────────────────────
    
    async def add_conversation_memory(self, user_id: str, question: str, answer: str,
                                    project_id: Optional[str] = None,
                                    context: Dict[str, Any] = None) -> str:
        """Add conversation memory with enhanced context"""
        if not self.enhanced_available:
            logger.warning("[CORE_MEMORY] Enhanced features not available")
            return ""
        
        try:
            memory_id = self.enhanced_memory.add_memory(
                user_id=user_id,
                content=f"Q: {question}\nA: {answer}",
                memory_type="conversation",
                project_id=project_id,
                importance="medium",
                tags=["conversation", "qa"],
                metadata=context or {}
            )
            return memory_id
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to add conversation memory: {e}")
            return ""
    
    async def get_conversation_context(self, user_id: str, question: str,
                                     project_id: Optional[str] = None) -> Tuple[str, str]:
        """Get conversation context for chat continuity"""
        try:
            if self.enhanced_available:
                # Use enhanced context retrieval
                recent_context, semantic_context = await self._get_enhanced_context(user_id, question)
                return recent_context, semantic_context
            else:
                # Fallback to legacy context
                return "", ""
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to get conversation context: {e}")
            return "", ""
    
    async def search_memories(self, user_id: str, query: str,
                            project_id: Optional[str] = None,
                            limit: int = 10) -> List[Tuple[str, float]]:
        """Search memories using semantic similarity"""
        if not self.enhanced_available:
            return []
        
        try:
            results = self.enhanced_memory.search_memories(
                user_id=user_id,
                query=query,
                project_id=project_id,
                limit=limit
            )
            return [(m["content"], score) for m, score in results]
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to search memories: {e}")
            return []
    
    def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """Get memory statistics for a user"""
        if self.enhanced_available:
            return self.enhanced_memory.get_memory_stats(user_id)
        else:
            # Legacy memory stats
            all_memories = self.legacy_memory.all(user_id)
            return {
                "total_memories": len(all_memories),
                "system_type": "legacy",
                "enhanced_available": False
            }
    
    # ────────────────────────────── Private Helper Methods ──────────────────────────────
    
    async def _add_enhanced_memory(self, user_id: str, question: str, answer: str):
        """Add memory to enhanced system"""
        try:
            self.enhanced_memory.add_memory(
                user_id=user_id,
                content=f"Q: {question}\nA: {answer}",
                memory_type="conversation",
                importance="medium",
                tags=["conversation", "qa"]
            )
        except Exception as e:
            logger.warning(f"[CORE_MEMORY] Failed to add enhanced memory: {e}")
    
    async def _get_enhanced_context(self, user_id: str, question: str) -> Tuple[str, str]:
        """Get context from enhanced memory system"""
        try:
            # Get recent conversation memories
            recent_memories = self.enhanced_memory.get_memories(
                user_id=user_id,
                memory_type="conversation",
                limit=5
            )
            
            recent_context = ""
            if recent_memories:
                recent_summaries = [m["summary"] for m in recent_memories]
                recent_context = "\n\n".join(recent_summaries)
            
            # Get semantic context from other memory types
            semantic_memories = self.enhanced_memory.get_memories(
                user_id=user_id,
                limit=10
            )
            
            semantic_context = ""
            if semantic_memories:
                other_memories = [m for m in semantic_memories if m.get("memory_type") != "conversation"]
                if other_memories:
                    semantic_summaries = [m["summary"] for m in other_memories]
                    semantic_context = "\n\n".join(semantic_summaries)
            
            return recent_context, semantic_context
            
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to get enhanced context: {e}")
            return "", ""

# ────────────────────────────── Global Instance ──────────────────────────────

_memory_system: Optional[MemorySystem] = None

def get_memory_system(mongo_uri: str = None, db_name: str = None) -> MemorySystem:
    """Get the global memory system instance"""
    global _memory_system
    
    if _memory_system is None:
        if mongo_uri is None:
            mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        if db_name is None:
            db_name = os.getenv("MONGO_DB", "studybuddy")
        
        _memory_system = MemorySystem(mongo_uri, db_name)
        logger.info("[CORE_MEMORY] Global memory system initialized")
    
    return _memory_system

def reset_memory_system():
    """Reset the global memory system (for testing)"""
    global _memory_system
    _memory_system = None
