# ────────────────────────────── memo/persistent.py ──────────────────────────────
"""
Persistent Memory System

MongoDB-based persistent memory storage with semantic search capabilities.
"""

import os
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from utils.logger import get_logger
from utils.rag.embeddings import EmbeddingClient

logger = get_logger("PERSISTENT_MEMORY", __name__)

class PersistentMemory:
    """MongoDB-based persistent memory system with semantic search"""
    
    def __init__(self, mongo_uri: str, db_name: str, embedder: EmbeddingClient):
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.embedder = embedder
        
        # MongoDB connection
        try:
            from pymongo import MongoClient
            self.client = MongoClient(mongo_uri)
            self.db = self.client[db_name]
            self.memories = self.db["memories"]
            
            # Create indexes for efficient querying
            self.memories.create_index([("user_id", 1), ("memory_type", 1)])
            self.memories.create_index([("user_id", 1), ("created_at", -1)])
            self.memories.create_index([("user_id", 1), ("project_id", 1)])
            
            logger.info(f"[PERSISTENT_MEMORY] Connected to MongoDB: {db_name}")
        except Exception as e:
            logger.error(f"[PERSISTENT_MEMORY] Failed to connect to MongoDB: {e}")
            raise
    
    def add_memory(self, user_id: str, content: str, memory_type: str, 
                  project_id: str = None, importance: str = "medium",
                  tags: List[str] = None, metadata: Dict[str, Any] = None) -> str:
        """Add a memory entry to the persistent system"""
        try:
            # Generate embedding for semantic search
            embedding = self.embedder.embed([content])[0] if content else None
            
            # Create summary
            summary = content[:200] + "..." if len(content) > 200 else content
            
            memory_entry = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "project_id": project_id,
                "memory_type": memory_type,
                "content": content,
                "summary": summary,
                "importance": importance,
                "tags": tags or [],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "last_accessed": datetime.now(timezone.utc),
                "access_count": 0,
                "embedding": embedding,
                "metadata": metadata or {}
            }
            
            # Store in MongoDB
            self.memories.insert_one(memory_entry)
            logger.info(f"[PERSISTENT_MEMORY] Added {memory_type} memory for user {user_id}")
            return memory_entry["id"]
            
        except Exception as e:
            logger.error(f"[PERSISTENT_MEMORY] Failed to add memory: {e}")
            raise
    
    def get_memories(self, user_id: str, memory_type: str = None, 
                    project_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get memories for a user with optional filtering"""
        try:
            query = {"user_id": user_id}
            
            if memory_type:
                query["memory_type"] = memory_type
            
            if project_id:
                query["project_id"] = project_id
            
            cursor = self.memories.find(query).sort("created_at", -1).limit(limit)
            return list(cursor)
            
        except Exception as e:
            logger.error(f"[PERSISTENT_MEMORY] Failed to get memories: {e}")
            return []
    
    def search_memories(self, user_id: str, query: str, memory_types: List[str] = None,
                       project_id: str = None, limit: int = 10) -> List[Tuple[Dict[str, Any], float]]:
        """Search memories using semantic similarity"""
        try:
            # Generate query embedding
            query_embedding = self.embedder.embed([query])[0]
            
            # Build MongoDB query
            mongo_query = {
                "user_id": user_id,
                "embedding": {"$exists": True}
            }
            
            if memory_types:
                mongo_query["memory_type"] = {"$in": memory_types}
            
            if project_id:
                mongo_query["project_id"] = project_id
            
            # Get all matching memories
            cursor = self.memories.find(mongo_query)
            
            # Calculate similarities
            results = []
            for doc in cursor:
                try:
                    if doc.get("embedding"):
                        # Calculate cosine similarity
                        similarity = self._cosine_similarity(query_embedding, doc["embedding"])
                        results.append((doc, similarity))
                except Exception as e:
                    logger.warning(f"[PERSISTENT_MEMORY] Failed to process memory for search: {e}")
                    continue
            
            # Sort by similarity and return top results
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:limit]
            
        except Exception as e:
            logger.error(f"[PERSISTENT_MEMORY] Failed to search memories: {e}")
            return []
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            import numpy as np
            from memo.context import cosine_similarity
            a_np = np.array(a)
            b_np = np.array(b)
            return cosine_similarity(a_np, b_np)
        except Exception:
            return 0.0
    
    def clear_user_memories(self, user_id: str) -> int:
        """Clear all memories for a user"""
        try:
            result = self.memories.delete_many({"user_id": user_id})
            logger.info(f"[PERSISTENT_MEMORY] Cleared {result.deleted_count} memories for user {user_id}")
            return result.deleted_count
        except Exception as e:
            logger.error(f"[PERSISTENT_MEMORY] Failed to clear user memories: {e}")
            return 0
    
    def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """Get memory statistics for a user"""
        try:
            stats = {
                "total_memories": self.memories.count_documents({"user_id": user_id}),
                "by_type": {},
                "recent_activity": 0
            }
            
            # Count by memory type
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$group": {"_id": "$memory_type", "count": {"$sum": 1}}}
            ]
            
            for result in self.memories.aggregate(pipeline):
                stats["by_type"][result["_id"]] = result["count"]
            
            # Recent activity (last 7 days)
            from datetime import timedelta
            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            stats["recent_activity"] = self.memories.count_documents({
                "user_id": user_id,
                "created_at": {"$gte": week_ago}
            })
            
            return stats
            
        except Exception as e:
            logger.error(f"[PERSISTENT_MEMORY] Failed to get memory stats: {e}")
            return {}
