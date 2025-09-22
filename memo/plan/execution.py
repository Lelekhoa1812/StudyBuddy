# ────────────────────────────── memo/plan/execution.py ──────────────────────────────
"""
Execution Engine

Handles memory retrieval execution based on planned strategies.
"""

from typing import List, Dict, Any, Tuple, Optional

from utils.logger import get_logger
from utils.rag.embeddings import EmbeddingClient
from memo.plan.intent import QueryIntent
from memo.plan.strategy import MemoryStrategy

logger = get_logger("EXECUTION_ENGINE", __name__)

class ExecutionEngine:
    """Handles memory retrieval execution based on planned strategies"""
    
    def __init__(self, memory_system, embedder: EmbeddingClient):
        self.memory_system = memory_system
        self.embedder = embedder
    
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
            logger.error(f"[EXECUTION_ENGINE] Plan execution failed: {e}")
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
            logger.error(f"[EXECUTION_ENGINE] Focused Q&A retrieval failed: {e}")
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
            logger.error(f"[EXECUTION_ENGINE] Recent focus retrieval failed: {e}")
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
            logger.error(f"[EXECUTION_ENGINE] Broad context retrieval failed: {e}")
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
            logger.error(f"[EXECUTION_ENGINE] Semantic deep retrieval failed: {e}")
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
            logger.error(f"[EXECUTION_ENGINE] Mixed approach retrieval failed: {e}")
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
            
            # Use DeepSeek for better memory selection reasoning
            from utils.api.router import deepseek_chat_completion
            response = await deepseek_chat_completion(sys_prompt, user_prompt, nvidia_rotator)
            
            return response.strip()
            
        except Exception as e:
            logger.warning(f"[EXECUTION_ENGINE] AI Q&A selection failed: {e}")
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
            logger.warning(f"[EXECUTION_ENGINE] Semantic Q&A selection failed: {e}")
            return ""


# ────────────────────────────── Global Instance ──────────────────────────────

_execution_engine: Optional[ExecutionEngine] = None

def get_execution_engine(memory_system=None, embedder: EmbeddingClient = None) -> ExecutionEngine:
    """Get the global execution engine instance"""
    global _execution_engine
    
    if _execution_engine is None:
        if not memory_system:
            from memo.core import get_memory_system
            memory_system = get_memory_system()
        if not embedder:
            from utils.rag.embeddings import EmbeddingClient
            embedder = EmbeddingClient()
        
        _execution_engine = ExecutionEngine(memory_system, embedder)
        logger.info("[EXECUTION_ENGINE] Global execution engine initialized")
    
    return _execution_engine
