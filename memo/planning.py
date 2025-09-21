# ────────────────────────────── memo/planning.py ──────────────────────────────
"""
Memory Planning Strategy

Intelligent memory planning system that analyzes user intent and determines
the optimal memory retrieval strategy, especially for enhancement requests.
"""

import re
from typing import List, Dict, Any, Tuple, Optional, Set
from enum import Enum

from utils.logger import get_logger
from utils.rag.embeddings import EmbeddingClient

logger = get_logger("MEMORY_PLANNER", __name__)

class QueryIntent(Enum):
    """Types of user query intents"""
    ENHANCEMENT = "enhancement"  # User wants more details/elaboration
    CLARIFICATION = "clarification"  # User wants clarification
    CONTINUATION = "continuation"  # User is continuing previous topic
    NEW_TOPIC = "new_topic"  # User is starting a new topic
    COMPARISON = "comparison"  # User wants to compare with previous content
    REFERENCE = "reference"  # User is referencing specific past content

class MemoryStrategy(Enum):
    """Memory retrieval strategies"""
    FOCUSED_QA = "focused_qa"  # Focus on past Q&A pairs
    BROAD_CONTEXT = "broad_context"  # Use broad semantic context
    RECENT_FOCUS = "recent_focus"  # Focus on recent memories
    SEMANTIC_DEEP = "semantic_deep"  # Deep semantic search
    MIXED_APPROACH = "mixed_approach"  # Combine multiple strategies

class MemoryPlanner:
    """
    Intelligent memory planning system that determines optimal memory retrieval
    strategy based on user intent and query characteristics.
    """
    
    def __init__(self, memory_system, embedder: EmbeddingClient):
        self.memory_system = memory_system
        self.embedder = embedder
        
        # Enhancement request patterns
        self.enhancement_patterns = [
            r'\b(enhance|elaborate|expand|detail|elaborate on|be more detailed|more details|more information)\b',
            r'\b(explain more|tell me more|go deeper|dive deeper|more context)\b',
            r'\b(what else|anything else|additional|further|supplement)\b',
            r'\b(comprehensive|thorough|complete|full)\b',
            r'\b(based on|from our|as we discussed|following up|regarding)\b'
        ]
        
        # Clarification patterns
        self.clarification_patterns = [
            r'\b(what do you mean|clarify|explain|what is|define)\b',
            r'\b(how does|why does|when does|where does)\b',
            r'\b(can you explain|help me understand)\b'
        ]
        
        # Comparison patterns
        self.comparison_patterns = [
            r'\b(compare|versus|vs|difference|similar|different)\b',
            r'\b(like|unlike|similar to|different from)\b',
            r'\b(contrast|opposite|better|worse)\b'
        ]
        
        # Reference patterns
        self.reference_patterns = [
            r'\b(you said|we discussed|earlier|before|previously)\b',
            r'\b(that|this|it|the above|mentioned)\b',
            r'\b(according to|based on|from|in)\b'
        ]
    
    async def plan_memory_strategy(self, user_id: str, question: str, 
                                 nvidia_rotator=None, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Plan the optimal memory retrieval strategy based on user intent and context.
        
        Args:
            user_id: User identifier
            question: Current user question/instruction
            nvidia_rotator: NVIDIA API rotator for AI analysis
            project_id: Project context
            
        Returns:
            Dictionary containing strategy, intent, and retrieval parameters
        """
        try:
            # Detect user intent
            intent = await self._detect_user_intent(question, nvidia_rotator)
            
            # Get conversation context for better planning
            conversation_context = await self._get_conversation_context(user_id, question)
            
            # Determine memory strategy based on intent and context
            strategy = self._determine_memory_strategy(intent, question, conversation_context)
            
            # Plan specific retrieval parameters
            retrieval_params = await self._plan_retrieval_parameters(
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
            return self._get_fallback_plan()
    
    async def _detect_user_intent(self, question: str, nvidia_rotator) -> QueryIntent:
        """Detect user intent from the question"""
        try:
            question_lower = question.lower()
            
            # Check for enhancement patterns
            if any(re.search(pattern, question_lower) for pattern in self.enhancement_patterns):
                return QueryIntent.ENHANCEMENT
            
            # Check for clarification patterns
            if any(re.search(pattern, question_lower) for pattern in self.clarification_patterns):
                return QueryIntent.CLARIFICATION
            
            # Check for comparison patterns
            if any(re.search(pattern, question_lower) for pattern in self.comparison_patterns):
                return QueryIntent.COMPARISON
            
            # Check for reference patterns
            if any(re.search(pattern, question_lower) for pattern in self.reference_patterns):
                return QueryIntent.REFERENCE
            
            # Use AI for more sophisticated intent detection
            if nvidia_rotator:
                try:
                    return await self._ai_intent_detection(question, nvidia_rotator)
                except Exception as e:
                    logger.warning(f"[MEMORY_PLANNER] AI intent detection failed: {e}")
            
            # Default to continuation if no clear patterns
            return QueryIntent.CONTINUATION
            
        except Exception as e:
            logger.warning(f"[MEMORY_PLANNER] Intent detection failed: {e}")
            return QueryIntent.CONTINUATION
    
    async def _ai_intent_detection(self, question: str, nvidia_rotator) -> QueryIntent:
        """Use AI to detect user intent more accurately"""
        try:
            from utils.api.router import generate_answer_with_model
            
            sys_prompt = """You are an expert at analyzing user intent in questions.

Classify the user's question into one of these intents:
- ENHANCEMENT: User wants more details, elaboration, or comprehensive information
- CLARIFICATION: User wants explanation or clarification of something
- CONTINUATION: User is continuing a previous topic or conversation
- NEW_TOPIC: User is starting a completely new topic
- COMPARISON: User wants to compare or contrast things
- REFERENCE: User is referencing specific past content or discussions

Respond with only the intent name (e.g., "ENHANCEMENT")."""
            
            user_prompt = f"Question: {question}\n\nWhat is the user's intent?"
            
            selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
            response = await generate_answer_with_model(
                selection=selection,
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                gemini_rotator=None,
                nvidia_rotator=nvidia_rotator
            )
            
            # Parse response
            response_upper = response.strip().upper()
            for intent in QueryIntent:
                if intent.name in response_upper:
                    return intent
            
            return QueryIntent.CONTINUATION
            
        except Exception as e:
            logger.warning(f"[MEMORY_PLANNER] AI intent detection failed: {e}")
            return QueryIntent.CONTINUATION
    
    def _determine_memory_strategy(self, intent: QueryIntent, question: str, 
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
            logger.warning(f"[MEMORY_PLANNER] Strategy determination failed: {e}")
            return MemoryStrategy.MIXED_APPROACH
    
    async def _plan_retrieval_parameters(self, user_id: str, question: str, intent: QueryIntent,
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
            logger.warning(f"[MEMORY_PLANNER] Parameter planning failed: {e}")
            return {
                "recent_limit": 3,
                "semantic_limit": 5,
                "qa_focus": False,
                "enhancement_mode": False,
                "priority_types": ["conversation"],
                "similarity_threshold": 0.15,
                "use_ai_selection": False
            }
    
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
    
    def _get_fallback_plan(self) -> Dict[str, Any]:
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
    
    async def execute_memory_plan(self, user_id: str, question: str, execution_plan: Dict[str, Any],
                                 nvidia_rotator=None, project_id: Optional[str] = None) -> Tuple[str, str, Dict[str, Any]]:
        """
        Execute the planned memory retrieval strategy.
        
        Returns:
            Tuple of (recent_context, semantic_context, metadata)
        """
        try:
            params = execution_plan["retrieval_params"]
            strategy = execution_plan["strategy"]
            intent = execution_plan["intent"]
            
            # Execute based on strategy
            if strategy == MemoryStrategy.FOCUSED_QA:
                return await self._execute_focused_qa_retrieval(
                    user_id, question, params, nvidia_rotator, project_id
                )
            elif strategy == MemoryStrategy.RECENT_FOCUS:
                return await self._execute_recent_focus_retrieval(
                    user_id, question, params, nvidia_rotator, project_id
                )
            elif strategy == MemoryStrategy.BROAD_CONTEXT:
                return await self._execute_broad_context_retrieval(
                    user_id, question, params, nvidia_rotator, project_id
                )
            elif strategy == MemoryStrategy.SEMANTIC_DEEP:
                return await self._execute_semantic_deep_retrieval(
                    user_id, question, params, nvidia_rotator, project_id
                )
            else:  # MIXED_APPROACH
                return await self._execute_mixed_approach_retrieval(
                    user_id, question, params, nvidia_rotator, project_id
                )
                
        except Exception as e:
            logger.error(f"[MEMORY_PLANNER] Plan execution failed: {e}")
            return "", "", {"error": str(e)}
    
    async def _execute_focused_qa_retrieval(self, user_id: str, question: str, params: Dict[str, Any],
                                          nvidia_rotator, project_id: Optional[str]) -> Tuple[str, str, Dict[str, Any]]:
        """Execute focused Q&A retrieval for enhancement requests"""
        try:
            recent_context = ""
            semantic_context = ""
            metadata = {"strategy": "focused_qa", "qa_focus": True}
            
            if self.memory_system.is_enhanced_available():
                # Get Q&A focused memories
                qa_memories = self.memory_system.enhanced_memory.get_memories(
                    user_id, memory_type="conversation", limit=params["recent_limit"]
                )
                
                if qa_memories:
                    # Use AI to select most relevant Q&A pairs for enhancement
                    if params["use_ai_selection"] and nvidia_rotator:
                        recent_context = await self._ai_select_qa_memories(
                            question, qa_memories, nvidia_rotator, "recent"
                        )
                    else:
                        recent_context = await self._semantic_select_qa_memories(
                            question, qa_memories, params["similarity_threshold"]
                        )
                
                # Get additional semantic Q&A context
                all_memories = self.memory_system.enhanced_memory.get_memories(
                    user_id, limit=params["semantic_limit"]
                )
                
                if all_memories:
                    if params["use_ai_selection"] and nvidia_rotator:
                        semantic_context = await self._ai_select_qa_memories(
                            question, all_memories, nvidia_rotator, "semantic"
                        )
                    else:
                        semantic_context = await self._semantic_select_qa_memories(
                            question, all_memories, params["similarity_threshold"]
                        )
            else:
                # Legacy fallback
                recent_memories = self.memory_system.recent(user_id, params["recent_limit"])
                rest_memories = self.memory_system.rest(user_id, params["recent_limit"])
                
                if recent_memories:
                    recent_context = await self._semantic_select_qa_memories(
                        question, [{"content": m} for m in recent_memories], params["similarity_threshold"]
                    )
                
                if rest_memories:
                    semantic_context = await self._semantic_select_qa_memories(
                        question, [{"content": m} for m in rest_memories], params["similarity_threshold"]
                    )
            
            metadata["enhancement_focus"] = True
            metadata["qa_memories_found"] = len(recent_context) > 0 or len(semantic_context) > 0
            
            return recent_context, semantic_context, metadata
            
        except Exception as e:
            logger.error(f"[MEMORY_PLANNER] Focused Q&A retrieval failed: {e}")
            return "", "", {"error": str(e)}
    
    async def _execute_recent_focus_retrieval(self, user_id: str, question: str, params: Dict[str, Any],
                                            nvidia_rotator, project_id: Optional[str]) -> Tuple[str, str, Dict[str, Any]]:
        """Execute recent focus retrieval for clarification requests"""
        try:
            recent_context = ""
            semantic_context = ""
            metadata = {"strategy": "recent_focus"}
            
            if self.memory_system.is_enhanced_available():
                recent_memories = self.memory_system.enhanced_memory.get_memories(
                    user_id, memory_type="conversation", limit=params["recent_limit"]
                )
                
                if recent_memories:
                    recent_context = "\n\n".join([m["content"] for m in recent_memories])
                
                # Get some semantic context
                all_memories = self.memory_system.enhanced_memory.get_memories(
                    user_id, limit=params["semantic_limit"]
                )
                
                if all_memories:
                    semantic_context = await self._semantic_select_qa_memories(
                        question, all_memories, params["similarity_threshold"]
                    )
            else:
                # Legacy fallback
                recent_memories = self.memory_system.recent(user_id, params["recent_limit"])
                rest_memories = self.memory_system.rest(user_id, params["recent_limit"])
                
                recent_context = "\n\n".join(recent_memories)
                
                if rest_memories:
                    semantic_context = await self._semantic_select_qa_memories(
                        question, [{"content": m} for m in rest_memories], params["similarity_threshold"]
                    )
            
            return recent_context, semantic_context, metadata
            
        except Exception as e:
            logger.error(f"[MEMORY_PLANNER] Recent focus retrieval failed: {e}")
            return "", "", {"error": str(e)}
    
    async def _execute_broad_context_retrieval(self, user_id: str, question: str, params: Dict[str, Any],
                                             nvidia_rotator, project_id: Optional[str]) -> Tuple[str, str, Dict[str, Any]]:
        """Execute broad context retrieval for comparison requests"""
        try:
            recent_context = ""
            semantic_context = ""
            metadata = {"strategy": "broad_context"}
            
            if self.memory_system.is_enhanced_available():
                # Get recent context
                recent_memories = self.memory_system.enhanced_memory.get_memories(
                    user_id, memory_type="conversation", limit=params["recent_limit"]
                )
                
                if recent_memories:
                    recent_context = "\n\n".join([m["content"] for m in recent_memories])
                
                # Get broad semantic context
                all_memories = self.memory_system.enhanced_memory.get_memories(
                    user_id, limit=params["semantic_limit"]
                )
                
                if all_memories:
                    semantic_context = await self._semantic_select_qa_memories(
                        question, all_memories, params["similarity_threshold"]
                    )
            else:
                # Legacy fallback
                recent_memories = self.memory_system.recent(user_id, params["recent_limit"])
                rest_memories = self.memory_system.rest(user_id, params["recent_limit"])
                
                recent_context = "\n\n".join(recent_memories)
                semantic_context = "\n\n".join(rest_memories)
            
            return recent_context, semantic_context, metadata
            
        except Exception as e:
            logger.error(f"[MEMORY_PLANNER] Broad context retrieval failed: {e}")
            return "", "", {"error": str(e)}
    
    async def _execute_semantic_deep_retrieval(self, user_id: str, question: str, params: Dict[str, Any],
                                             nvidia_rotator, project_id: Optional[str]) -> Tuple[str, str, Dict[str, Any]]:
        """Execute semantic deep retrieval for new topics"""
        try:
            recent_context = ""
            semantic_context = ""
            metadata = {"strategy": "semantic_deep"}
            
            if self.memory_system.is_enhanced_available():
                # Get all memories for deep semantic search
                all_memories = self.memory_system.enhanced_memory.get_memories(
                    user_id, limit=params["semantic_limit"]
                )
                
                if all_memories:
                    if params["use_ai_selection"] and nvidia_rotator:
                        semantic_context = await self._ai_select_qa_memories(
                            question, all_memories, nvidia_rotator, "semantic"
                        )
                    else:
                        semantic_context = await self._semantic_select_qa_memories(
                            question, all_memories, params["similarity_threshold"]
                        )
                
                # Get some recent context
                recent_memories = self.memory_system.enhanced_memory.get_memories(
                    user_id, memory_type="conversation", limit=params["recent_limit"]
                )
                
                if recent_memories:
                    recent_context = "\n\n".join([m["content"] for m in recent_memories])
            else:
                # Legacy fallback
                all_memories = self.memory_system.all(user_id)
                recent_memories = self.memory_system.recent(user_id, params["recent_limit"])
                
                if all_memories:
                    semantic_context = await self._semantic_select_qa_memories(
                        question, [{"content": m} for m in all_memories], params["similarity_threshold"]
                    )
                
                recent_context = "\n\n".join(recent_memories)
            
            return recent_context, semantic_context, metadata
            
        except Exception as e:
            logger.error(f"[MEMORY_PLANNER] Semantic deep retrieval failed: {e}")
            return "", "", {"error": str(e)}
    
    async def _execute_mixed_approach_retrieval(self, user_id: str, question: str, params: Dict[str, Any],
                                              nvidia_rotator, project_id: Optional[str]) -> Tuple[str, str, Dict[str, Any]]:
        """Execute mixed approach retrieval for continuation requests"""
        try:
            recent_context = ""
            semantic_context = ""
            metadata = {"strategy": "mixed_approach"}
            
            if self.memory_system.is_enhanced_available():
                # Get recent context
                recent_memories = self.memory_system.enhanced_memory.get_memories(
                    user_id, memory_type="conversation", limit=params["recent_limit"]
                )
                
                if recent_memories:
                    if params["use_ai_selection"] and nvidia_rotator:
                        recent_context = await self._ai_select_qa_memories(
                            question, recent_memories, nvidia_rotator, "recent"
                        )
                    else:
                        recent_context = await self._semantic_select_qa_memories(
                            question, recent_memories, params["similarity_threshold"]
                        )
                
                # Get semantic context
                all_memories = self.memory_system.enhanced_memory.get_memories(
                    user_id, limit=params["semantic_limit"]
                )
                
                if all_memories:
                    if params["use_ai_selection"] and nvidia_rotator:
                        semantic_context = await self._ai_select_qa_memories(
                            question, all_memories, nvidia_rotator, "semantic"
                        )
                    else:
                        semantic_context = await self._semantic_select_qa_memories(
                            question, all_memories, params["similarity_threshold"]
                        )
            else:
                # Legacy fallback
                recent_memories = self.memory_system.recent(user_id, params["recent_limit"])
                rest_memories = self.memory_system.rest(user_id, params["recent_limit"])
                
                if recent_memories:
                    recent_context = await self._semantic_select_qa_memories(
                        question, [{"content": m} for m in recent_memories], params["similarity_threshold"]
                    )
                
                if rest_memories:
                    semantic_context = await self._semantic_select_qa_memories(
                        question, [{"content": m} for m in rest_memories], params["similarity_threshold"]
                    )
            
            return recent_context, semantic_context, metadata
            
        except Exception as e:
            logger.error(f"[MEMORY_PLANNER] Mixed approach retrieval failed: {e}")
            return "", "", {"error": str(e)}
    
    async def _ai_select_qa_memories(self, question: str, memories: List[Dict[str, Any]], 
                                   nvidia_rotator, context_type: str) -> str:
        """Use AI to select the most relevant Q&A memories"""
        try:
            from utils.api.router import generate_answer_with_model
            
            if not memories:
                return ""
            
            sys_prompt = f"""You are an expert at selecting the most relevant Q&A memories for {context_type} context.

Given a user's question and a list of Q&A memories, select the most relevant ones that would help provide a comprehensive and detailed answer.

Focus on:
1. Direct relevance to the question
2. Q&A pairs that provide supporting information
3. Memories that add context and depth
4. Past discussions that relate to the current question

Return ONLY the selected Q&A memories, concatenated together. If none are relevant, return nothing."""
            
            # Format memories for AI
            formatted_memories = []
            for i, memory in enumerate(memories):
                content = memory.get("content", "")
                if content:
                    formatted_memories.append(f"Memory {i+1}: {content}")
            
            user_prompt = f"""Question: {question}

Available Q&A Memories:
{chr(10).join(formatted_memories)}

Select the most relevant Q&A memories:"""
            
            selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
            response = await generate_answer_with_model(
                selection=selection,
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                gemini_rotator=None,
                nvidia_rotator=nvidia_rotator
            )
            
            return response.strip()
            
        except Exception as e:
            logger.warning(f"[MEMORY_PLANNER] AI Q&A selection failed: {e}")
            return ""
    
    async def _semantic_select_qa_memories(self, question: str, memories: List[Dict[str, Any]], 
                                         threshold: float) -> str:
        """Use semantic similarity to select Q&A memories"""
        try:
            if not memories:
                return ""
            
            # Extract content from memories
            memory_contents = [memory.get("content", "") for memory in memories if memory.get("content")]
            
            if not memory_contents:
                return ""
            
            # Use semantic similarity
            from memo.context import semantic_context
            selected = await semantic_context(question, memory_contents, self.embedder, len(memory_contents))
            
            return selected
            
        except Exception as e:
            logger.warning(f"[MEMORY_PLANNER] Semantic Q&A selection failed: {e}")
            return ""


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

# def reset_memory_planner():
#     """Reset the global memory planner (for testing)"""
#     global _memory_planner
#     _memory_planner = None
