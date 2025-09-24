# ────────────────────────────── memo/core.py ──────────────────────────────
"""
Core Memory System

Main memory system that provides both legacy and enhanced functionality.
"""

import os
import asyncio
from typing import List, Dict, Any, Optional, Tuple

from utils.logger import get_logger
from utils.rag.embeddings import EmbeddingClient
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
        self.session_memory = None
        
        try:
            self.embedder = EmbeddingClient()
            self.enhanced_memory = PersistentMemory(self.mongo_uri, self.db_name, self.embedder)
            from memo.session import get_session_memory_manager
            self.session_memory = get_session_memory_manager(self.mongo_uri, self.db_name)
            self.enhanced_available = True
            logger.info("[CORE_MEMORY] Enhanced memory system and session memory initialized")
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
    
    def clear_all_memory(self, user_id: str, project_id: str = None) -> Dict[str, Any]:
        """Clear all memory components for a user including sessions and planning state"""
        try:
            results = {
                "legacy_cleared": False,
                "enhanced_cleared": False,
                "session_cleared": False,
                "planning_reset": False,
                "errors": []
            }
            
            # Clear legacy memory
            try:
                self.legacy_memory.clear(user_id)
                results["legacy_cleared"] = True
                logger.info(f"[CORE_MEMORY] Cleared legacy memory for user {user_id}")
            except Exception as e:
                error_msg = f"Failed to clear legacy memory: {e}"
                results["errors"].append(error_msg)
                logger.warning(f"[CORE_MEMORY] {error_msg}")
            
            # Clear enhanced memory if available
            if self.enhanced_available:
                try:
                    if project_id:
                        # Clear project-specific memories
                        self.enhanced_memory.memories.delete_many({
                            "user_id": user_id, 
                            "project_id": project_id
                        })
                    else:
                        # Clear all user memories
                        self.enhanced_memory.clear_user_memories(user_id)
                    results["enhanced_cleared"] = True
                    logger.info(f"[CORE_MEMORY] Cleared enhanced memory for user {user_id}, project {project_id}")
                except Exception as e:
                    error_msg = f"Failed to clear enhanced memory: {e}"
                    results["errors"].append(error_msg)
                    logger.warning(f"[CORE_MEMORY] {error_msg}")
            
            # Clear conversation sessions
            try:
                from memo.sessions import get_session_manager
                session_manager = get_session_manager()
                session_manager.clear_session(user_id)
                results["session_cleared"] = True
                logger.info(f"[CORE_MEMORY] Cleared session for user {user_id}")
            except Exception as e:
                error_msg = f"Failed to clear session: {e}"
                results["errors"].append(error_msg)
                logger.warning(f"[CORE_MEMORY] {error_msg}")
            
            # Reset planning state (if needed)
            try:
                # Planning state is stateless, but we can log the reset
                results["planning_reset"] = True
                logger.info(f"[CORE_MEMORY] Reset planning state for user {user_id}")
            except Exception as e:
                error_msg = f"Failed to reset planning state: {e}"
                results["errors"].append(error_msg)
                logger.warning(f"[CORE_MEMORY] {error_msg}")
            
            # Clear any cached contexts
            try:
                from memo.retrieval import get_retrieval_manager
                retrieval_manager = get_retrieval_manager(self, self.embedder)
                # Reset any cached state if needed
                logger.info(f"[CORE_MEMORY] Cleared cached contexts for user {user_id}")
            except Exception as e:
                error_msg = f"Failed to clear cached contexts: {e}"
                results["errors"].append(error_msg)
                logger.warning(f"[CORE_MEMORY] {error_msg}")
            
            success = all([results["legacy_cleared"], results["session_cleared"]])
            if self.enhanced_available:
                success = success and results["enhanced_cleared"]
            
            if success:
                logger.info(f"[CORE_MEMORY] Successfully cleared all memory for user {user_id}, project {project_id}")
            else:
                logger.warning(f"[CORE_MEMORY] Partial memory clear for user {user_id}, project {project_id}: {results}")
            
            return results
            
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to clear all memory for user {user_id}: {e}")
            return {
                "legacy_cleared": False,
                "enhanced_cleared": False,
                "session_cleared": False,
                "planning_reset": False,
                "errors": [f"Critical error: {e}"]
            }
    
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
        """Get conversation context for chat continuity with enhanced memory ability"""
        try:
            if self.enhanced_available:
                # Use enhanced context retrieval with better integration
                recent_context, semantic_context = await self._get_enhanced_context(user_id, question)
                return recent_context, semantic_context
            else:
                # Use legacy context with enhanced semantic selection
                from memo.context import get_legacy_context
                return await get_legacy_context(user_id, question, self, self.embedder, 3)
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to get conversation context: {e}")
            return "", ""
    
    async def get_enhanced_context(self, user_id: str, question: str,
                                 project_id: Optional[str] = None) -> Tuple[str, str, Dict[str, Any]]:
        """Get enhanced context using the new memory planning system"""
        try:
            return await self.get_smart_context(user_id, question, None, project_id, "chat")
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to get enhanced context: {e}")
            return "", "", {"error": str(e)}
    
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
    
    async def consolidate_memories(self, user_id: str, nvidia_rotator=None) -> Dict[str, Any]:
        """Consolidate and prune memories to prevent information overload"""
        try:
            from memo.conversation import get_conversation_manager
            conversation_manager = get_conversation_manager(self, self.embedder)
            
            return await conversation_manager.consolidate_memories(user_id, nvidia_rotator)
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Memory consolidation failed: {e}")
            return {"consolidated": 0, "pruned": 0, "error": str(e)}
    
    async def handle_context_switch(self, user_id: str, new_question: str, 
                                  nvidia_rotator=None) -> Dict[str, Any]:
        """Handle context switching when user changes topics"""
        try:
            from memo.conversation import get_conversation_manager
            conversation_manager = get_conversation_manager(self, self.embedder)
            
            return await conversation_manager.handle_context_switch(user_id, new_question, nvidia_rotator)
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Context switch handling failed: {e}")
            return {"is_context_switch": False, "confidence": 0.0, "error": str(e)}
    
    def get_conversation_insights(self, user_id: str) -> Dict[str, Any]:
        """Get insights about the user's conversation patterns"""
        try:
            from memo.conversation import get_conversation_manager
            conversation_manager = get_conversation_manager(self, self.embedder)
            
            return conversation_manager.get_conversation_insights(user_id)
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to get conversation insights: {e}")
            return {"error": str(e)}
    
    async def get_smart_context(self, user_id: str, question: str, 
                              nvidia_rotator=None, project_id: Optional[str] = None,
                              conversation_mode: str = "chat") -> Tuple[str, str, Dict[str, Any]]:
        """Get smart context using advanced memory planning strategy"""
        try:
            from memo.planning import get_memory_planner
            memory_planner = get_memory_planner(self, self.embedder)
            
            # Plan memory strategy based on user intent
            execution_plan = await memory_planner.plan_memory_strategy(
                user_id, question, nvidia_rotator, project_id
            )
            
            # Execute the planned strategy
            recent_context, semantic_context, metadata = await memory_planner.execute_memory_plan(
                user_id, question, execution_plan, nvidia_rotator, project_id
            )
            
            # Add planning metadata to response
            metadata.update({
                "memory_planning": True,
                "intent": execution_plan["intent"].value,
                "strategy": execution_plan["strategy"].value,
                "enhancement_focus": execution_plan["enhancement_focus"],
                "qa_focus": execution_plan["qa_focus"]
            })
            
            return recent_context, semantic_context, metadata
            
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to get smart context: {e}")
            # Fallback to original conversation manager
            try:
                from memo.conversation import get_conversation_manager
                conversation_manager = get_conversation_manager(self, self.embedder)
                
                return await conversation_manager.get_smart_context(
                    user_id, question, nvidia_rotator, project_id, conversation_mode
                )
            except Exception as fallback_error:
                logger.error(f"[CORE_MEMORY] Fallback also failed: {fallback_error}")
                return "", "", {"error": str(e)}
    
    async def get_enhancement_context(self, user_id: str, question: str, 
                                    nvidia_rotator=None, project_id: Optional[str] = None) -> Tuple[str, str, Dict[str, Any]]:
        """Get context specifically optimized for enhancement requests"""
        try:
            from memo.planning import get_memory_planner, QueryIntent, MemoryStrategy
            memory_planner = get_memory_planner(self, self.embedder)
            
            # Force enhancement intent and focused Q&A strategy
            execution_plan = {
                "intent": QueryIntent.ENHANCEMENT,
                "strategy": MemoryStrategy.FOCUSED_QA,
                "retrieval_params": {
                    "recent_limit": 5,
                    "semantic_limit": 10,
                    "qa_focus": True,
                    "enhancement_mode": True,
                    "priority_types": ["conversation", "qa"],
                    "similarity_threshold": 0.05,  # Very low threshold for maximum recall
                    "use_ai_selection": True
                },
                "conversation_context": {},
                "enhancement_focus": True,
                "qa_focus": True
            }
            
            # Execute the enhancement-focused strategy
            recent_context, semantic_context, metadata = await memory_planner.execute_memory_plan(
                user_id, question, execution_plan, nvidia_rotator, project_id
            )
            
            # Add enhancement-specific metadata
            metadata.update({
                "enhancement_mode": True,
                "qa_focused": True,
                "memory_planning": True,
                "intent": "enhancement",
                "strategy": "focused_qa"
            })
            
            logger.info(f"[CORE_MEMORY] Enhancement context retrieved: {len(recent_context)} recent, {len(semantic_context)} semantic")
            return recent_context, semantic_context, metadata
            
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to get enhancement context: {e}")
            return "", "", {"error": str(e)}
    
    # ────────────────────────────── Session-Specific Memory Operations ──────────────────────────────
    
    def add_session_memory(self, user_id: str, project_id: str, session_id: str, 
                          question: str, answer: str, context: Dict[str, Any] = None) -> str:
        """Add memory to a specific session"""
        try:
            if not self.session_memory:
                logger.warning("[CORE_MEMORY] Session memory not available")
                return ""
            
            # Create session-specific memory content
            content = f"Q: {question}\nA: {answer}"
            
            memory_id = self.session_memory.add_session_memory(
                user_id=user_id,
                project_id=project_id,
                session_id=session_id,
                content=content,
                memory_type="conversation",
                importance="medium",
                tags=["conversation", "qa"],
                metadata=context or {}
            )
            
            logger.debug(f"[CORE_MEMORY] Added session memory for session {session_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to add session memory: {e}")
            return ""
    
    def get_session_memory_context(self, user_id: str, project_id: str, session_id: str,
                                  question: str, limit: int = 5) -> Tuple[str, str]:
        """Get memory context for a specific session"""
        try:
            if not self.session_memory:
                return "", ""
            
            # Get recent session memories
            recent_memories = self.session_memory.get_session_memories(
                user_id, project_id, session_id, memory_type="conversation", limit=limit
            )
            
            recent_context = ""
            if recent_memories:
                recent_context = "\n\n".join([mem["content"] for mem in recent_memories])
            
            # Get semantic context from session memories
            semantic_memories = self.session_memory.search_session_memories(
                user_id, project_id, session_id, question, self.embedder, limit=3
            )
            
            semantic_context = ""
            if semantic_memories:
                semantic_context = "\n\n".join([mem["content"] for mem, score in semantic_memories])
            
            return recent_context, semantic_context
            
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to get session memory context: {e}")
            return "", ""
    
    def clear_session_memories(self, user_id: str, project_id: str, session_id: str):
        """Clear all memories for a specific session"""
        try:
            if not self.session_memory:
                return 0
            
            deleted_count = self.session_memory.clear_session_memories(user_id, project_id, session_id)
            logger.info(f"[CORE_MEMORY] Cleared {deleted_count} session memories for session {session_id}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"[CORE_MEMORY] Failed to clear session memories: {e}")
            return 0
    
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
        """Get context from enhanced memory system with semantic selection"""
        try:
            # Get recent conversation memories
            recent_memories = self.enhanced_memory.get_memories(
                user_id=user_id,
                memory_type="conversation",
                limit=5
            )
            
            recent_context = ""
            if recent_memories and self.embedder:
                # Use semantic similarity to select most relevant recent memories
                try:
                    from memo.context import semantic_context
                    recent_summaries = [m["summary"] for m in recent_memories]
                    recent_context = await semantic_context(question, recent_summaries, self.embedder, 3)
                except Exception as e:
                    logger.warning(f"[CORE_MEMORY] Semantic recent context failed, using all: {e}")
                    recent_context = "\n\n".join([m["summary"] for m in recent_memories])
            elif recent_memories:
                recent_context = "\n\n".join([m["summary"] for m in recent_memories])
            
            # Get semantic context from other memory types
            semantic_memories = self.enhanced_memory.get_memories(
                user_id=user_id,
                limit=10
            )
            
            semantic_context = ""
            if semantic_memories and self.embedder:
                try:
                    from memo.context import semantic_context
                    other_memories = [m for m in semantic_memories if m.get("memory_type") != "conversation"]
                    if other_memories:
                        other_summaries = [m["summary"] for m in other_memories]
                        semantic_context = await semantic_context(question, other_summaries, self.embedder, 5)
                except Exception as e:
                    logger.warning(f"[CORE_MEMORY] Semantic context failed, using all: {e}")
                    other_memories = [m for m in semantic_memories if m.get("memory_type") != "conversation"]
                    if other_memories:
                        semantic_context = "\n\n".join([m["summary"] for m in other_memories])
            elif semantic_memories:
                other_memories = [m for m in semantic_memories if m.get("memory_type") != "conversation"]
                if other_memories:
                    semantic_context = "\n\n".join([m["summary"] for m in other_memories])
            
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

# def reset_memory_system():
#     """Reset the global memory system (for testing)"""
#     global _memory_system
#     _memory_system = None
