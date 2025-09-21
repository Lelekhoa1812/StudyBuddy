# ────────────────────────────── memo/plan/strategy.py ──────────────────────────────
"""
Strategy Planning

Handles memory strategy planning and parameter optimization.
"""

from typing import List, Dict, Any, Tuple, Optional
from enum import Enum

from utils.logger import get_logger
from memo.plan.intent import QueryIntent

logger = get_logger("STRATEGY_PLANNER", __name__)

class MemoryStrategy(Enum):
    """Memory retrieval strategies"""
    FOCUSED_QA = "focused_qa"  # Focus on past Q&A pairs
    BROAD_CONTEXT = "broad_context"  # Use broad semantic context
    RECENT_FOCUS = "recent_focus"  # Focus on recent memories
    SEMANTIC_DEEP = "semantic_deep"  # Deep semantic search
    MIXED_APPROACH = "mixed_approach"  # Combine multiple strategies

class StrategyPlanner:
    """Handles memory strategy planning and parameter optimization"""
    
    def __init__(self):
        pass
    
    def determine_strategy(self, intent: QueryIntent, question: str, 
                          conversation_context: Dict[str, Any]) -> MemoryStrategy:
        """Determine the optimal memory retrieval strategy"""
        try:
            # Enhancement requests need focused Q&A retrieval
            if intent == QueryIntent.ENHANCEMENT:
                return MemoryStrategy.FOCUSED_QA
            
            # Clarification requests need recent context and Q&A
            if intent == QueryIntent.CLARIFICATION:
                return MemoryStrategy.RECENT_FOCUS
            
            # Comparison requests need broad context
            if intent == QueryIntent.COMPARISON:
                return MemoryStrategy.BROAD_CONTEXT
            
            # Reference requests need focused Q&A
            if intent == QueryIntent.REFERENCE:
                return MemoryStrategy.FOCUSED_QA
            
            # New topics need semantic deep search
            if intent == QueryIntent.NEW_TOPIC:
                return MemoryStrategy.SEMANTIC_DEEP
            
            # Continuation requests use mixed approach
            if intent == QueryIntent.CONTINUATION:
                return MemoryStrategy.MIXED_APPROACH
            
            # Default to mixed approach
            return MemoryStrategy.MIXED_APPROACH
            
        except Exception as e:
            logger.warning(f"[STRATEGY_PLANNER] Strategy determination failed: {e}")
            return MemoryStrategy.MIXED_APPROACH
    
    def plan_retrieval_parameters(self, user_id: str, question: str, intent: QueryIntent,
                                strategy: MemoryStrategy, conversation_context: Dict[str, Any],
                                nvidia_rotator) -> Dict[str, Any]:
        """Plan specific retrieval parameters based on strategy"""
        try:
            params = {
                "recent_limit": 3,
                "semantic_limit": 5,
                "qa_focus": False,
                "enhancement_mode": False,
                "priority_types": ["conversation"],
                "similarity_threshold": 0.15,
                "use_ai_selection": False
            }
            
            # Adjust parameters based on strategy
            if strategy == MemoryStrategy.FOCUSED_QA:
                params.update({
                    "recent_limit": 5,  # More recent Q&A pairs
                    "semantic_limit": 10,  # More semantic Q&A pairs
                    "qa_focus": True,
                    "enhancement_mode": True,
                    "priority_types": ["conversation", "qa"],
                    "similarity_threshold": 0.1,  # Lower threshold for more results
                    "use_ai_selection": True
                })
            
            elif strategy == MemoryStrategy.RECENT_FOCUS:
                params.update({
                    "recent_limit": 5,
                    "semantic_limit": 3,
                    "qa_focus": True,
                    "priority_types": ["conversation"]
                })
            
            elif strategy == MemoryStrategy.BROAD_CONTEXT:
                params.update({
                    "recent_limit": 3,
                    "semantic_limit": 15,
                    "qa_focus": False,
                    "priority_types": ["conversation", "general", "knowledge"],
                    "similarity_threshold": 0.2
                })
            
            elif strategy == MemoryStrategy.SEMANTIC_DEEP:
                params.update({
                    "recent_limit": 2,
                    "semantic_limit": 20,
                    "qa_focus": False,
                    "priority_types": ["conversation", "general", "knowledge", "qa"],
                    "similarity_threshold": 0.1,
                    "use_ai_selection": True
                })
            
            elif strategy == MemoryStrategy.MIXED_APPROACH:
                params.update({
                    "recent_limit": 4,
                    "semantic_limit": 8,
                    "qa_focus": True,
                    "priority_types": ["conversation", "qa"],
                    "use_ai_selection": True
                })
            
            # Special handling for enhancement requests
            if intent == QueryIntent.ENHANCEMENT:
                params["enhancement_mode"] = True
                params["qa_focus"] = True
                params["use_ai_selection"] = True
                params["similarity_threshold"] = 0.05  # Very low threshold for maximum recall
            
            return params
            
        except Exception as e:
            logger.warning(f"[STRATEGY_PLANNER] Parameter planning failed: {e}")
            return {
                "recent_limit": 3,
                "semantic_limit": 5,
                "qa_focus": False,
                "enhancement_mode": False,
                "priority_types": ["conversation"],
                "similarity_threshold": 0.15,
                "use_ai_selection": False
            }
    
    def get_fallback_plan(self) -> Dict[str, Any]:
        """Get fallback plan when planning fails"""
        return {
            "intent": QueryIntent.CONTINUATION,
            "strategy": MemoryStrategy.MIXED_APPROACH,
            "retrieval_params": {
                "recent_limit": 3,
                "semantic_limit": 5,
                "qa_focus": False,
                "enhancement_mode": False,
                "priority_types": ["conversation"],
                "similarity_threshold": 0.15,
                "use_ai_selection": False
            },
            "conversation_context": {},
            "enhancement_focus": False,
            "qa_focus": False
        }


# ────────────────────────────── Global Instance ──────────────────────────────

_strategy_planner: Optional[StrategyPlanner] = None

def get_strategy_planner() -> StrategyPlanner:
    """Get the global strategy planner instance"""
    global _strategy_planner
    
    if _strategy_planner is None:
        _strategy_planner = StrategyPlanner()
        logger.info("[STRATEGY_PLANNER] Global strategy planner initialized")
    
    return _strategy_planner
