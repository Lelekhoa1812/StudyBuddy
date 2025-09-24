# routes/projects.py
import uuid
import time
from datetime import datetime, timezone
from fastapi import Form, HTTPException
from pymongo.errors import PyMongoError

from helpers.setup import app, rag, logger
from helpers.models import ProjectResponse, ProjectsListResponse, MessageResponse


# ────────────────────────────── Project Management ───────────────────────────
@app.post("/projects/create", response_model=ProjectResponse)
async def create_project(user_id: str = Form(...), name: str = Form(...), description: str = Form("")):
    """Create a new project for a user"""
    try:
        if not rag:
            raise HTTPException(500, detail="Database connection not available")
            
        if not name.strip():
            raise HTTPException(400, detail="Project name is required")
        
        if not user_id.strip():
            raise HTTPException(400, detail="User ID is required")
        
        project_id = str(uuid.uuid4())
        current_time = datetime.now(timezone.utc)
        
        project = {
            "project_id": project_id,
            "user_id": user_id,
            "name": name.strip(),
            "description": description.strip(),
            "created_at": current_time,
            "updated_at": current_time
        }
        
        logger.info(f"[PROJECT] Creating project {name} for user {user_id}")
        
        # Insert the project
        try:
            result = rag.db["projects"].insert_one(project)
            logger.info(f"[PROJECT] Created project {name} with ID {project_id}, MongoDB result: {result.inserted_id}")
        except PyMongoError as mongo_error:
            logger.error(f"[PROJECT] MongoDB error creating project: {str(mongo_error)}")
            raise HTTPException(500, detail=f"Database error: {str(mongo_error)}")
        except Exception as db_error:
            logger.error(f"[PROJECT] Database error creating project: {str(db_error)}")
            raise HTTPException(500, detail=f"Database error: {str(db_error)}")
        
        # Return a properly formatted response
        response = ProjectResponse(
            project_id=project_id,
            user_id=user_id,
            name=name.strip(),
            description=description.strip(),
            created_at=current_time.isoformat(),
            updated_at=current_time.isoformat()
        )
        
        logger.info(f"[PROJECT] Successfully created project {name} for user {user_id}")
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"[PROJECT] Error creating project: {str(e)}")
        logger.error(f"[PROJECT] Error type: {type(e)}")
        logger.error(f"[PROJECT] Error details: {e}")
        raise HTTPException(500, detail=f"Failed to create project: {str(e)}")


@app.get("/projects", response_model=ProjectsListResponse)
async def list_projects(user_id: str):
    """List all projects for a user"""
    projects_cursor = rag.db["projects"].find(
        {"user_id": user_id}
    ).sort("updated_at", -1)
    
    projects = []
    for project in projects_cursor:
        projects.append(ProjectResponse(
            project_id=project["project_id"],
            user_id=project["user_id"],
            name=project["name"],
            description=project.get("description", ""),
            created_at=project["created_at"].isoformat() if isinstance(project["created_at"], datetime) else str(project["created_at"]),
            updated_at=project["updated_at"].isoformat() if isinstance(project["updated_at"], datetime) else str(project["updated_at"])
        ))
    
    return ProjectsListResponse(projects=projects)


@app.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, user_id: str):
    """Get a specific project (with user ownership check)"""
    project = rag.db["projects"].find_one(
        {"project_id": project_id, "user_id": user_id}
    )
    if not project:
        raise HTTPException(404, detail="Project not found")
    
    return ProjectResponse(
        project_id=project["project_id"],
        user_id=project["user_id"],
        name=project["name"],
        description=project.get("description", ""),
        created_at=project["created_at"].isoformat() if isinstance(project["created_at"], datetime) else str(project["created_at"]),
        updated_at=project["updated_at"].isoformat() if isinstance(project["updated_at"], datetime) else str(project["updated_at"])
    )


@app.delete("/projects/{project_id}", response_model=MessageResponse)
async def delete_project(project_id: str, user_id: str):
    """Delete a project and all its associated data including all sessions"""
    # Check ownership
    project = rag.db["projects"].find_one({"project_id": project_id, "user_id": user_id})
    if not project:
        raise HTTPException(404, detail="Project not found")
    
    try:
        # Delete project and all associated data
        rag.db["projects"].delete_one({"project_id": project_id})
        rag.db["chunks"].delete_many({"project_id": project_id})
        rag.db["files"].delete_many({"project_id": project_id})
        chat_result = rag.db["chat_sessions"].delete_many({"project_id": project_id})
        
        # Clear all session-specific memory for this project
        try:
            from memo.core import get_memory_system
            memory = get_memory_system()
            
            # Clear session memories for this project
            if memory.session_memory:
                session_memory_result = memory.session_memory.session_memories.delete_many({
                    "user_id": user_id,
                    "project_id": project_id
                })
                logger.info(f"[PROJECT] Cleared {session_memory_result.deleted_count} session memories for project {project_id}")
            
            # Clear enhanced memory for this project
            if memory.enhanced_available:
                enhanced_result = memory.enhanced_memory.memories.delete_many({
                    "user_id": user_id,
                    "project_id": project_id
                })
                logger.info(f"[PROJECT] Cleared {enhanced_result.deleted_count} enhanced memories for project {project_id}")
            
            # Clear legacy memory for this user (since it's user-scoped, not project-scoped)
            memory.legacy_memory.clear(user_id)
            logger.info(f"[PROJECT] Cleared legacy memory for user {user_id}")
            
        except Exception as e:
            logger.warning(f"[PROJECT] Failed to clear some memory components: {e}")
        
        logger.info(f"[PROJECT] Deleted project {project_id} for user {user_id} - removed {chat_result.deleted_count} chat sessions")
        return MessageResponse(message=f"Project deleted successfully. Removed {chat_result.deleted_count} chat sessions and all associated data.")
        
    except Exception as e:
        logger.error(f"[PROJECT] Failed to delete project {project_id}: {e}")
        raise HTTPException(500, detail=f"Failed to delete project: {str(e)}")


