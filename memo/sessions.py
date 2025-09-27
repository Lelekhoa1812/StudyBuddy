# ────────────────────────────── memo/sessions.py ──────────────────────────────
"""
Conversation Session Management

Handles conversation session tracking, context switching detection,
and conversation insights.
"""

import re
import time
from typing import Dict, Any, Tuple, Optional

from utils.logger import get_logger

logger = get_logger("SESSION_MANAGER", __name__)

class SessionManager:
    """
    Manages conversation sessions and tracks conversation state.
    """
    
    def __init__(self):
        self.conversation_sessions = {}  # Track active conversation sessions
        self.context_cache = {}  # Cache recent context for performance
    
    def get_or_create_session(self, user_id: str, question: str, conversation_mode: str) -> Dict[str, Any]:
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
    
    def update_session(self, user_id: str, original_question: str, 
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
    
    async def detect_context_switch(self, user_id: str, new_question: str, 
                                  nvidia_rotator=None) -> Dict[str, Any]:
        """Detect if user has switched context/topic"""
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
                
                logger.info(f"[SESSION_MANAGER] Context switch detected for user {user_id} (confidence: {confidence:.2f})")
                
                return {
                    "is_context_switch": True,
                    "confidence": confidence,
                    "switch_count": session_info["context_switches"]
                }
            
            return {"is_context_switch": False, "confidence": confidence}
            
        except Exception as e:
            logger.error(f"[SESSION_MANAGER] Context switch detection failed: {e}")
            return {"is_context_switch": False, "confidence": 0.0, "error": str(e)}
    
    def get_conversation_insights(self, user_id: str) -> Dict[str, Any]:
        """Get insights about the user's conversation patterns"""
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
            logger.error(f"[SESSION_MANAGER] Failed to get conversation insights: {e}")
            return {"error": str(e)}
    
    def clear_session(self, user_id: str):
        """Clear session for user"""
        if user_id in self.conversation_sessions:
            del self.conversation_sessions[user_id]
        if user_id in self.context_cache:
            del self.context_cache[user_id]
    
    # ────────────────────────────── Private Helper Methods ──────────────────────────────
    
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
                    
                    selection = {"provider": "nvidia", "model": os.getenv("NVIDIA_SMALL", "meta/llama-3.1-8b-instruct")}
                    response = await generate_answer_with_model(
                        selection=selection,
                        system_prompt=sys_prompt,
                        user_prompt=user_prompt,
                        gemini_rotator=None,
                        nvidia_rotator=nvidia_rotator,
                        user_id="system",
                        context="context_switch_detection"
                    )
                    
                    # Parse JSON response
                    import json
                    try:
                        result = json.loads(response.strip())
                        return result.get("is_context_switch", False), result.get("confidence", 0.0)
                    except:
                        pass
                        
                except Exception as e:
                    logger.warning(f"[SESSION_MANAGER] Context switch detection failed: {e}")
            
            # Fallback: simple keyword-based detection
            return self._simple_context_switch_detection(last_question, new_question)
            
        except Exception as e:
            logger.warning(f"[SESSION_MANAGER] Context switch detection failed: {e}")
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
            logger.warning(f"[SESSION_MANAGER] Simple context switch detection failed: {e}")
            return False, 0.0


# ────────────────────────────── Global Instance ──────────────────────────────

_session_manager: Optional[SessionManager] = None

def get_session_manager() -> SessionManager:
    """Get the global session manager instance"""
    global _session_manager
    
    if _session_manager is None:
        _session_manager = SessionManager()
        logger.info("[SESSION_MANAGER] Global session manager initialized")
    
    return _session_manager

# def reset_session_manager():
#     """Reset the global session manager (for testing)"""
#     global _session_manager
#     _session_manager = None
