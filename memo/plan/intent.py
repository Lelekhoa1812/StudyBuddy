# ────────────────────────────── memo/plan/intent.py ──────────────────────────────
"""
Intent Detection

Handles user intent detection for memory planning.
"""

import re
from typing import List, Dict, Any, Tuple, Optional
from enum import Enum

from utils.logger import get_logger

logger = get_logger("INTENT_DETECTOR", __name__)

class QueryIntent(Enum):
    """Types of user query intents"""
    ENHANCEMENT = "enhancement"  # User wants more details/elaboration
    CLARIFICATION = "clarification"  # User wants clarification
    CONTINUATION = "continuation"  # User is continuing previous topic
    NEW_TOPIC = "new_topic"  # User is starting a new topic
    COMPARISON = "comparison"  # User wants to compare with previous content
    REFERENCE = "reference"  # User is referencing specific past content

class IntentDetector:
    """Handles user intent detection for memory planning"""
    
    def __init__(self):
        # Enhancement request patterns
        self.enhancement_patterns = [
            r'\b(enhance|elaborate|expand|detail|elaborate on|be more detailed|more details|more information)\b',
            r'\b(explain more|tell me more|go deeper|dive deeper|more context)\b',
            r'\b(what else|anything else|additional|further|supplement)\b',
            r'\b(comprehensive|thorough|complete|full)\b',
            r'\b(based on|from our|as we discussed|following up|regarding)\b'
        ]
        
        # Clarification patterns
        self.clarification_patterns = [
            r'\b(what do you mean|clarify|explain|what is|define)\b',
            r'\b(how does|why does|when does|where does)\b',
            r'\b(can you explain|help me understand)\b'
        ]
        
        # Comparison patterns
        self.comparison_patterns = [
            r'\b(compare|versus|vs|difference|similar|different)\b',
            r'\b(like|unlike|similar to|different from)\b',
            r'\b(contrast|opposite|better|worse)\b'
        ]
        
        # Reference patterns
        self.reference_patterns = [
            r'\b(you said|we discussed|earlier|before|previously)\b',
            r'\b(that|this|it|the above|mentioned)\b',
            r'\b(according to|based on|from|in)\b'
        ]
    
    async def detect_intent(self, question: str, nvidia_rotator=None) -> QueryIntent:
        """Detect user intent from the question"""
        try:
            question_lower = question.lower()
            
            # Check for enhancement patterns
            if any(re.search(pattern, question_lower) for pattern in self.enhancement_patterns):
                return QueryIntent.ENHANCEMENT
            
            # Check for clarification patterns
            if any(re.search(pattern, question_lower) for pattern in self.clarification_patterns):
                return QueryIntent.CLARIFICATION
            
            # Check for comparison patterns
            if any(re.search(pattern, question_lower) for pattern in self.comparison_patterns):
                return QueryIntent.COMPARISON
            
            # Check for reference patterns
            if any(re.search(pattern, question_lower) for pattern in self.reference_patterns):
                return QueryIntent.REFERENCE
            
            # Use AI for more sophisticated intent detection
            if nvidia_rotator:
                try:
                    return await self._ai_intent_detection(question, nvidia_rotator)
                except Exception as e:
                    logger.warning(f"[INTENT_DETECTOR] AI intent detection failed: {e}")
            
            # Default to continuation if no clear patterns
            return QueryIntent.CONTINUATION
            
        except Exception as e:
            logger.warning(f"[INTENT_DETECTOR] Intent detection failed: {e}")
            return QueryIntent.CONTINUATION
    
    async def _ai_intent_detection(self, question: str, nvidia_rotator) -> QueryIntent:
        """Use AI to detect user intent more accurately"""
        try:
            from utils.api.router import generate_answer_with_model
            
            sys_prompt = """You are an expert at analyzing user intent in questions.

Classify the user's question into one of these intents:
- ENHANCEMENT: User wants more details, elaboration, or comprehensive information
- CLARIFICATION: User wants explanation or clarification of something
- CONTINUATION: User is continuing a previous topic or conversation
- NEW_TOPIC: User is starting a completely new topic
- COMPARISON: User wants to compare or contrast things
- REFERENCE: User is referencing specific past content or discussions

Respond with only the intent name (e.g., "ENHANCEMENT")."""
            
            user_prompt = f"Question: {question}\n\nWhat is the user's intent?"
            
            # Use Qwen for better intent detection reasoning
            from utils.api.router import qwen_chat_completion
            response = await qwen_chat_completion(sys_prompt, user_prompt, nvidia_rotator)
            
            # Parse response
            response_upper = response.strip().upper()
            for intent in QueryIntent:
                if intent.name in response_upper:
                    return intent
            
            return QueryIntent.CONTINUATION
            
        except Exception as e:
            logger.warning(f"[INTENT_DETECTOR] AI intent detection failed: {e}")
            return QueryIntent.CONTINUATION


# ────────────────────────────── Global Instance ──────────────────────────────

_intent_detector: Optional[IntentDetector] = None

def get_intent_detector() -> IntentDetector:
    """Get the global intent detector instance"""
    global _intent_detector
    
    if _intent_detector is None:
        _intent_detector = IntentDetector()
        logger.info("[INTENT_DETECTOR] Global intent detector initialized")
    
    return _intent_detector
