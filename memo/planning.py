# ────────────────────────────── memo/planning.py ──────────────────────────────
"""
Memory Planning Coordinator

Main coordinator for the memory planning system that orchestrates
intent detection, strategy planning, and execution.
"""

from typing import List, Dict, Any, Tuple, Optional
import os

from utils.logger import get_logger
from utils.rag.embeddings import EmbeddingClient
from memo.plan.intent import QueryIntent, get_intent_detector
from memo.plan.strategy import MemoryStrategy, get_strategy_planner
from memo.plan.execution import get_execution_engine

logger = get_logger("MEMORY_PLANNER", __name__)

class MemoryPlanner:
    """
    Main coordinator for memory planning system.
    Orchestrates intent detection, strategy planning, and execution.
    """
    
    def __init__(self, memory_system, embedder: EmbeddingClient):
        self.memory_system = memory_system
        self.embedder = embedder
        self.intent_detector = get_intent_detector()
        self.strategy_planner = get_strategy_planner()
        self.execution_engine = get_execution_engine(memory_system, embedder)
    
    async def plan_memory_strategy(self, user_id: str, question: str, 
                                 nvidia_rotator=None, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Plan the optimal memory retrieval strategy based on user intent and context"""
        try:
            # Detect user intent
            intent = await self.intent_detector.detect_intent(question, nvidia_rotator)
            
            # Get conversation context for better planning
            conversation_context = await self._get_conversation_context(user_id, question)
            
            # Determine memory strategy based on intent and context
            strategy = self.strategy_planner.determine_strategy(intent, question, conversation_context)
            
            # Plan specific retrieval parameters
            retrieval_params = self.strategy_planner.plan_retrieval_parameters(
                user_id, question, intent, strategy, conversation_context, nvidia_rotator
            )
            
            # Create execution plan
            execution_plan = {
                "intent": intent,
                "strategy": strategy,
                "retrieval_params": retrieval_params,
                "conversation_context": conversation_context,
                "enhancement_focus": intent == QueryIntent.ENHANCEMENT,
                "qa_focus": intent in [QueryIntent.ENHANCEMENT, QueryIntent.CLARIFICATION, QueryIntent.REFERENCE]
            }
            
            logger.info(f"[MEMORY_PLANNER] Planned strategy: {strategy.value} for intent: {intent.value}")
            return execution_plan
            
        except Exception as e:
            logger.error(f"[MEMORY_PLANNER] Memory planning failed: {e}")
            return self.strategy_planner.get_fallback_plan()
    
    async def execute_memory_plan(self, user_id: str, question: str, execution_plan: Dict[str, Any],
                                 nvidia_rotator=None, project_id: Optional[str] = None) -> Tuple[str, str, Dict[str, Any]]:
        """Execute the planned memory retrieval strategy"""
        try:
            return await self.execution_engine.execute_memory_plan(
                user_id, question, execution_plan, nvidia_rotator, project_id
            )
        except Exception as e:
            logger.error(f"[MEMORY_PLANNER] Plan execution failed: {e}")
            return "", "", {"error": str(e)}
    
    async def _get_conversation_context(self, user_id: str, question: str) -> Dict[str, Any]:
        """Get conversation context for better planning"""
        try:
            context = {
                "has_recent_memories": False,
                "memory_count": 0,
                "conversation_depth": 0,
                "last_question": "",
                "is_continuation": False
            }
            
            if self.memory_system.is_enhanced_available():
                # Get enhanced memory stats
                stats = self.memory_system.get_memory_stats(user_id)
                context["memory_count"] = stats.get("total_memories", 0)
                
                # Get recent memories
                recent_memories = self.memory_system.enhanced_memory.get_memories(
                    user_id, memory_type="conversation", limit=5
                )
                context["has_recent_memories"] = len(recent_memories) > 0
                
                if recent_memories:
                    context["last_question"] = recent_memories[0].get("content", "")
            else:
                # Legacy memory stats
                recent_memories = self.memory_system.recent(user_id, 3)
                context["has_recent_memories"] = len(recent_memories) > 0
                context["memory_count"] = len(self.memory_system.all(user_id))
                
                if recent_memories:
                    context["last_question"] = recent_memories[0]
            
            return context
            
        except Exception as e:
            logger.warning(f"[MEMORY_PLANNER] Context retrieval failed: {e}")
            return {
                "has_recent_memories": False,
                "memory_count": 0,
                "conversation_depth": 0,
                "last_question": "",
                "is_continuation": False
            }


# ────────────────────────────── Global Instance ──────────────────────────────

_memory_planner: Optional[MemoryPlanner] = None

def get_memory_planner(memory_system=None, embedder: EmbeddingClient = None) -> MemoryPlanner:
    """Get the global memory planner instance"""
    global _memory_planner
    
    if _memory_planner is None:
        if not memory_system:
            from memo.core import get_memory_system
            memory_system = get_memory_system()
        if not embedder:
            from utils.rag.embeddings import EmbeddingClient
            embedder = EmbeddingClient()
        
        _memory_planner = MemoryPlanner(memory_system, embedder)
        logger.info("[MEMORY_PLANNER] Global memory planner initialized")
    
    return _memory_planner