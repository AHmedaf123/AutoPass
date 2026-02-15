"""
Session Metrics Service - Track and analyze session activity
Provides analytics on tasks completed, errors, retries, active sessions, and duration
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from loguru import logger

from infrastructure.persistence.models.session import SessionModel, SessionStatus
from infrastructure.persistence.models.apply_queue import ApplyQueueModel, TaskStatus, TaskType


class SessionMetrics:
    """Container for session metrics data"""
    
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc)
        self.total_sessions = 0
        self.active_sessions = 0
        self.idle_sessions = 0
        self.tainted_sessions = 0
        self.disposed_sessions = 0
        self.failed_sessions = 0
        
        self.total_tasks = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        self.pending_tasks = 0
        self.processing_tasks = 0
        self.total_retries = 0
        self.average_retries = 0.0
        
        self.total_errors = 0
        self.error_distribution = {}  # By error type
        self.health_issues_detected = 0
        self.by_health_issue = {}  # 429_error, expired_session, checkpoint
        
        self.average_task_duration_seconds = 0.0
        self.average_session_duration_seconds = 0.0
        self.average_task_success_rate = 0.0
        
        self.top_error_messages: List[Dict] = []
        self.top_health_issues: List[Dict] = []
        self.recent_failed_tasks: List[Dict] = []
        self.user_session_breakdown: Dict[str, Dict] = {}  # By user


class SessionMetricsService:
    """Calculate and track session metrics"""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def calculate_metrics(self) -> SessionMetrics:
        """Calculate comprehensive session metrics"""
        metrics = SessionMetrics()
        
        try:
            # Session counts
            metrics.total_sessions, session_breakdown = await self._get_session_counts()
            metrics.active_sessions = session_breakdown.get('active', 0)
            metrics.idle_sessions = session_breakdown.get('idle', 0)
            metrics.tainted_sessions = session_breakdown.get('tainted', 0)
            metrics.disposed_sessions = session_breakdown.get('disposed', 0)
            metrics.failed_sessions = session_breakdown.get('failed', 0)
            
            # Task counts
            metrics.total_tasks, task_breakdown = await self._get_task_counts()
            metrics.completed_tasks = task_breakdown.get('completed', 0)
            metrics.failed_tasks = task_breakdown.get('failed', 0)
            metrics.pending_tasks = task_breakdown.get('pending', 0)
            metrics.processing_tasks = task_breakdown.get('processing', 0)
            
            # Retry metrics
            metrics.total_retries = await self._get_total_retries()
            metrics.average_retries = await self._get_average_retries()
            
            # Error metrics
            metrics.total_errors = await self._get_total_errors()
            metrics.error_distribution = await self._get_error_distribution()
            metrics.top_error_messages = await self._get_top_errors(limit=5)
            
            # Health check metrics
            metrics.health_issues_detected = await self._get_health_issues_count()
            metrics.by_health_issue = await self._get_health_issues_breakdown()
            metrics.top_health_issues = await self._get_top_health_issues(limit=5)
            
            # Duration metrics
            metrics.average_task_duration_seconds = await self._get_average_task_duration()
            metrics.average_session_duration_seconds = await self._get_average_session_duration()
            metrics.average_task_success_rate = await self._get_task_success_rate()
            
            # Recent failures
            metrics.recent_failed_tasks = await self._get_recent_failed_tasks(limit=5)
            
            # User breakdown
            metrics.user_session_breakdown = await self._get_user_session_breakdown()
            
            logger.info("✅ Session metrics calculated successfully")
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            return metrics
    
    async def _get_session_counts(self) -> tuple[int, Dict[str, int]]:
        """Get total session count and breakdown by status"""
        result = await self.db.execute(
            select(SessionModel.status, func.count(SessionModel.id).label('count'))
            .group_by(SessionModel.status)
        )
        
        breakdown = {}
        total = 0
        for row in result.all():
            count = row.count
            total += count
            status = row.status.value if hasattr(row.status, 'value') else str(row.status)
            breakdown[status] = count
        
        return total, breakdown
    
    async def _get_task_counts(self) -> tuple[int, Dict[str, int]]:
        """Get total task count and breakdown by status"""
        result = await self.db.execute(
            select(ApplyQueueModel.status, func.count(ApplyQueueModel.id).label('count'))
            .group_by(ApplyQueueModel.status)
        )
        
        breakdown = {}
        total = 0
        for row in result.all():
            count = row.count
            total += count
            status = row.status.value if hasattr(row.status, 'value') else str(row.status)
            breakdown[status] = count
        
        return total, breakdown
    
    async def _get_total_retries(self) -> int:
        """Get total retry count"""
        result = await self.db.execute(
            select(func.sum(ApplyQueueModel.retries))
        )
        total = result.scalar() or 0
        return total
    
    async def _get_average_retries(self) -> float:
        """Get average retries per task"""
        result = await self.db.execute(
            select(func.avg(ApplyQueueModel.retries))
        )
        avg = result.scalar() or 0.0
        return round(float(avg), 2)
    
    async def _get_total_errors(self) -> int:
        """Get count of tasks with errors"""
        result = await self.db.execute(
            select(func.count(ApplyQueueModel.id))
            .where(ApplyQueueModel.error_message.isnot(None))
        )
        return result.scalar() or 0
    
    async def _get_error_distribution(self) -> Dict[str, int]:
        """Get error type distribution"""
        result = await self.db.execute(
            select(ApplyQueueModel.error_message, func.count(ApplyQueueModel.id).label('count'))
            .where(ApplyQueueModel.error_message.isnot(None))
            .group_by(ApplyQueueModel.error_message)
            .limit(10)
        )
        
        distribution = {}
        for row in result.all():
            # Extract error type from message
            msg = row.error_message or "Unknown"
            error_type = msg.split(':')[0][:50]  # First part, max 50 chars
            distribution[error_type] = distribution.get(error_type, 0) + row.count
        
        return distribution
    
    async def _get_top_errors(self, limit: int = 5) -> List[Dict]:
        """Get most common error messages"""
        result = await self.db.execute(
            select(
                ApplyQueueModel.error_message,
                func.count(ApplyQueueModel.id).label('count'),
                func.max(ApplyQueueModel.last_error_at).label('last_seen')
            )
            .where(ApplyQueueModel.error_message.isnot(None))
            .group_by(ApplyQueueModel.error_message)
            .order_by(func.count(ApplyQueueModel.id).desc())
            .limit(limit)
        )
        
        errors = []
        for row in result.all():
            errors.append({
                "message": row.error_message[:100],  # Truncate
                "count": row.count,
                "last_seen": row.last_seen.isoformat() if row.last_seen else None
            })
        
        return errors
    
    async def _get_health_issues_count(self) -> int:
        """Get count of sessions with health issues detected"""
        result = await self.db.execute(
            select(func.count(SessionModel.id))
            .where(SessionModel.health_issues_detected > 0)
        )
        return result.scalar() or 0
    
    async def _get_health_issues_breakdown(self) -> Dict[str, int]:
        """Get health issues breakdown by type"""
        result = await self.db.execute(
            select(SessionModel.last_health_issue, func.count(SessionModel.id).label('count'))
            .where(SessionModel.last_health_issue.isnot(None))
            .group_by(SessionModel.last_health_issue)
        )
        
        breakdown = {}
        for row in result.all():
            issue_type = row.last_health_issue or "unknown"
            breakdown[issue_type] = row.count
        
        return breakdown
    
    async def _get_top_health_issues(self, limit: int = 5) -> List[Dict]:
        """Get most common health issues"""
        result = await self.db.execute(
            select(
                SessionModel.last_health_issue,
                func.count(SessionModel.id).label('count'),
                func.max(SessionModel.last_health_check).label('last_seen')
            )
            .where(SessionModel.last_health_issue.isnot(None))
            .group_by(SessionModel.last_health_issue)
            .order_by(func.count(SessionModel.id).desc())
            .limit(limit)
        )
        
        issues = []
        for row in result.all():
            issues.append({
                "type": row.last_health_issue,
                "count": row.count,
                "last_seen": row.last_seen.isoformat() if row.last_seen else None
            })
        
        return issues
    
    async def _get_average_task_duration(self) -> float:
        """Get average task completion time in seconds"""
        result = await self.db.execute(
            select(
                func.avg(
                    func.extract('epoch', ApplyQueueModel.completed_at - ApplyQueueModel.started_at)
                )
            )
            .where(
                and_(
                    ApplyQueueModel.status == TaskStatus.COMPLETED,
                    ApplyQueueModel.started_at.isnot(None),
                    ApplyQueueModel.completed_at.isnot(None)
                )
            )
        )
        
        avg = result.scalar() or 0.0
        return round(float(avg), 2)
    
    async def _get_average_session_duration(self) -> float:
        """Get average session lifetime in seconds"""
        result = await self.db.execute(
            select(func.avg(SessionModel.session_duration_seconds))
            .where(SessionModel.session_duration_seconds.isnot(None))
        )
        
        avg = result.scalar() or 0.0
        return round(float(avg), 2)
    
    async def _get_task_success_rate(self) -> float:
        """Get percentage of tasks that completed successfully"""
        result = await self.db.execute(
            select(
                func.count(ApplyQueueModel.id).filter(ApplyQueueModel.status == TaskStatus.COMPLETED).label('completed'),
                func.count(ApplyQueueModel.id).label('total')
            )
        )
        
        row = result.first()
        if row and row.total > 0:
            rate = (row.completed / row.total) * 100
            return round(rate, 2)
        
        return 0.0
    
    async def _get_recent_failed_tasks(self, limit: int = 5) -> List[Dict]:
        """Get recently failed tasks"""
        result = await self.db.execute(
            select(
                ApplyQueueModel.id,
                ApplyQueueModel.task_type,
                ApplyQueueModel.error_message,
                ApplyQueueModel.completed_at,
                ApplyQueueModel.retries
            )
            .where(ApplyQueueModel.status == TaskStatus.FAILED)
            .order_by(ApplyQueueModel.completed_at.desc())
            .limit(limit)
        )
        
        tasks = []
        for row in result.all():
            tasks.append({
                "task_id": str(row.id),
                "type": row.task_type.value if hasattr(row.task_type, 'value') else str(row.task_type),
                "error": row.error_message[:80] if row.error_message else None,
                "failed_at": row.completed_at.isoformat() if row.completed_at else None,
                "retries": row.retries
            })
        
        return tasks
    
    async def _get_user_session_breakdown(self) -> Dict[str, Dict]:
        """Get session breakdown by user"""
        result = await self.db.execute(
            select(
                SessionModel.user_id,
                func.count(SessionModel.id).label('total_sessions'),
                func.count(SessionModel.id).filter(SessionModel.status == SessionStatus.ACTIVE).label('active'),
                func.count(SessionModel.id).filter(SessionModel.status == SessionStatus.IDLE).label('idle'),
                func.count(SessionModel.id).filter(SessionModel.status == SessionStatus.TAINTED).label('tainted'),
                func.sum(SessionModel.tasks_completed).label('total_tasks'),
                func.avg(SessionModel.session_duration_seconds).label('avg_duration')
            )
            .group_by(SessionModel.user_id)
        )
        
        breakdown = {}
        for row in result.all():
            user_id = str(row.user_id)
            breakdown[user_id] = {
                "total_sessions": row.total_sessions,
                "active": row.active or 0,
                "idle": row.idle or 0,
                "tainted": row.tainted or 0,
                "total_tasks_completed": row.total_tasks or 0,
                "avg_session_duration": round(float(row.avg_duration) if row.avg_duration else 0, 2)
            }
        
        return breakdown


def get_metrics_service(db_session: AsyncSession) -> SessionMetricsService:
    """Factory function to get metrics service"""
    return SessionMetricsService(db_session)
