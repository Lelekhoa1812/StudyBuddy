# ────────────────────────────── utils/analytics.py ──────────────────────────────
"""
Analytics and Usage Tracking System

Tracks user-specific usage of models and agents for analytics dashboard.
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo import MongoClient
from utils.logger import get_logger

logger = get_logger("ANALYTICS", __name__)

class AnalyticsTracker:
    """Tracks user usage analytics for models and agents."""
    
    def __init__(self, mongo_client: MongoClient, db_name: str = "studybuddy"):
        self.client = mongo_client
        self.db = mongo_client[db_name]
        self.usage_collection = self.db["usage_analytics"]
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """Create necessary indexes for efficient queries."""
        try:
            # Compound index for user_id + timestamp
            self.usage_collection.create_index([("user_id", 1), ("timestamp", -1)])
            # Index for aggregation queries
            self.usage_collection.create_index([("user_id", 1), ("type", 1), ("timestamp", -1)])
            logger.info("[ANALYTICS] Indexes created successfully")
        except Exception as e:
            logger.warning(f"[ANALYTICS] Failed to create indexes: {e}")
    
    async def track_model_usage(self, user_id: str, model_name: str, provider: str, 
                               context: str = "", metadata: Optional[Dict] = None):
        """Track model usage for analytics."""
        try:
            usage_record = {
                "user_id": user_id,
                "type": "model",
                "model_name": model_name,
                "provider": provider,
                "context": context,
                "timestamp": time.time(),
                "created_at": datetime.now(timezone.utc),
                "metadata": metadata or {}
            }
            
            self.usage_collection.insert_one(usage_record)
            logger.debug(f"[ANALYTICS] Tracked model usage: {model_name} for user {user_id}")
            
        except Exception as e:
            logger.error(f"[ANALYTICS] Failed to track model usage: {e}")
    
    async def track_agent_usage(self, user_id: str, agent_name: str, action: str,
                              context: str = "", metadata: Optional[Dict] = None):
        """Track agent usage for analytics."""
        try:
            usage_record = {
                "user_id": user_id,
                "type": "agent",
                "agent_name": agent_name,
                "action": action,
                "context": context,
                "timestamp": time.time(),
                "created_at": datetime.now(timezone.utc),
                "metadata": metadata or {}
            }
            
            self.usage_collection.insert_one(usage_record)
            logger.debug(f"[ANALYTICS] Tracked agent usage: {agent_name} for user {user_id}")
            
        except Exception as e:
            logger.error(f"[ANALYTICS] Failed to track agent usage: {e}")
    
    async def get_user_analytics(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive analytics for a user."""
        try:
            # Calculate time range
            cutoff_time = time.time() - (days * 24 * 60 * 60)
            
            # Model usage analytics
            model_pipeline = [
                {"$match": {"user_id": user_id, "type": "model", "timestamp": {"$gte": cutoff_time}}},
                {"$group": {
                    "_id": "$model_name",
                    "count": {"$sum": 1},
                    "provider": {"$first": "$provider"},
                    "last_used": {"$max": "$timestamp"}
                }},
                {"$sort": {"count": -1}}
            ]
            
            model_usage = list(self.usage_collection.aggregate(model_pipeline))
            
            # Agent usage analytics
            agent_pipeline = [
                {"$match": {"user_id": user_id, "type": "agent", "timestamp": {"$gte": cutoff_time}}},
                {"$group": {
                    "_id": "$agent_name",
                    "count": {"$sum": 1},
                    "actions": {"$addToSet": "$action"},
                    "last_used": {"$max": "$timestamp"}
                }},
                {"$sort": {"count": -1}}
            ]
            
            agent_usage = list(self.usage_collection.aggregate(agent_pipeline))
            
            # Daily usage trends
            daily_pipeline = [
                {"$match": {"user_id": user_id, "timestamp": {"$gte": cutoff_time}}},
                {"$group": {
                    "_id": {
                        "year": {"$year": {"$dateFromTimestamp": {"$multiply": ["$timestamp", 1000]}}},
                        "month": {"$month": {"$dateFromTimestamp": {"$multiply": ["$timestamp", 1000]}}},
                        "day": {"$dayOfMonth": {"$dateFromTimestamp": {"$multiply": ["$timestamp", 1000]}}}
                    },
                    "total_requests": {"$sum": 1},
                    "model_requests": {"$sum": {"$cond": [{"$eq": ["$type", "model"]}, 1, 0]}},
                    "agent_requests": {"$sum": {"$cond": [{"$eq": ["$type", "agent"]}, 1, 0]}}
                }},
                {"$sort": {"_id.year": 1, "_id.month": 1, "_id.day": 1}}
            ]
            
            daily_usage = list(self.usage_collection.aggregate(daily_pipeline))
            
            return {
                "user_id": user_id,
                "period_days": days,
                "model_usage": model_usage,
                "agent_usage": agent_usage,
                "daily_usage": daily_usage,
                "total_requests": sum(item["count"] for item in model_usage + agent_usage),
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"[ANALYTICS] Failed to get user analytics: {e}")
            return {
                "user_id": user_id,
                "period_days": days,
                "model_usage": [],
                "agent_usage": [],
                "daily_usage": [],
                "total_requests": 0,
                "error": str(e),
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
    
    async def get_global_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get global analytics across all users."""
        try:
            cutoff_time = time.time() - (days * 24 * 60 * 60)
            
            # Global model usage
            model_pipeline = [
                {"$match": {"type": "model", "timestamp": {"$gte": cutoff_time}}},
                {"$group": {
                    "_id": "$model_name",
                    "count": {"$sum": 1},
                    "unique_users": {"$addToSet": "$user_id"},
                    "provider": {"$first": "$provider"}
                }},
                {"$addFields": {"unique_user_count": {"$size": "$unique_users"}}},
                {"$sort": {"count": -1}}
            ]
            
            global_model_usage = list(self.usage_collection.aggregate(model_pipeline))
            
            # Global agent usage
            agent_pipeline = [
                {"$match": {"type": "agent", "timestamp": {"$gte": cutoff_time}}},
                {"$group": {
                    "_id": "$agent_name",
                    "count": {"$sum": 1},
                    "unique_users": {"$addToSet": "$user_id"},
                    "actions": {"$addToSet": "$action"}
                }},
                {"$addFields": {"unique_user_count": {"$size": "$unique_users"}}},
                {"$sort": {"count": -1}}
            ]
            
            global_agent_usage = list(self.usage_collection.aggregate(agent_pipeline))
            
            return {
                "period_days": days,
                "global_model_usage": global_model_usage,
                "global_agent_usage": global_agent_usage,
                "total_requests": sum(item["count"] for item in global_model_usage + global_agent_usage),
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"[ANALYTICS] Failed to get global analytics: {e}")
            return {
                "period_days": days,
                "global_model_usage": [],
                "global_agent_usage": [],
                "total_requests": 0,
                "error": str(e),
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
    
    async def cleanup_old_data(self, days_to_keep: int = 90):
        """Clean up old analytics data to prevent database bloat."""
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
            result = self.usage_collection.delete_many({"timestamp": {"$lt": cutoff_time}})
            logger.info(f"[ANALYTICS] Cleaned up {result.deleted_count} old records")
            return result.deleted_count
        except Exception as e:
            logger.error(f"[ANALYTICS] Failed to cleanup old data: {e}")
            return 0


# Global analytics tracker instance
analytics_tracker: Optional[AnalyticsTracker] = None

def init_analytics(mongo_client, db_name: str = "studybuddy"):
    """Initialize the global analytics tracker."""
    global analytics_tracker
    analytics_tracker = AnalyticsTracker(mongo_client, db_name)
    logger.info("[ANALYTICS] Analytics tracker initialized")

def get_analytics_tracker() -> Optional[AnalyticsTracker]:
    """Get the global analytics tracker instance."""
    return analytics_tracker
