# ────────────────────────────── memo/consolidation.py ──────────────────────────────
"""
Memory Consolidation and Pruning

Handles memory consolidation, pruning, and optimization
to prevent information overload and maintain performance.
"""

import re
from typing import List, Dict, Any, Optional

from utils.logger import get_logger
from memo.context import cosine_similarity

logger = get_logger("CONSOLIDATION_MANAGER", __name__)

class ConsolidationManager:
    """
    Manages memory consolidation and pruning operations.
    """
    
    def __init__(self, memory_system, embedder):
        self.memory_system = memory_system
        self.embedder = embedder
        self.memory_consolidation_threshold = 10  # Consolidate after 10 memories
    
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
                    consolidated_memory = await self._consolidate_memory_group(group, nvidia_rotator, user_id)
                    
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
            
            logger.info(f"[CONSOLIDATION_MANAGER] Consolidated {consolidated_count} groups, pruned {pruned_count} memories")
            return {"consolidated": consolidated_count, "pruned": pruned_count}
            
        except Exception as e:
            logger.error(f"[CONSOLIDATION_MANAGER] Memory consolidation failed: {e}")
            return {"consolidated": 0, "pruned": 0, "error": str(e)}
    
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
            logger.error(f"[CONSOLIDATION_MANAGER] Memory grouping failed: {e}")
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
            logger.warning(f"[CONSOLIDATION_MANAGER] Memory similarity calculation failed: {e}")
            return 0.0
    
    async def _consolidate_memory_group(self, group: List[Dict[str, Any]], 
                                      nvidia_rotator, user_id: str = "") -> Optional[Dict[str, Any]]:
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
                    from utils.analytics import get_analytics_tracker
                    
                    # Track memory agent usage
                    tracker = get_analytics_tracker()
                    if tracker:
                        await tracker.track_agent_usage(
                            user_id=user_id,
                            agent_name="memory",
                            action="consolidate",
                            context="memory_consolidation",
                            metadata={"count": len(contents)}
                        )
                    
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
                    
                    # Track memory agent usage
                    try:
                        from utils.analytics import get_analytics_tracker
                        tracker = get_analytics_tracker()
                        if tracker and user_id:
                            await tracker.track_agent_usage(
                                user_id=user_id,
                                agent_name="memory",
                                action="consolidate",
                                context="memory_consolidation",
                                metadata={"memories_count": len(contents)}
                            )
                    except Exception:
                        pass
                    
                    # Track memory agent usage
                    tracker = get_analytics_tracker()
                    if tracker:
                        await tracker.track_agent_usage(
                            user_id=user_id,
                            agent_name="memory",
                            action="consolidate",
                            context="memory_consolidation",
                            metadata={"count": len(contents)}
                        )
                    
                    # Use Qwen for better memory consolidation reasoning
                    from utils.api.router import qwen_chat_completion
                    consolidated_content = await qwen_chat_completion(sys_prompt, user_prompt, nvidia_rotator, user_id, "memory_consolidation")
                    
                    return {
                        "content": consolidated_content.strip(),
                        "memory_type": memory_types[0] if memory_types else "conversation",
                        "tags": list(set(tags)) + ["consolidated"]
                    }
                    
                except Exception as e:
                    logger.warning(f"[CONSOLIDATION_MANAGER] NVIDIA consolidation failed: {e}")
            
            # Fallback: simple concatenation
            consolidated_content = "\n\n".join(contents)
            return {
                "content": consolidated_content,
                "memory_type": memory_types[0] if memory_types else "conversation",
                "tags": list(set(tags)) + ["consolidated"]
            }
            
        except Exception as e:
            logger.error(f"[CONSOLIDATION_MANAGER] Memory consolidation failed: {e}")
            return None


# ────────────────────────────── Global Instance ──────────────────────────────

_consolidation_manager: Optional[ConsolidationManager] = None

def get_consolidation_manager(memory_system=None, embedder=None) -> ConsolidationManager:
    """Get the global consolidation manager instance"""
    global _consolidation_manager
    
    if _consolidation_manager is None:
        if not memory_system:
            from memo.core import get_memory_system
            memory_system = get_memory_system()
        if not embedder:
            from utils.rag.embeddings import EmbeddingClient
            embedder = EmbeddingClient()
        
        _consolidation_manager = ConsolidationManager(memory_system, embedder)
        logger.info("[CONSOLIDATION_MANAGER] Global consolidation manager initialized")
    
    return _consolidation_manager

# def reset_consolidation_manager():
#     """Reset the global consolidation manager (for testing)"""
#     global _consolidation_manager
#     _consolidation_manager = None
