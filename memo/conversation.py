# ────────────────────────────── memo/conversation.py ──────────────────────────────
"""
Advanced Conversation Management

Handles conversation continuity, context switching, memory consolidation,
and edge cases for natural conversational flow.
"""

import re
import time
from typing import List, Dict, Any, Tuple, Optional, Set
from datetime import datetime, timezone, timedelta

from utils.logger import get_logger
from utils.rag.embeddings import EmbeddingClient
from memo.context import cosine_similarity, semantic_context

logger = get_logger("CONVERSATION_MANAGER", __name__)

class ConversationManager:
    """
    Advanced conversation manager that handles:
    - Conversation continuity and context switching
    - Memory consolidation and pruning
    - Edge case handling for natural conversation flow
    - Intelligent context retrieval
    """
    
    def __init__(self, memory_system, embedder: EmbeddingClient):
        self.memory_system = memory_system
        self.embedder = embedder
        self.conversation_sessions = {}  # Track active conversation sessions
        self.context_cache = {}  # Cache recent context for performance
        self.memory_consolidation_threshold = 10  # Consolidate after 10 memories
        
    async def get_smart_context(self, user_id: str, question: str, 
                              nvidia_rotator=None, project_id: Optional[str] = None,
                              conversation_mode: str = "chat") -> Tuple[str, str, Dict[str, Any]]:
        """
        Get intelligent context for conversation with enhanced edge case handling.
        
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
            # Check for conversation session continuity
            session_info = self._get_or_create_session(user_id, question, conversation_mode)
            
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
                question, recent_context, semantic_context, nvidia_rotator, conversation_mode
            )
            
            # Update session tracking
            self._update_session(user_id, question, enhanced_input, context_used)
            
            # Prepare metadata
            metadata = {
                "session_id": session_info["session_id"],
                "is_continuation": session_info["is_continuation"],
                "context_enhanced": context_used,
                "conversation_depth": session_info["depth"],
                "last_activity": session_info["last_activity"]
            }
            
            return recent_context, semantic_context, metadata
            
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Smart context failed: {e}")
            return "", "", {"error": str(e)}
    
    async def consolidate_memories(self, user_id: str, nvidia_rotator=None) -> Dict[str, Any]:
        """
        Consolidate and prune memories to prevent information overload.
        """
        try:
            if not self.memory_system.is_enhanced_available():
                return {"consolidated": 0, "pruned": 0}
            
            # Get all memories for user
            all_memories = self.memory_system.enhanced_memory.get_memories(user_id, limit=100)
            
            if len(all_memories) < self.memory_consolidation_threshold:
                return {"consolidated": 0, "pruned": 0}
            
            # Group similar memories
            memory_groups = await self._group_similar_memories(all_memories, nvidia_rotator)
            
            # Consolidate each group
            consolidated_count = 0
            pruned_count = 0
            
            for group in memory_groups:
                if len(group) > 1:
                    # Consolidate similar memories
                    consolidated_memory = await self._consolidate_memory_group(group, nvidia_rotator)
                    
                    if consolidated_memory:
                        # Remove old memories and add consolidated one
                        for memory in group:
                            self.memory_system.enhanced_memory.memories.delete_one({"_id": memory["_id"]})
                            pruned_count += 1
                        
                        # Add consolidated memory
                        self.memory_system.enhanced_memory.add_memory(
                            user_id=user_id,
                            content=consolidated_memory["content"],
                            memory_type=consolidated_memory["memory_type"],
                            importance="high",  # Consolidated memories are important
                            tags=consolidated_memory["tags"] + ["consolidated"]
                        )
                        consolidated_count += 1
            
            logger.info(f"[CONVERSATION_MANAGER] Consolidated {consolidated_count} groups, pruned {pruned_count} memories")
            return {"consolidated": consolidated_count, "pruned": pruned_count}
            
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Memory consolidation failed: {e}")
            return {"consolidated": 0, "pruned": 0, "error": str(e)}
    
    async def handle_context_switch(self, user_id: str, new_question: str, 
                                  nvidia_rotator=None) -> Dict[str, Any]:
        """
        Handle context switching when user changes topics or asks unrelated questions.
        """
        try:
            session_info = self.conversation_sessions.get(user_id, {})
            
            if not session_info:
                return {"is_context_switch": False, "confidence": 0.0}
            
            # Check if this is a context switch
            is_switch, confidence = await self._detect_context_switch(
                session_info.get("last_question", ""), new_question, nvidia_rotator
            )
            
            if is_switch and confidence > 0.7:
                # Clear recent context cache for fresh start
                self.context_cache.pop(user_id, None)
                
                # Update session to indicate context switch
                session_info["context_switches"] = session_info.get("context_switches", 0) + 1
                session_info["last_context_switch"] = time.time()
                
                logger.info(f"[CONVERSATION_MANAGER] Context switch detected for user {user_id} (confidence: {confidence:.2f})")
                
                return {
                    "is_context_switch": True,
                    "confidence": confidence,
                    "switch_count": session_info["context_switches"]
                }
            
            return {"is_context_switch": False, "confidence": confidence}
            
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Context switch detection failed: {e}")
            return {"is_context_switch": False, "confidence": 0.0, "error": str(e)}
    
    def get_conversation_insights(self, user_id: str) -> Dict[str, Any]:
        """
        Get insights about the user's conversation patterns.
        """
        try:
            session_info = self.conversation_sessions.get(user_id, {})
            
            if not session_info:
                return {"status": "no_active_session"}
            
            return {
                "session_duration": time.time() - session_info.get("start_time", time.time()),
                "message_count": session_info.get("message_count", 0),
                "context_switches": session_info.get("context_switches", 0),
                "last_activity": session_info.get("last_activity", 0),
                "conversation_depth": session_info.get("depth", 0),
                "enhancement_rate": session_info.get("enhancement_rate", 0.0)
            }
            
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Failed to get conversation insights: {e}")
            return {"error": str(e)}
    
    # ────────────────────────────── Private Helper Methods ──────────────────────────────
    
    def _get_or_create_session(self, user_id: str, question: str, conversation_mode: str) -> Dict[str, Any]:
        """Get or create conversation session for user"""
        current_time = time.time()
        
        if user_id not in self.conversation_sessions:
            # New session
            self.conversation_sessions[user_id] = {
                "session_id": f"{user_id}_{int(current_time)}",
                "start_time": current_time,
                "last_activity": current_time,
                "message_count": 0,
                "context_switches": 0,
                "depth": 0,
                "enhancement_rate": 0.0,
                "conversation_mode": conversation_mode,
                "last_question": "",
                "is_continuation": False
            }
            return self.conversation_sessions[user_id]
        
        session = self.conversation_sessions[user_id]
        
        # Check if this is a continuation (within 30 minutes and same mode)
        time_since_last = current_time - session["last_activity"]
        is_continuation = (time_since_last < 1800 and  # 30 minutes
                          session["conversation_mode"] == conversation_mode)
        
        session["is_continuation"] = is_continuation
        session["last_activity"] = current_time
        session["message_count"] += 1
        
        return session
    
    def _update_session(self, user_id: str, original_question: str, 
                       enhanced_input: str, context_used: bool):
        """Update session with new information"""
        if user_id not in self.conversation_sessions:
            return
        
        session = self.conversation_sessions[user_id]
        session["last_question"] = original_question
        session["depth"] += 1
        
        # Update enhancement rate
        total_enhancements = session.get("total_enhancements", 0)
        if context_used:
            total_enhancements += 1
        session["total_enhancements"] = total_enhancements
        session["enhancement_rate"] = total_enhancements / session["message_count"]
    
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
                        logger.warning(f"[CONVERSATION_MANAGER] NVIDIA recent context failed: {e}")
                        recent_context = await semantic_context(question, recent_memories, self.embedder, 3)
                
                semantic_context = ""
                if rest_memories:
                    semantic_context = await semantic_context(question, rest_memories, self.embedder, 5)
            
            return recent_context, semantic_context
            
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Continuation context failed: {e}")
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
            logger.error(f"[CONVERSATION_MANAGER] Fresh context failed: {e}")
            return "", ""
    
    async def _enhance_input_with_context(self, original_input: str, recent_context: str, 
                                        semantic_context: str, nvidia_rotator, 
                                        conversation_mode: str) -> Tuple[str, bool]:
        """Enhance input with relevant context if beneficial"""
        try:
            # Determine if enhancement would be beneficial
            should_enhance = await self._should_enhance_input(
                original_input, recent_context, semantic_context, nvidia_rotator
            )
            
            if not should_enhance:
                return original_input, False
            
            # Enhance based on conversation mode
            if conversation_mode == "chat":
                return await self._enhance_question(original_input, recent_context, semantic_context, nvidia_rotator)
            else:  # report mode
                return await self._enhance_instructions(original_input, recent_context, semantic_context, nvidia_rotator)
                
        except Exception as e:
            logger.warning(f"[CONVERSATION_MANAGER] Input enhancement failed: {e}")
            return original_input, False
    
    async def _should_enhance_input(self, original_input: str, recent_context: str, 
                                  semantic_context: str, nvidia_rotator) -> bool:
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
                    
                    selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
                    response = await generate_answer_with_model(
                        selection=selection,
                        system_prompt=sys_prompt,
                        user_prompt=user_prompt,
                        gemini_rotator=None,
                        nvidia_rotator=nvidia_rotator
                    )
                    
                    return "YES" in response.upper()
                    
                except Exception as e:
                    logger.warning(f"[CONVERSATION_MANAGER] Enhancement decision failed: {e}")
            
            # Fallback: enhance if we have substantial context
            total_context_length = len(recent_context) + len(semantic_context)
            return total_context_length > 100
            
        except Exception as e:
            logger.warning(f"[CONVERSATION_MANAGER] Enhancement decision failed: {e}")
            return False
    
    async def _enhance_question(self, question: str, recent_context: str, 
                              semantic_context: str, nvidia_rotator) -> Tuple[str, bool]:
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
            
            selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
            enhanced_question = await generate_answer_with_model(
                selection=selection,
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                gemini_rotator=None,
                nvidia_rotator=nvidia_rotator
            )
            
            return enhanced_question.strip(), True
            
        except Exception as e:
            logger.warning(f"[CONVERSATION_MANAGER] Question enhancement failed: {e}")
            return question, False
    
    async def _enhance_instructions(self, instructions: str, recent_context: str, 
                                  semantic_context: str, nvidia_rotator) -> Tuple[str, bool]:
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
            
            selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
            enhanced_instructions = await generate_answer_with_model(
                selection=selection,
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                gemini_rotator=None,
                nvidia_rotator=nvidia_rotator
            )
            
            return enhanced_instructions.strip(), True
            
        except Exception as e:
            logger.warning(f"[CONVERSATION_MANAGER] Instructions enhancement failed: {e}")
            return instructions, False
    
    async def _detect_context_switch(self, last_question: str, new_question: str, 
                                   nvidia_rotator) -> Tuple[bool, float]:
        """Detect if user has switched context/topic"""
        try:
            if not last_question or not new_question:
                return False, 0.0
            
            if nvidia_rotator:
                try:
                    from utils.api.router import generate_answer_with_model
                    
                    sys_prompt = """You are an expert at detecting context switches in conversations.

Given two consecutive questions, determine if the user has switched to a completely different topic or context.

Consider:
- Different subject matter
- Different intent or goal
- No logical connection between questions
- Change in conversation direction

Respond with a JSON object: {"is_context_switch": true/false, "confidence": 0.0-1.0}"""
                    
                    user_prompt = f"""PREVIOUS QUESTION: {last_question}

CURRENT QUESTION: {new_question}

Is this a context switch?"""
                    
                    selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
                    response = await generate_answer_with_model(
                        selection=selection,
                        system_prompt=sys_prompt,
                        user_prompt=user_prompt,
                        gemini_rotator=None,
                        nvidia_rotator=nvidia_rotator
                    )
                    
                    # Parse JSON response
                    import json
                    try:
                        result = json.loads(response.strip())
                        return result.get("is_context_switch", False), result.get("confidence", 0.0)
                    except:
                        pass
                        
                except Exception as e:
                    logger.warning(f"[CONVERSATION_MANAGER] Context switch detection failed: {e}")
            
            # Fallback: simple keyword-based detection
            return self._simple_context_switch_detection(last_question, new_question)
            
        except Exception as e:
            logger.warning(f"[CONVERSATION_MANAGER] Context switch detection failed: {e}")
            return False, 0.0
    
    def _simple_context_switch_detection(self, last_question: str, new_question: str) -> Tuple[bool, float]:
        """Simple keyword-based context switch detection"""
        try:
            # Extract keywords from both questions
            last_words = set(re.findall(r'\b\w+\b', last_question.lower()))
            new_words = set(re.findall(r'\b\w+\b', new_question.lower()))
            
            # Calculate overlap
            overlap = len(last_words.intersection(new_words))
            total_unique = len(last_words.union(new_words))
            
            if total_unique == 0:
                return False, 0.0
            
            similarity = overlap / total_unique
            
            # Context switch if similarity is very low
            is_switch = similarity < 0.1
            confidence = 1.0 - similarity if is_switch else similarity
            
            return is_switch, confidence
            
        except Exception as e:
            logger.warning(f"[CONVERSATION_MANAGER] Simple context switch detection failed: {e}")
            return False, 0.0
    
    async def _group_similar_memories(self, memories: List[Dict[str, Any]], 
                                    nvidia_rotator) -> List[List[Dict[str, Any]]]:
        """Group similar memories for consolidation"""
        try:
            if not memories or len(memories) < 2:
                return [memories] if memories else []
            
            groups = []
            used = set()
            
            for i, memory in enumerate(memories):
                if i in used:
                    continue
                
                group = [memory]
                used.add(i)
                
                # Find similar memories
                for j, other_memory in enumerate(memories[i+1:], i+1):
                    if j in used:
                        continue
                    
                    # Calculate similarity
                    similarity = await self._calculate_memory_similarity(memory, other_memory, nvidia_rotator)
                    
                    if similarity > 0.7:  # High similarity threshold
                        group.append(other_memory)
                        used.add(j)
                
                groups.append(group)
            
            return groups
            
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Memory grouping failed: {e}")
            return [memories] if memories else []
    
    async def _calculate_memory_similarity(self, memory1: Dict[str, Any], 
                                         memory2: Dict[str, Any], nvidia_rotator) -> float:
        """Calculate similarity between two memories"""
        try:
            # Use embedding similarity if available
            if memory1.get("embedding") and memory2.get("embedding"):
                return cosine_similarity(
                    memory1["embedding"], 
                    memory2["embedding"]
                )
            
            # Fallback to content similarity
            content1 = memory1.get("content", "")
            content2 = memory2.get("content", "")
            
            if not content1 or not content2:
                return 0.0
            
            # Simple word overlap similarity
            words1 = set(re.findall(r'\b\w+\b', content1.lower()))
            words2 = set(re.findall(r'\b\w+\b', content2.lower()))
            
            if not words1 or not words2:
                return 0.0
            
            overlap = len(words1.intersection(words2))
            total = len(words1.union(words2))
            
            return overlap / total if total > 0 else 0.0
            
        except Exception as e:
            logger.warning(f"[CONVERSATION_MANAGER] Memory similarity calculation failed: {e}")
            return 0.0
    
    async def _consolidate_memory_group(self, group: List[Dict[str, Any]], 
                                      nvidia_rotator) -> Optional[Dict[str, Any]]:
        """Consolidate a group of similar memories into one"""
        try:
            if not group or len(group) < 2:
                return None
            
            # Extract content from all memories
            contents = [memory.get("content", "") for memory in group]
            memory_types = list(set(memory.get("memory_type", "conversation") for memory in group))
            tags = []
            for memory in group:
                tags.extend(memory.get("tags", []))
            
            # Use NVIDIA to consolidate content
            if nvidia_rotator:
                try:
                    from utils.api.router import generate_answer_with_model
                    
                    sys_prompt = """You are an expert at consolidating similar conversation memories.

Given multiple similar conversation memories, create a single consolidated memory that:
1. Preserves all important information
2. Removes redundancy
3. Maintains the essential context
4. Is concise but comprehensive

Return the consolidated content in the same format as the original memories."""
                    
                    user_prompt = f"""CONSOLIDATE THESE SIMILAR MEMORIES:

{chr(10).join(f"Memory {i+1}: {content}" for i, content in enumerate(contents))}

Create a single consolidated memory:"""
                    
                    selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
                    consolidated_content = await generate_answer_with_model(
                        selection=selection,
                        system_prompt=sys_prompt,
                        user_prompt=user_prompt,
                        gemini_rotator=None,
                        nvidia_rotator=nvidia_rotator
                    )
                    
                    return {
                        "content": consolidated_content.strip(),
                        "memory_type": memory_types[0] if memory_types else "conversation",
                        "tags": list(set(tags)) + ["consolidated"]
                    }
                    
                except Exception as e:
                    logger.warning(f"[CONVERSATION_MANAGER] NVIDIA consolidation failed: {e}")
            
            # Fallback: simple concatenation
            consolidated_content = "\n\n".join(contents)
            return {
                "content": consolidated_content,
                "memory_type": memory_types[0] if memory_types else "conversation",
                "tags": list(set(tags)) + ["consolidated"]
            }
            
        except Exception as e:
            logger.error(f"[CONVERSATION_MANAGER] Memory consolidation failed: {e}")
            return None


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

def reset_conversation_manager():
    """Reset the global conversation manager (for testing)"""
    global _conversation_manager
    _conversation_manager = None
