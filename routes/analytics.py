# ────────────────────────────── routes/analytics.py ──────────────────────────────
"""
Analytics API Routes

Provides endpoints for retrieving user and global analytics data.
"""
import os

from fastapi import HTTPException, Query
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from helpers.setup import app, logger
from utils.analytics import get_analytics_tracker


class AnalyticsResponse(BaseModel):
    """Response model for analytics data."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: str


@app.get("/analytics/user", response_model=AnalyticsResponse)
async def get_user_analytics(
    user_id: str = Query(..., description="User ID to get analytics for"),
    days: int = Query(30, description="Number of days to include in analytics", ge=1, le=365)
):
    """Get analytics data for a specific user."""
    try:
        tracker = get_analytics_tracker()
        if not tracker:
            raise HTTPException(500, detail="Analytics tracker not initialized")
        
        analytics_data = await tracker.get_user_analytics(user_id, days)
        
        return AnalyticsResponse(
            success=True,
            data=analytics_data,
            message=f"Analytics data retrieved for user {user_id}"
        )
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Failed to get user analytics: {e}")
        raise HTTPException(500, detail=f"Failed to retrieve analytics: {str(e)}")


@app.get("/analytics/test", response_model=AnalyticsResponse)
async def test_analytics():
    """Test endpoint to verify analytics system is working."""
    try:
        tracker = get_analytics_tracker()
        if not tracker:
            return AnalyticsResponse(
                success=False,
                data=None,
                message="Analytics tracker not initialized"
            )
        
        return AnalyticsResponse(
            success=True,
            data={"status": "analytics_system_working"},
            message="Analytics system is operational"
        )
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Test endpoint error: {e}")
        return AnalyticsResponse(
            success=False,
            data=None,
            message=f"Analytics test failed: {str(e)}"
        )


@app.get("/analytics/global", response_model=AnalyticsResponse)
async def get_global_analytics(
    days: int = Query(30, description="Number of days to include in analytics", ge=1, le=365)
):
    """Get global analytics data across all users."""
    try:
        tracker = get_analytics_tracker()
        if not tracker:
            raise HTTPException(500, detail="Analytics tracker not initialized")
        
        analytics_data = await tracker.get_global_analytics(days)
        
        return AnalyticsResponse(
            success=True,
            data=analytics_data,
            message="Global analytics data retrieved"
        )
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Failed to get global analytics: {e}")
        raise HTTPException(500, detail=f"Failed to retrieve global analytics: {str(e)}")


@app.post("/analytics/cleanup", response_model=AnalyticsResponse)
async def cleanup_analytics(
    days_to_keep: int = Query(90, description="Number of days of data to keep", ge=30, le=365)
):
    """Clean up old analytics data."""
    try:
        tracker = get_analytics_tracker()
        if not tracker:
            raise HTTPException(500, detail="Analytics tracker not initialized")
        
        deleted_count = await tracker.cleanup_old_data(days_to_keep)
        
        return AnalyticsResponse(
            success=True,
            data={"deleted_records": deleted_count},
            message=f"Cleaned up {deleted_count} old analytics records"
        )
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Failed to cleanup analytics: {e}")
        raise HTTPException(500, detail=f"Failed to cleanup analytics: {str(e)}")
