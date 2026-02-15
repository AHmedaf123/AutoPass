from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from loguru import logger

from core.database import get_db
from application.services.session_metrics_service import (
    SessionMetricsService,
    SessionMetrics
)


# ============================================================================
# Pydantic Models for Response Serialization
# ============================================================================

class ErrorMetricResponse(BaseModel):
    """Single error metric"""
    message: str
    count: int
    last_seen: Optional[str]


class HealthIssueMetricResponse(BaseModel):
    """Single health issue metric"""
    type: str
    count: int
    last_seen: Optional[str]


class FailedTaskMetricResponse(BaseModel):
    """Failed task metric"""
    task_id: str
    type: str
    error: Optional[str]
    failed_at: Optional[str]
    retries: int


class UserBreakdownMetricResponse(BaseModel):
    """User session metrics"""
    total_sessions: int
    active: int
    idle: int
    tainted: int
    total_tasks_completed: int
    avg_session_duration: float


class SessionMetricsResponse(BaseModel):
    """Complete session metrics response"""
    timestamp: str
    
    # Session counts
    sessions: Dict[str, Any] = {}
    
    # Task counts and metrics
    tasks: Dict[str, Any] = {}
    
    # Error metrics
    errors: Dict[str, Any] = {}
    
    # Health check metrics
    health_checks: Dict[str, Any] = {}
    
    # Duration metrics
    duration: Dict[str, Any] = {}
    
    # Recent activity
    recent_failed_tasks: List[FailedTaskMetricResponse] = []
    
    # User breakdown
    user_breakdown: Dict[str, UserBreakdownMetricResponse] = {}


class MetricsHealthResponse(BaseModel):
    """Health check response for metrics endpoint"""
    status: str
    message: str
    timestamp: str


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin", "metrics"],
)


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/session-metrics", response_model=SessionMetricsResponse)
async def get_session_metrics(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get comprehensive session metrics and analytics
    
    Metrics include:
    - Session counts by status (active, idle, tainted, disposed, failed)
    - Task counts by status (completed, failed, pending, processing)
    - Retry statistics (total, average)
    - Error distribution and top errors
    - Health check metrics (issues detected, breakdown by type)
    - Duration metrics (average task duration, session duration, success rate)
    - Recent failed tasks
    - User session breakdown
    """
    try:
        metrics_service = SessionMetricsService(db)
        metrics = await metrics_service.calculate_metrics()
        
        # Build response
        response = {
            "timestamp": metrics.timestamp.isoformat(),
            
            # Session counts
            "sessions": {
                "total": metrics.total_sessions,
                "active": metrics.active_sessions,
                "idle": metrics.idle_sessions,
                "tainted": metrics.tainted_sessions,
                "disposed": metrics.disposed_sessions,
                "failed": metrics.failed_sessions,
            },
            
            # Task metrics
            "tasks": {
                "total": metrics.total_tasks,
                "completed": metrics.completed_tasks,
                "failed": metrics.failed_tasks,
                "pending": metrics.pending_tasks,
                "processing": metrics.processing_tasks,
                "total_retries": metrics.total_retries,
                "average_retries_per_task": metrics.average_retries,
                "success_rate_percent": metrics.average_task_success_rate,
            },
            
            # Error metrics
            "errors": {
                "total_errors": metrics.total_errors,
                "error_distribution": metrics.error_distribution,
                "top_errors": [
                    {
                        "message": err["message"],
                        "count": err["count"],
                        "last_seen": err["last_seen"]
                    }
                    for err in metrics.top_error_messages
                ],
            },
            
            # Health check metrics
            "health_checks": {
                "total_health_issues_detected": metrics.health_issues_detected,
                "issues_by_type": metrics.by_health_issue,
                "top_health_issues": [
                    {
                        "type": issue["type"],
                        "count": issue["count"],
                        "last_seen": issue["last_seen"]
                    }
                    for issue in metrics.top_health_issues
                ],
            },
            
            # Duration metrics
            "duration": {
                "average_task_duration_seconds": metrics.average_task_duration_seconds,
                "average_session_duration_seconds": metrics.average_session_duration_seconds,
            },
            
            # Recent activity
            "recent_failed_tasks": [
                {
                    "task_id": task["task_id"],
                    "type": task["type"],
                    "error": task["error"],
                    "failed_at": task["failed_at"],
                    "retries": task["retries"]
                }
                for task in metrics.recent_failed_tasks
            ],
            
            # User breakdown
            "user_breakdown": {
                user_id: {
                    "total_sessions": data["total_sessions"],
                    "active": data["active"],
                    "idle": data["idle"],
                    "tainted": data["tainted"],
                    "total_tasks_completed": data["total_tasks_completed"],
                    "avg_session_duration": data["avg_session_duration"]
                }
                for user_id, data in metrics.user_session_breakdown.items()
            },
        }
        
        logger.info(f"✅ Session metrics retrieved - {metrics.total_sessions} sessions, {metrics.total_tasks} tasks")
        return response
        
    except Exception as e:
        logger.error(f"Error retrieving session metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving metrics: {str(e)}"
        )


@router.get("/health", response_model=MetricsHealthResponse)
async def metrics_health(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """
    Health check endpoint for metrics service
    """
    try:
        metrics_service = SessionMetricsService(db)
        metrics = await metrics_service.calculate_metrics()
        
        # Consider healthy if we can query metrics
        return {
            "status": "healthy",
            "message": f"Metrics service operational - {metrics.total_sessions} sessions tracked",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Metrics health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Metrics service unavailable"
        )
