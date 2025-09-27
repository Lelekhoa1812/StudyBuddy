"""
Session Auto-Naming Module

This module handles automatic naming of chat sessions based on the first user query.
Uses NVIDIA_SMALL API to generate concise, descriptive session names.
"""

import asyncio
from typing import Optional
from utils.logger import get_logger

logger = get_logger("SESSION_NAMER", __name__)


async def auto_name_session(
    user_id: str, 
    project_id: str, 
    session_id: str, 
    first_query: str,
    nvidia_rotator=None,
    rag_db=None
) -> Optional[str]:
    """
    Automatically name a session based on the first query using NVIDIA_SMALL API.
    
    Args:
        user_id: User identifier
        project_id: Project identifier  
        session_id: Session identifier
        first_query: The first user query in the session
        nvidia_rotator: NVIDIA API rotator instance
        rag_db: Database connection
        
    Returns:
        Generated session name or None if failed
    """
    try:
        logger.info(f"[NAMER] Starting auto-naming for session {session_id}")
        logger.info(f"[NAMER] User: {user_id}, Project: {project_id}")
        logger.info(f"[NAMER] First query: {first_query[:100]}...")
        logger.info(f"[NAMER] NVIDIA rotator available: {nvidia_rotator is not None}")
        logger.info(f"[NAMER] Database available: {rag_db is not None}")
        
        if not nvidia_rotator:
            logger.warning("[NAMER] NVIDIA rotator not available")
            return None
        
        # Use NVIDIA_SMALL to generate a 2-3 word session name
        sys_prompt = """You are an expert at creating concise, descriptive session names.

Given a user's first query in a chat session, create a 2-3 word session name that captures the main topic or intent.

Rules:
- Use 2-3 words maximum
- Be descriptive but concise
- Use title case (capitalize first letter of each word)
- Focus on the main topic or question type
- Avoid generic terms like "Question" or "Chat"

Examples:
- "Machine Learning Basics" for "What is machine learning?"
- "Python Functions" for "How do I create functions in Python?"
- "Data Analysis" for "Can you help me analyze this dataset?"

Return only the session name, nothing else."""

        user_prompt = f"First query: {first_query}\n\nCreate a 2-3 word session name:"
        
        try:
            from utils.api.router import generate_answer_with_model
            selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
            
            logger.info(f"[NAMER] Calling NVIDIA API with model: {selection['model']}")
            logger.info(f"[NAMER] System prompt length: {len(sys_prompt)}")
            logger.info(f"[NAMER] User prompt: {user_prompt}")
            
            response = await generate_answer_with_model(
                selection=selection,
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                gemini_rotator=None,
                nvidia_rotator=nvidia_rotator,
                user_id=user_id,
                context="session_naming"
            )
            
            logger.info(f"[NAMER] Raw API response: {response}")
            
            # Clean up the response
            session_name = response.strip()
            logger.info(f"[NAMER] Initial session name: '{session_name}'")
            
            # Remove quotes if present
            if session_name.startswith('"') and session_name.endswith('"'):
                session_name = session_name[1:-1]
                logger.info(f"[NAMER] Removed double quotes: '{session_name}'")
            if session_name.startswith("'") and session_name.endswith("'"):
                session_name = session_name[1:-1]
                logger.info(f"[NAMER] Removed single quotes: '{session_name}'")
            
            # Truncate if too long (safety measure)
            if len(session_name) > 50:
                session_name = session_name[:47] + "..."
                logger.info(f"[NAMER] Truncated long name: '{session_name}'")
            
            logger.info(f"[NAMER] Final session name: '{session_name}'")
            
            # Update the session with the auto-generated name in database
            if rag_db:
                logger.info(f"[NAMER] Updating database for session {session_id}")
                logger.info(f"[NAMER] Query: user_id={user_id}, project_id={project_id}, session_id={session_id}")
                
                result = rag_db["chat_sessions"].update_many(
                    {"user_id": user_id, "project_id": project_id, "session_id": session_id},
                    {"$set": {"session_name": session_name, "is_auto_named": True}}
                )
                
                logger.info(f"[NAMER] Database update result: matched={result.matched_count}, modified={result.modified_count}")
                
                if result.modified_count > 0:
                    logger.info(f"[NAMER] ✅ Successfully auto-named session '{session_id}' to '{session_name}'")
                    return session_name
                else:
                    logger.warning(f"[NAMER] ❌ Session not found for auto-naming: {session_id}")
                    logger.warning(f"[NAMER] This might mean the session doesn't exist in the database yet")
                    return None
            else:
                logger.warning("[NAMER] ❌ Database connection not provided")
                return session_name
                
        except Exception as e:
            logger.error(f"[NAMER] ❌ Auto-naming API call failed: {e}")
            logger.error(f"[NAMER] Exception type: {type(e).__name__}")
            return None
            
    except Exception as e:
        logger.error(f"[NAMER] ❌ Failed to auto-name session: {e}")
        logger.error(f"[NAMER] Exception type: {type(e).__name__}")
        return None


async def auto_name_session_immediate(
    user_id: str, 
    project_id: str, 
    session_id: str, 
    first_query: str,
    nvidia_rotator=None,
    rag_db=None
) -> Optional[str]:
    """
    Immediately auto-name a session and return the name for UI update.
    This function is designed to be called synchronously during chat processing.
    
    Args:
        user_id: User identifier
        project_id: Project identifier  
        session_id: Session identifier
        first_query: The first user query in the session
        nvidia_rotator: NVIDIA API rotator instance
        rag_db: Database connection
        
    Returns:
        Generated session name or None if failed
    """
    try:
        # Run auto-naming in a separate task to avoid blocking
        task = asyncio.create_task(
            auto_name_session(user_id, project_id, session_id, first_query, nvidia_rotator, rag_db)
        )
        
        # Wait for completion with a timeout
        try:
            session_name = await asyncio.wait_for(task, timeout=10.0)
            return session_name
        except asyncio.TimeoutError:
            logger.warning(f"[NAMER] Auto-naming timed out for session {session_id}")
            return None
            
    except Exception as e:
        logger.error(f"[NAMER] Immediate auto-naming failed: {e}")
        return None
