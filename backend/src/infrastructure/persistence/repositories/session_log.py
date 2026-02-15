"""
Session Log Repository Implementation
SQLAlchemy async repository for session logging
"""
from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from domain.entities.session_log import SessionLog
from infrastructure.persistence.models.session_log import SessionLogModel
from application.repositories.interfaces import ISessionLogRepository


class SessionLogRepository(ISessionLogRepository):
    """Session log repository using SQLAlchemy"""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def create(self, session_log: SessionLog) -> SessionLog:
        """Create new session log"""
        model = SessionLogModel(
            user_id=session_log.user_id,
            session_id=session_log.session_id,
            status=session_log.status,
            created_at=session_log.created_at,
            started_at=session_log.started_at,
            completed_at=session_log.completed_at,
            last_used=session_log.last_used,
            task_name=session_log.task_name,
            task_started_at=session_log.task_started_at,
            task_completed_at=session_log.task_completed_at,
            tasks_completed=session_log.tasks_completed,
            retries=session_log.retries,
            errors_count=session_log.errors_count,
            error_message=session_log.error_message,
            error_type=session_log.error_type,
            activity_log=session_log.activity_log,
            browser_type=session_log.browser_type,
            headless=1 if session_log.headless else 0,
            session_duration_seconds=session_log.session_duration_seconds,
            login_time_seconds=session_log.login_time_seconds,
            task_duration_seconds=session_log.task_duration_seconds,
            idle_time_seconds=session_log.idle_time_seconds,
            termination_reason=session_log.termination_reason,
        )
        
        self.db.add(model)
        await self.db.flush()
        return self._model_to_entity(model)
    
    async def get_by_session_id(self, session_id: str) -> Optional[SessionLog]:
        """Get session log by session ID"""
        query = select(SessionLogModel).where(
            SessionLogModel.session_id == session_id
        )
        result = await self.db.execute(query)
        model = result.scalar_one_or_none()
        
        return self._model_to_entity(model) if model else None
    
    async def get_user_sessions(
        self, 
        user_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[SessionLog]:
        """Get all session logs for a user"""
        query = select(SessionLogModel).where(
            SessionLogModel.user_id == user_id
        ).order_by(
            SessionLogModel.created_at.desc()
        ).limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        models = result.scalars().all()
        
        return [self._model_to_entity(model) for model in models]
    
    async def update(self, session_log: SessionLog) -> SessionLog:
        """Update session log"""
        model = await self.db.get(SessionLogModel, str(session_log.session_id))
        
        if not model:
            raise ValueError(f"Session log not found: {session_log.session_id}")
        
        # Update fields
        model.status = session_log.status
        model.started_at = session_log.started_at
        model.completed_at = session_log.completed_at
        model.last_used = session_log.last_used
        model.task_name = session_log.task_name
        model.task_started_at = session_log.task_started_at
        model.task_completed_at = session_log.task_completed_at
        model.tasks_completed = session_log.tasks_completed
        model.retries = session_log.retries
        model.errors_count = session_log.errors_count
        model.error_message = session_log.error_message
        model.error_type = session_log.error_type
        model.activity_log = session_log.activity_log
        model.session_duration_seconds = session_log.session_duration_seconds
        model.login_time_seconds = session_log.login_time_seconds
        model.task_duration_seconds = session_log.task_duration_seconds
        model.idle_time_seconds = session_log.idle_time_seconds
        model.termination_reason = session_log.termination_reason
        
        await self.db.flush()
        return self._model_to_entity(model)
    
    async def get_by_status(
        self,
        status: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[SessionLog]:
        """Get session logs by status"""
        query = select(SessionLogModel).where(
            SessionLogModel.status == status
        ).order_by(
            SessionLogModel.created_at.desc()
        ).limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        models = result.scalars().all()
        
        return [self._model_to_entity(model) for model in models]
    
    async def get_user_error_sessions(
        self,
        user_id: UUID,
        limit: int = 50
    ) -> List[SessionLog]:
        """Get session logs with errors for a user"""
        query = select(SessionLogModel).where(
            and_(
                SessionLogModel.user_id == user_id,
                SessionLogModel.status == "ERROR"
            )
        ).order_by(
            SessionLogModel.created_at.desc()
        ).limit(limit)
        
        result = await self.db.execute(query)
        models = result.scalars().all()
        
        return [self._model_to_entity(model) for model in models]
    
    async def get_user_statistics(self, user_id: UUID) -> dict:
        """Get aggregated statistics for user's sessions"""
        query = select(
            func.count(SessionLogModel.id).label("total_sessions"),
            func.sum(SessionLogModel.tasks_completed).label("total_tasks"),
            func.sum(SessionLogModel.retries).label("total_retries"),
            func.sum(SessionLogModel.errors_count).label("total_errors"),
            func.avg(SessionLogModel.session_duration_seconds).label("avg_session_duration"),
            func.avg(SessionLogModel.login_time_seconds).label("avg_login_time"),
            func.avg(SessionLogModel.task_duration_seconds).label("avg_task_duration"),
        ).where(
            SessionLogModel.user_id == user_id
        )
        
        result = await self.db.execute(query)
        row = result.one_or_none()
        
        if not row:
            return {
                "total_sessions": 0,
                "total_tasks": 0,
                "total_retries": 0,
                "total_errors": 0,
                "avg_session_duration": 0,
                "avg_login_time": 0,
                "avg_task_duration": 0,
            }
        
        return {
            "total_sessions": row[0] or 0,
            "total_tasks": row[1] or 0,
            "total_retries": row[2] or 0,
            "total_errors": row[3] or 0,
            "avg_session_duration": float(row[4] or 0),
            "avg_login_time": float(row[5] or 0),
            "avg_task_duration": float(row[6] or 0),
        }
    
    @staticmethod
    def _model_to_entity(model: SessionLogModel) -> SessionLog:
        """Convert SQLAlchemy model to domain entity"""
        return SessionLog(
            user_id=model.user_id,
            session_id=model.session_id,
            status=model.status,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            last_used=model.last_used,
            task_name=model.task_name,
            task_started_at=model.task_started_at,
            task_completed_at=model.task_completed_at,
            tasks_completed=model.tasks_completed,
            retries=model.retries,
            errors_count=model.errors_count,
            error_message=model.error_message,
            error_type=model.error_type,
            activity_log=model.activity_log,
            browser_type=model.browser_type,
            headless=bool(model.headless),
            session_duration_seconds=model.session_duration_seconds,
            login_time_seconds=model.login_time_seconds,
            task_duration_seconds=model.task_duration_seconds,
            idle_time_seconds=model.idle_time_seconds,
            termination_reason=model.termination_reason,
        )
