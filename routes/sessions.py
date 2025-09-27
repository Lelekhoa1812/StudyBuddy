# routes/sessions.py
import json, time, uuid, os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import Form, HTTPException

from helpers.setup import app, rag, logger, nvidia_rotator
from helpers.models import MessageResponse


@app.get("/sessions/list")
async def list_sessions(user_id: str, project_id: str):
    """Get all sessions for a project"""
    try:
        # First, get all session records (including those without messages)
        sessions_cursor = rag.db["chat_sessions"].find(
            {"user_id": user_id, "project_id": project_id, "role": {"$exists": False}}  # Session records don't have role
        ).sort("created_at", -1)
        
        # Group by session_id to get unique sessions
        sessions_map = {}
        
        # Process session records first
        for session_record in sessions_cursor:
            session_id = session_record.get("session_id")
            if session_id and session_id not in sessions_map:
                sessions_map[session_id] = {
                    "session_id": session_id,
                    "name": session_record.get("session_name", "New Chat"),
                    "is_auto_named": session_record.get("is_auto_named", True),
                    "created_at": session_record.get("created_at"),
                    "last_activity": session_record.get("timestamp", 0),
                    "message_count": 0
                }
        
        # Now count messages for each session
        messages_cursor = rag.db["chat_sessions"].find(
            {"user_id": user_id, "project_id": project_id, "role": {"$exists": True}}  # Messages have role
        ).sort("timestamp", -1)
        
        for message in messages_cursor:
            session_id = message.get("session_id")
            if session_id and session_id in sessions_map:
                sessions_map[session_id]["message_count"] += 1
                # Update last activity to most recent message
                if message.get("timestamp", 0) > sessions_map[session_id]["last_activity"]:
                    sessions_map[session_id]["last_activity"] = message.get("timestamp", 0)
        
        sessions = list(sessions_map.values())
        
        # If no sessions exist, create a default one
        if not sessions:
            try:
                session_id = str(uuid.uuid4())
                current_time = time.time()
                
                session_data = {
                    "user_id": user_id,
                    "project_id": project_id,
                    "session_id": session_id,
                    "session_name": "New Chat",
                    "is_auto_named": True,
                    "created_at": datetime.now(timezone.utc),
                    "timestamp": current_time
                }
                
                rag.db["chat_sessions"].insert_one(session_data)
                
                sessions = [{
                    "session_id": session_id,
                    "name": "New Chat",
                    "is_auto_named": True,
                    "created_at": session_data["created_at"].isoformat(),
                    "last_activity": current_time,
                    "message_count": 0
                }]
                
                logger.info(f"[SESSIONS] Created default session {session_id} for user {user_id}, project {project_id}")
            except Exception as e:
                logger.warning(f"[SESSIONS] Failed to create default session: {e}")
        
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


# Some deployments/proxies do not allow PUT; provide POST alias for compatibility
@app.post("/sessions/rename")
async def rename_session_post(
    user_id: str = Form(...),
    project_id: str = Form(...),
    session_id: str = Form(...),
    new_name: str = Form(...)
):
    return await rename_session(user_id=user_id, project_id=project_id, session_id=session_id, new_name=new_name)


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
        from helpers.namer import auto_name_session_immediate
        
        session_name = await auto_name_session_immediate(
            user_id, project_id, session_id, first_query, nvidia_rotator, rag.db
        )
        
        if session_name:
            return MessageResponse(message=f"Session auto-named: {session_name}")
        else:
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