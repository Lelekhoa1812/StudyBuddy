# ────────────────────────────── memo/retrieval.py ──────────────────────────────
"""
Context Retrieval and Enhancement

Handles intelligent context retrieval, enhancement decisions,
and input optimization for natural conversation flow.
"""

import re
from typing import List, Dict, Any, Tuple, Optional

from utils.logger import get_logger
from utils.rag.embeddings import EmbeddingClient
from memo.context import cosine_similarity, semantic_context

logger = get_logger("RETRIEVAL_MANAGER", __name__)

class RetrievalManager:
    """
    Manages context retrieval and enhancement for conversations.
    """
    
    def __init__(self, memory_system, embedder: EmbeddingClient):
        self.memory_system = memory_system
        self.embedder = embedder
    
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
            # Use the new memory planning system from core memory
            return await self.memory_system.get_smart_context(
                user_id, question, nvidia_rotator, project_id, conversation_mode
            )
            
        except Exception as e:
            logger.error(f"[RETRIEVAL_MANAGER] Smart context failed: {e}")
            # Fallback to legacy approach
            try:
                return await self._get_legacy_smart_context(
                    user_id, question, nvidia_rotator, project_id, conversation_mode
                )
            except Exception as fallback_error:
                logger.error(f"[RETRIEVAL_MANAGER] Legacy fallback also failed: {fallback_error}")
                return "", "", {"error": str(e)}
    
    async def _get_legacy_smart_context(self, user_id: str, question: str, 
                                      nvidia_rotator=None, project_id: Optional[str] = None,
                                      conversation_mode: str = "chat") -> Tuple[str, str, Dict[str, Any]]:
        """Legacy smart context retrieval as fallback"""
        try:
            # Check for conversation session continuity
            from memo.sessions import get_session_manager
            session_manager = get_session_manager()
            session_info = session_manager.get_or_create_session(user_id, question, conversation_mode)
            
            # Get enhanced context based on conversation state
            if session_info["is_continuation"]:
                recent_context, semantic_context = await self._get_continuation_context(
                    user_id, question, session_info, nvidia_rotator, project_id
                )
            else:
                recent_context, semantic_context = await self._get_fresh_context(
                    user_id, question, nvidia_rotator, project_id
                )
            
            # Enhance question/instructions with context if beneficial
            enhanced_input, context_used = await self._enhance_input_with_context(
                question, recent_context, semantic_context, nvidia_rotator, conversation_mode, user_id
            )
            
            # Update session tracking
            session_manager.update_session(user_id, question, enhanced_input, context_used)
            
            # Prepare metadata
            metadata = {
                "session_id": session_info["session_id"],
                "is_continuation": session_info["is_continuation"],
                "context_enhanced": context_used,
                "enhanced_input": enhanced_input,
                "conversation_depth": session_info["depth"],
                "last_activity": session_info["last_activity"],
                "legacy_mode": True
            }
            
            return recent_context, semantic_context, metadata
            
        except Exception as e:
            logger.error(f"[RETRIEVAL_MANAGER] Legacy smart context failed: {e}")
            return "", "", {"error": str(e)}
    
    async def _get_continuation_context(self, user_id: str, question: str, 
                                      session_info: Dict[str, Any], nvidia_rotator, 
                                      project_id: Optional[str]) -> Tuple[str, str]:
        """Get context for conversation continuation"""
        try:
            # Use enhanced context retrieval with focus on recent conversation
            if self.memory_system.is_enhanced_available():
                recent_context, semantic_context = await self.memory_system.get_conversation_context(
                    user_id, question, project_id
                )
            else:
                # Fallback to legacy with enhanced selection
                recent_memories = self.memory_system.recent(user_id, 5)  # More recent for continuation
                rest_memories = self.memory_system.rest(user_id, 5)
                
                recent_context = ""
                if recent_memories and nvidia_rotator:
                    try:
                        from memo.nvidia import related_recent_context
                        recent_context = await related_recent_context(question, recent_memories, nvidia_rotator)
                    except Exception as e:
                        logger.warning(f"[RETRIEVAL_MANAGER] NVIDIA recent context failed: {e}")
                        recent_context = await semantic_context(question, recent_memories, self.embedder, 3)
                
                semantic_context = ""
                if rest_memories:
                    semantic_context = await semantic_context(question, rest_memories, self.embedder, 5)
            
            return recent_context, semantic_context
            
        except Exception as e:
            logger.error(f"[RETRIEVAL_MANAGER] Continuation context failed: {e}")
            return "", ""
    
    async def _get_fresh_context(self, user_id: str, question: str, 
                               nvidia_rotator, project_id: Optional[str]) -> Tuple[str, str]:
        """Get context for fresh conversation or context switch"""
        try:
            # Use standard context retrieval
            if self.memory_system.is_enhanced_available():
                recent_context, semantic_context = await self.memory_system.get_conversation_context(
                    user_id, question, project_id
                )
            else:
                # Legacy fallback
                recent_memories = self.memory_system.recent(user_id, 3)
                rest_memories = self.memory_system.rest(user_id, 3)
                
                recent_context = await semantic_context(question, recent_memories, self.embedder, 2)
                semantic_context = await semantic_context(question, rest_memories, self.embedder, 3)
            
            return recent_context, semantic_context
            
        except Exception as e:
            logger.error(f"[RETRIEVAL_MANAGER] Fresh context failed: {e}")
            return "", ""
    
    async def _enhance_input_with_context(self, original_input: str, recent_context: str, 
                                        semantic_context: str, nvidia_rotator, 
                                        conversation_mode: str, user_id: str = "") -> Tuple[str, bool]:
        """Enhance input with relevant context if beneficial"""
        try:
            # Determine if enhancement would be beneficial
            should_enhance = await self._should_enhance_input(
                original_input, recent_context, semantic_context, nvidia_rotator, user_id
            )
            
            if not should_enhance:
                return original_input, False
            
            # Enhance based on conversation mode
            if conversation_mode == "chat":
                return await self._enhance_question(original_input, recent_context, semantic_context, nvidia_rotator, user_id)
            else:  # report mode
                return await self._enhance_instructions(original_input, recent_context, semantic_context, nvidia_rotator, user_id)
                
        except Exception as e:
            logger.warning(f"[RETRIEVAL_MANAGER] Input enhancement failed: {e}")
            return original_input, False
    
    async def _should_enhance_input(self, original_input: str, recent_context: str, 
                                  semantic_context: str, nvidia_rotator, user_id: str = "") -> bool:
        """Determine if input should be enhanced with context"""
        try:
            # Don't enhance if no context available
            if not recent_context and not semantic_context:
                return False
            
            # Don't enhance very specific questions that seem complete
            if len(original_input.split()) > 20:  # Long, detailed questions
                return False
            
            # Don't enhance if input already contains context indicators
            context_indicators = ["based on", "from our", "as we discussed", "following up", "regarding"]
            if any(indicator in original_input.lower() for indicator in context_indicators):
                return False
            
            # Use NVIDIA to determine if enhancement would be helpful
            if nvidia_rotator:
                try:
                    from utils.api.router import generate_answer_with_model
                    
                    sys_prompt = """You are an expert at determining if a user's question would benefit from additional context.

Given a user's question and available context, determine if enhancing the question with context would:
1. Make the answer more relevant and helpful
2. Provide better continuity in conversation
3. Not make the question unnecessarily complex

Respond with only "YES" or "NO"."""
                    
                    user_prompt = f"""USER QUESTION: {original_input}

AVAILABLE CONTEXT:
Recent: {recent_context[:200]}...
Semantic: {semantic_context[:200]}...

Should this question be enhanced with context?"""
                    
                    # Track memory agent usage
                    try:
                        from utils.analytics import get_analytics_tracker
                        tracker = get_analytics_tracker()
                        if tracker and user_id:
                            await tracker.track_agent_usage(
                                user_id=user_id,
                                agent_name="memory",
                                action="enhance",
                                context="enhancement_decision",
                                metadata={"input": original_input[:100]}
                            )
                    except Exception:
                        pass
                    
                    # Use Qwen for better context enhancement reasoning
                    from utils.api.router import qwen_chat_completion
                    response = await qwen_chat_completion(sys_prompt, user_prompt, nvidia_rotator, user_id, "enhancement_decision")
                    
                    return "YES" in response.upper()
                    
                except Exception as e:
                    logger.warning(f"[RETRIEVAL_MANAGER] Enhancement decision failed: {e}")
            
            # Fallback: enhance if we have substantial context
            total_context_length = len(recent_context) + len(semantic_context)
            return total_context_length > 100
            
        except Exception as e:
            logger.warning(f"[RETRIEVAL_MANAGER] Enhancement decision failed: {e}")
            return False
    
    async def _enhance_question(self, question: str, recent_context: str, 
                              semantic_context: str, nvidia_rotator, user_id: str = "") -> Tuple[str, bool]:
        """Enhance question with context"""
        try:
            from utils.api.router import generate_answer_with_model
            
            sys_prompt = """You are an expert at enhancing user questions with relevant conversation context.

Given a user's question and relevant context, create an enhanced question that:
1. Incorporates the context naturally and seamlessly
2. Maintains the user's original intent
3. Provides better context for answering
4. Flows naturally and doesn't sound forced

Return ONLY the enhanced question, no meta-commentary."""
            
            context_text = ""
            if recent_context:
                context_text += f"Recent conversation:\n{recent_context}\n\n"
            if semantic_context:
                context_text += f"Related information:\n{semantic_context}\n\n"
            
            user_prompt = f"""ORIGINAL QUESTION: {question}

RELEVANT CONTEXT:
{context_text}

Create an enhanced version that incorporates this context naturally."""
            
            # Track memory agent usage
            try:
                from utils.analytics import get_analytics_tracker
                tracker = get_analytics_tracker()
                if tracker and user_id:
                    await tracker.track_agent_usage(
                        user_id=user_id,
                        agent_name="memory",
                        action="enhance",
                        context="question_enhancement",
                        metadata={"question": question[:100]}
                    )
            except Exception:
                pass
            
            # Use Qwen for better question enhancement reasoning
            from utils.api.router import qwen_chat_completion
            enhanced_question = await qwen_chat_completion(sys_prompt, user_prompt, nvidia_rotator, user_id, "question_enhancement")
            
            return enhanced_question.strip(), True
            
        except Exception as e:
            logger.warning(f"[RETRIEVAL_MANAGER] Question enhancement failed: {e}")
            return question, False
    
    async def _enhance_instructions(self, instructions: str, recent_context: str, 
                                  semantic_context: str, nvidia_rotator, user_id: str = "") -> Tuple[str, bool]:
        """Enhance report instructions with context"""
        try:
            from utils.api.router import generate_answer_with_model
            
            sys_prompt = """You are an expert at enhancing report instructions with relevant conversation context.

Given report instructions and relevant context, create enhanced instructions that:
1. Incorporates the context naturally and seamlessly
2. Maintains the user's original intent for the report
3. Provides better context for generating a comprehensive report
4. Flows naturally and doesn't sound forced

Return ONLY the enhanced instructions, no meta-commentary."""
            
            context_text = ""
            if recent_context:
                context_text += f"Recent conversation:\n{recent_context}\n\n"
            if semantic_context:
                context_text += f"Related information:\n{semantic_context}\n\n"
            
            user_prompt = f"""ORIGINAL REPORT INSTRUCTIONS: {instructions}

RELEVANT CONTEXT:
{context_text}

Create an enhanced version that incorporates this context naturally."""
            
            # Track memory agent usage
            try:
                from utils.analytics import get_analytics_tracker
                tracker = get_analytics_tracker()
                if tracker and user_id:
                    await tracker.track_agent_usage(
                        user_id=user_id,
                        agent_name="memory",
                        action="enhance",
                        context="instruction_enhancement",
                        metadata={"instructions": instructions[:100]}
                    )
            except Exception:
                pass
            
            # Use Qwen for better instruction enhancement reasoning
            from utils.api.router import qwen_chat_completion
            enhanced_instructions = await qwen_chat_completion(sys_prompt, user_prompt, nvidia_rotator, user_id, "instruction_enhancement")
            
            return enhanced_instructions.strip(), True
            
        except Exception as e:
            logger.warning(f"[RETRIEVAL_MANAGER] Instructions enhancement failed: {e}")
            return instructions, False
    
    async def get_enhancement_context(self, user_id: str, question: str, 
                                    nvidia_rotator=None, project_id: Optional[str] = None) -> Tuple[str, str, Dict[str, Any]]:
        """Get context specifically optimized for enhancement requests"""
        try:
            # Use the core memory system's enhancement context method
            return await self.memory_system.get_enhancement_context(
                user_id, question, nvidia_rotator, project_id
            )
            
        except Exception as e:
            logger.error(f"[RETRIEVAL_MANAGER] Enhancement context failed: {e}")
            return "", "", {"error": str(e)}


# ────────────────────────────── Global Instance ──────────────────────────────

_retrieval_manager: Optional[RetrievalManager] = None

def get_retrieval_manager(memory_system=None, embedder: EmbeddingClient = None) -> RetrievalManager:
    """Get the global retrieval manager instance"""
    global _retrieval_manager
    
    if _retrieval_manager is None:
        if not memory_system:
            from memo.core import get_memory_system
            memory_system = get_memory_system()
        if not embedder:
            from utils.rag.embeddings import EmbeddingClient
            embedder = EmbeddingClient()
        
        _retrieval_manager = RetrievalManager(memory_system, embedder)
        logger.info("[RETRIEVAL_MANAGER] Global retrieval manager initialized")
    
    return _retrieval_manager

# def reset_retrieval_manager():
#     """Reset the global retrieval manager (for testing)"""
#     global _retrieval_manager
#     _retrieval_manager = None