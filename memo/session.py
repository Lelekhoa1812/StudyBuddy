# memo/session.py
"""
Session-Specific Memory Management

Handles memory storage and retrieval for individual chat sessions,
separate from project-wide memory.
"""

import os
import time
import uuid
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from utils.logger import get_logger
from utils.rag.embeddings import EmbeddingClient

logger = get_logger("SESSION_MEMORY", __name__)

class SessionMemoryManager:
    """
    Manages memory for individual chat sessions.
    Each session has its own memory context separate from project memory.
    """
    
    def __init__(self, mongo_uri: str = None, db_name: str = "studybuddy"):
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.db_name = db_name
        
        # MongoDB connection
        try:
            from pymongo import MongoClient
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[self.db_name]
            self.session_memories = self.db["session_memories"]
            
            # Create indexes for efficient querying
            self.session_memories.create_index([("user_id", 1), ("project_id", 1), ("session_id", 1)])
            self.session_memories.create_index([("user_id", 1), ("project_id", 1), ("session_id", 1), ("created_at", -1)])
            
            logger.info(f"[SESSION_MEMORY] Connected to MongoDB: {self.db_name}")
        except Exception as e:
            logger.error(f"[SESSION_MEMORY] Failed to connect to MongoDB: {e}")
            raise
    
    def add_session_memory(self, user_id: str, project_id: str, session_id: str, 
                          content: str, memory_type: str = "conversation",
                          importance: str = "medium", tags: List[str] = None,
                          metadata: Dict[str, Any] = None) -> str:
        """Add a memory entry to a specific session"""
        try:
            memory_id = str(uuid.uuid4())
            
            memory_entry = {
                "memory_id": memory_id,
                "user_id": user_id,
                "project_id": project_id,
                "session_id": session_id,
                "content": content,
                "memory_type": memory_type,
                "importance": importance,
                "tags": tags or [],
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc),
                "timestamp": time.time()
            }
            
            self.session_memories.insert_one(memory_entry)
            logger.debug(f"[SESSION_MEMORY] Added memory to session {session_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"[SESSION_MEMORY] Failed to add session memory: {e}")
            return ""
    
    def get_session_memories(self, user_id: str, project_id: str, session_id: str,
                           memory_type: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get memories for a specific session"""
        try:
            query = {
                "user_id": user_id,
                "project_id": project_id,
                "session_id": session_id
            }
            
            if memory_type:
                query["memory_type"] = memory_type
            
            cursor = self.session_memories.find(query).sort("created_at", -1).limit(limit)
            return list(cursor)
            
        except Exception as e:
            logger.error(f"[SESSION_MEMORY] Failed to get session memories: {e}")
            return []
    
    def search_session_memories(self, user_id: str, project_id: str, session_id: str,
                              query: str, embedder: EmbeddingClient = None,
                              limit: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """Search memories within a session using semantic similarity"""
        try:
            if not embedder:
                # Fallback to text-based search
                memories = self.get_session_memories(user_id, project_id, session_id, limit=limit)
                return [(mem, 1.0) for mem in memories]
            
            # Get all session memories
            memories = self.get_session_memories(user_id, project_id, session_id, limit=50)
            if not memories:
                return []
            
            # Generate query embedding
            query_embedding = embedder.embed([query])[0]
            
            # Calculate similarities
            results = []
            for memory in memories:
                if "embedding" in memory:
                    similarity = self._cosine_similarity(query_embedding, memory["embedding"])
                    results.append((memory, similarity))
            
            # Sort by similarity and return top results
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:limit]
            
        except Exception as e:
            logger.error(f"[SESSION_MEMORY] Failed to search session memories: {e}")
            return []
    
    def clear_session_memories(self, user_id: str, project_id: str, session_id: str):
        """Clear all memories for a specific session"""
        try:
            result = self.session_memories.delete_many({
                "user_id": user_id,
                "project_id": project_id,
                "session_id": session_id
            })
            logger.info(f"[SESSION_MEMORY] Cleared {result.deleted_count} memories for session {session_id}")
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"[SESSION_MEMORY] Failed to clear session memories: {e}")
            return 0
    
    def get_session_memory_stats(self, user_id: str, project_id: str, session_id: str) -> Dict[str, Any]:
        """Get memory statistics for a session"""
        try:
            total_memories = self.session_memories.count_documents({
                "user_id": user_id,
                "project_id": project_id,
                "session_id": session_id
            })
            
            memory_types = self.session_memories.distinct("memory_type", {
                "user_id": user_id,
                "project_id": project_id,
                "session_id": session_id
            })
            
            return {
                "total_memories": total_memories,
                "memory_types": memory_types,
                "session_id": session_id
            }
            
        except Exception as e:
            logger.error(f"[SESSION_MEMORY] Failed to get session memory stats: {e}")
            return {"total_memories": 0, "memory_types": [], "session_id": session_id}
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            import numpy as np
            
            # Convert to numpy arrays
            a = np.array(vec1)
            b = np.array(vec2)
            
            # Calculate cosine similarity
            dot_product = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            return dot_product / (norm_a * norm_b)
            
        except Exception as e:
            logger.warning(f"[SESSION_MEMORY] Cosine similarity calculation failed: {e}")
            return 0.0


# ────────────────────────────── Global Instance ──────────────────────────────

_session_memory_manager: Optional[SessionMemoryManager] = None

def get_session_memory_manager(mongo_uri: str = None, db_name: str = None) -> SessionMemoryManager:
    """Get the global session memory manager instance"""
    global _session_memory_manager
    
    if _session_memory_manager is None:
        if mongo_uri is None:
            mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        if db_name is None:
            db_name = os.getenv("MONGO_DB", "studybuddy")
        
        _session_memory_manager = SessionMemoryManager(mongo_uri, db_name)
        logger.info("[SESSION_MEMORY] Global session memory manager initialized")
    
    return _session_memory_manager
