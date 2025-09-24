# routes/sessions.py
import json, time, uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import Form, HTTPException

from helpers.setup import app, rag, logger, nvidia_rotator
from helpers.models import MessageResponse


@app.get("/sessions/list")
async def list_sessions(user_id: str, project_id: str):
    """Get all sessions for a project"""
    try:
        sessions_cursor = rag.db["chat_sessions"].find(
            {"user_id": user_id, "project_id": project_id}
        ).sort("created_at", -1)
        
        # Group by session_id to get unique sessions
        sessions_map = {}
        for message in sessions_cursor:
            session_id = message.get("session_id")
            if session_id and session_id not in sessions_map:
                sessions_map[session_id] = {
                    "session_id": session_id,
                    "name": message.get("session_name", "New Chat"),
                    "is_auto_named": message.get("is_auto_named", True),
                    "created_at": message.get("created_at"),
                    "last_activity": message.get("timestamp", 0),
                    "message_count": 0
                }
            if session_id in sessions_map:
                sessions_map[session_id]["message_count"] += 1
                # Update last activity to most recent message
                if message.get("timestamp", 0) > sessions_map[session_id]["last_activity"]:
                    sessions_map[session_id]["last_activity"] = message.get("timestamp", 0)
        
        sessions = list(sessions_map.values())
        return {"sessions": sessions}
        
    except Exception as e:
        logger.error(f"[SESSIONS] Failed to list sessions: {e}")
        raise HTTPException(500, detail=f"Failed to list sessions: {str(e)}")


@app.post("/sessions/create")
async def create_session(
    user_id: str = Form(...),
    project_id: str = Form(...),
    session_name: str = Form("New Chat")
):
    """Create a new session"""
    try:
        session_id = str(uuid.uuid4())
        current_time = time.time()
        
        # Create session record
        session_data = {
            "user_id": user_id,
            "project_id": project_id,
            "session_id": session_id,
            "session_name": session_name,
            "is_auto_named": session_name == "New Chat",
            "created_at": datetime.now(timezone.utc),
            "timestamp": current_time
        }
        
        # Insert session record
        rag.db["chat_sessions"].insert_one(session_data)
        
        return {
            "session_id": session_id,
            "name": session_name,
            "is_auto_named": session_name == "New Chat",
            "created_at": session_data["created_at"].isoformat(),
            "last_activity": current_time,
            "message_count": 0
        }
        
    except Exception as e:
        logger.error(f"[SESSIONS] Failed to create session: {e}")
        raise HTTPException(500, detail=f"Failed to create session: {str(e)}")


@app.put("/sessions/rename")
async def rename_session(
    user_id: str = Form(...),
    project_id: str = Form(...),
    session_id: str = Form(...),
    new_name: str = Form(...)
):
    """Rename a session"""
    try:
        # Update all messages in this session with new name
        result = rag.db["chat_sessions"].update_many(
            {"user_id": user_id, "project_id": project_id, "session_id": session_id},
            {"$set": {"session_name": new_name, "is_auto_named": False}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(404, detail="Session not found")
        
        return MessageResponse(message="Session renamed successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SESSIONS] Failed to rename session: {e}")
        raise HTTPException(500, detail=f"Failed to rename session: {str(e)}")


@app.delete("/sessions/delete")
async def delete_session(
    user_id: str = Form(...),
    project_id: str = Form(...),
    session_id: str = Form(...)
):
    """Delete a session and all its messages"""
    try:
        # Delete all messages in this session
        chat_result = rag.db["chat_sessions"].delete_many({
            "user_id": user_id, 
            "project_id": project_id, 
            "session_id": session_id
        })
        
        # Clear session-specific memory
        try:
            from memo.core import get_memory_system
            memory = get_memory_system()
            
            # Clear session-specific enhanced memory
            if memory.is_enhanced_available():
                memory.enhanced_memory.memories.delete_many({
                    "user_id": user_id,
                    "project_id": project_id,
                    "session_id": session_id
                })
            
            logger.info(f"[SESSIONS] Cleared session-specific memory for session {session_id}")
        except Exception as me:
            logger.warning(f"[SESSIONS] Failed to clear session memory: {me}")
        
        return MessageResponse(message=f"Session deleted successfully. Removed {chat_result.deleted_count} messages.")
        
    except Exception as e:
        logger.error(f"[SESSIONS] Failed to delete session: {e}")
        raise HTTPException(500, detail=f"Failed to delete session: {str(e)}")


@app.post("/sessions/auto-name")
async def auto_name_session(
    user_id: str = Form(...),
    project_id: str = Form(...),
    session_id: str = Form(...),
    first_query: str = Form(...)
):
    """Automatically name a session based on the first query using NVIDIA_SMALL API"""
    try:
        if not nvidia_rotator:
            return MessageResponse(message="Auto-naming not available")
        
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
            
            response = await generate_answer_with_model(
                selection=selection,
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                gemini_rotator=None,
                nvidia_rotator=nvidia_rotator
            )
            
            # Clean up the response
            session_name = response.strip()
            # Remove quotes if present
            if session_name.startswith('"') and session_name.endswith('"'):
                session_name = session_name[1:-1]
            if session_name.startswith("'") and session_name.endswith("'"):
                session_name = session_name[1:-1]
            
            # Truncate if too long (safety measure)
            if len(session_name) > 50:
                session_name = session_name[:47] + "..."
            
            # Update the session with the auto-generated name
            result = rag.db["chat_sessions"].update_many(
                {"user_id": user_id, "project_id": project_id, "session_id": session_id},
                {"$set": {"session_name": session_name, "is_auto_named": True}}
            )
            
            if result.modified_count > 0:
                return MessageResponse(message=f"Session auto-named: {session_name}")
            else:
                return MessageResponse(message="Session not found for auto-naming")
                
        except Exception as e:
            logger.warning(f"[SESSIONS] Auto-naming failed: {e}")
            return MessageResponse(message="Auto-naming failed, keeping default name")
            
    except Exception as e:
        logger.error(f"[SESSIONS] Failed to auto-name session: {e}")
        raise HTTPException(500, detail=f"Failed to auto-name session: {str(e)}")


@app.post("/sessions/clear-memory")
async def clear_session_memory(
    user_id: str = Form(...),
    project_id: str = Form(...),
    session_id: str = Form(...)
):
    """Clear memory for a specific session"""
    try:
        from memo.core import get_memory_system
        memory = get_memory_system()
        
        # Clear session-specific memory
        deleted_count = memory.clear_session_memories(user_id, project_id, session_id)
        
        return MessageResponse(message=f"Session memory cleared successfully. Removed {deleted_count} memory entries.")
        
    except Exception as e:
        logger.error(f"[SESSIONS] Failed to clear session memory: {e}")
        raise HTTPException(500, detail=f"Failed to clear session memory: {str(e)}")