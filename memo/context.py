# ────────────────────────────── memo/context.py ──────────────────────────────
"""
Context Management

Functions for retrieving and managing conversation context.
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional

from utils.logger import get_logger
from utils.rag.embeddings import EmbeddingClient

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


# ────────────────────────────── Memory Enhancement Functions ──────────────────────────────

async def enhance_question_with_memory(user_id: str, question: str, memory, nvidia_rotator, embedder: EmbeddingClient) -> Tuple[str, str]:
    """Enhance the user's question with relevant conversation history using STM (latest 3 messages)"""
    try:
        # Get recent conversation history (STM - latest 3 messages)
        recent_memories = memory.recent(user_id, 3)
        
        if not recent_memories:
            logger.info("[CONTEXT_MANAGER] No recent conversation history found")
            return question, ""
        
        # Use NVIDIA to determine if recent memories are relevant to current question
        if nvidia_rotator:
            try:
                from memo.nvidia import related_recent_context
                relevant_context = await related_recent_context(question, recent_memories, nvidia_rotator)
                
                if relevant_context:
                    # Enhance the question with relevant context
                    enhanced_question = await create_enhanced_prompt(question, relevant_context, nvidia_rotator)
                    logger.info(f"[CONTEXT_MANAGER] Enhanced question with {len(relevant_context)} chars of relevant context")
                    return enhanced_question, relevant_context
                else:
                    logger.info("[CONTEXT_MANAGER] No relevant recent context found")
                    return question, ""
                    
            except Exception as e:
                logger.warning(f"[CONTEXT_MANAGER] NVIDIA context enhancement failed: {e}")
                # Fallback to semantic similarity
                return await enhance_with_semantic_similarity(question, recent_memories, embedder)
        else:
            # Use semantic similarity if no NVIDIA rotator
            return await enhance_with_semantic_similarity(question, recent_memories, embedder)
            
    except Exception as e:
        logger.error(f"[CONTEXT_MANAGER] Memory enhancement failed: {e}")
        return question, ""


async def enhance_instructions_with_memory(user_id: str, instructions: str, memory, nvidia_rotator, embedder: EmbeddingClient) -> Tuple[str, str]:
    """Enhance the user's report instructions with relevant conversation history using STM (latest 3 messages)"""
    try:
        # Get recent conversation history (STM - latest 3 messages)
        recent_memories = memory.recent(user_id, 3)
        
        if not recent_memories:
            logger.info("[CONTEXT_MANAGER] No recent conversation history found")
            return instructions, ""
        
        # Use NVIDIA to determine if recent memories are relevant to current instructions
        if nvidia_rotator:
            try:
                from memo.nvidia import related_recent_context
                relevant_context = await related_recent_context(instructions, recent_memories, nvidia_rotator)
                
                if relevant_context:
                    # Enhance the instructions with relevant context
                    enhanced_instructions = await create_enhanced_report_prompt(instructions, relevant_context, nvidia_rotator)
                    logger.info(f"[CONTEXT_MANAGER] Enhanced instructions with {len(relevant_context)} chars of relevant context")
                    return enhanced_instructions, relevant_context
                else:
                    logger.info("[CONTEXT_MANAGER] No relevant recent context found")
                    return instructions, ""
                    
            except Exception as e:
                logger.warning(f"[CONTEXT_MANAGER] NVIDIA context enhancement failed: {e}")
                # Fallback to semantic similarity
                return await enhance_report_with_semantic_similarity(instructions, recent_memories, embedder)
        else:
            # Use semantic similarity if no NVIDIA rotator
            return await enhance_report_with_semantic_similarity(instructions, recent_memories, embedder)
            
    except Exception as e:
        logger.error(f"[CONTEXT_MANAGER] Memory enhancement failed: {e}")
        return instructions, ""


async def enhance_with_semantic_similarity(question: str, recent_memories: List[str], embedder: EmbeddingClient) -> Tuple[str, str]:
    """Enhance question using semantic similarity as fallback"""
    try:
        relevant_context = await semantic_context(question, recent_memories, embedder, 2)
        
        if relevant_context:
            # Simple enhancement by prepending context
            enhanced_question = f"Based on our previous conversation:\n{relevant_context}\n\nNow, {question}"
            logger.info(f"[CONTEXT_MANAGER] Enhanced question with semantic context: {len(relevant_context)} chars")
            return enhanced_question, relevant_context
        else:
            return question, ""
            
    except Exception as e:
        logger.warning(f"[CONTEXT_MANAGER] Semantic enhancement failed: {e}")
        return question, ""


async def enhance_report_with_semantic_similarity(instructions: str, recent_memories: List[str], embedder: EmbeddingClient) -> Tuple[str, str]:
    """Enhance report instructions using semantic similarity as fallback"""
    try:
        relevant_context = await semantic_context(instructions, recent_memories, embedder, 2)
        
        if relevant_context:
            # Simple enhancement by prepending context
            enhanced_instructions = f"Based on our previous conversation:\n{relevant_context}\n\nNow, {instructions}"
            logger.info(f"[CONTEXT_MANAGER] Enhanced instructions with semantic context: {len(relevant_context)} chars")
            return enhanced_instructions, relevant_context
        else:
            return instructions, ""
            
    except Exception as e:
        logger.warning(f"[CONTEXT_MANAGER] Semantic enhancement failed: {e}")
        return instructions, ""


async def create_enhanced_prompt(original_question: str, relevant_context: str, nvidia_rotator) -> str:
    """Use NVIDIA to create an enhanced prompt that incorporates relevant context intelligently"""
    try:
        from utils.api.router import generate_answer_with_model
        
        sys_prompt = """You are an expert at enhancing user questions with relevant conversation context.

Given a user's current question and relevant context from previous conversations, create an enhanced question that:
1. Incorporates the relevant context naturally
2. Maintains the user's original intent
3. Provides better context for answering
4. Flows naturally and doesn't sound forced

The enhanced question should help the AI provide more detailed, contextual, and relevant answers.

Return ONLY the enhanced question, no meta-commentary."""

        user_prompt = f"""ORIGINAL QUESTION: {original_question}

RELEVANT CONTEXT FROM PREVIOUS CONVERSATION:
{relevant_context}

Create an enhanced version of the question that incorporates this context naturally."""

        selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
        enhanced_question = await generate_answer_with_model(
            selection=selection,
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            gemini_rotator=None,
            nvidia_rotator=nvidia_rotator
        )
        
        return enhanced_question.strip()
        
    except Exception as e:
        logger.warning(f"[CONTEXT_MANAGER] Prompt enhancement failed: {e}")
        # Fallback to simple concatenation
        return f"Based on our previous conversation:\n{relevant_context}\n\nNow, {original_question}"


async def create_enhanced_report_prompt(original_instructions: str, relevant_context: str, nvidia_rotator) -> str:
    """Use NVIDIA to create enhanced report instructions that incorporate relevant context intelligently"""
    try:
        from utils.api.router import generate_answer_with_model
        
        sys_prompt = """You are an expert at enhancing report instructions with relevant conversation context.

Given a user's current report instructions and relevant context from previous conversations, create enhanced instructions that:
1. Incorporates the relevant context naturally
2. Maintains the user's original intent for the report
3. Provides better context for generating a comprehensive report
4. Flows naturally and doesn't sound forced

The enhanced instructions should help generate a more detailed, contextual, and relevant report.

Return ONLY the enhanced instructions, no meta-commentary."""

        user_prompt = f"""ORIGINAL REPORT INSTRUCTIONS: {original_instructions}

RELEVANT CONTEXT FROM PREVIOUS CONVERSATION:
{relevant_context}

Create an enhanced version of the report instructions that incorporates this context naturally."""

        selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
        enhanced_instructions = await generate_answer_with_model(
            selection=selection,
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            gemini_rotator=None,
            nvidia_rotator=nvidia_rotator
        )
        
        return enhanced_instructions.strip()
        
    except Exception as e:
        logger.warning(f"[CONTEXT_MANAGER] Prompt enhancement failed: {e}")
        # Fallback to simple concatenation
        return f"Based on our previous conversation:\n{relevant_context}\n\nNow, {original_instructions}"
