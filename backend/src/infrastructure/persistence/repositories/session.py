"""
Session Repository Implementation
SQLAlchemy async repository for tracking concurrent Selenium sessions
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from infrastructure.persistence.models.session import SessionModel, SessionStatus


class SessionRepository:
    """Session repository using SQLAlchemy for concurrent Selenium session tracking"""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def create_session(
        self,
        session_id: str,
        user_id: UUID,
        browser_type: str = "chrome",
        headless: bool = True,
        metadata: Optional[str] = None
    ) -> SessionModel:
        """Create a new session"""
        session = SessionModel(
            session_id=session_id,
            user_id=user_id,
            status=SessionStatus.ACTIVE,
            browser_type=browser_type,
            headless=1 if headless else 0,
            session_metadata=metadata,
        )
        self.db.add(session)
        await self.db.flush()
        return session
    
    async def get_session(self, session_id: str) -> Optional[SessionModel]:
        """Get session by ID"""
        query = select(SessionModel).where(
            SessionModel.session_id == session_id
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_active_sessions_for_user(self, user_id: UUID) -> List[SessionModel]:
        """Get all active sessions for a user"""
        query = select(SessionModel).where(
            and_(
                SessionModel.user_id == user_id,
                SessionModel.status == SessionStatus.ACTIVE
            )
        ).order_by(SessionModel.session_start.desc())
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def get_concurrent_sessions_for_user(self, user_id: UUID) -> List[SessionModel]:
        """Get all concurrent (active or in_use) sessions for a user"""
        query = select(SessionModel).where(
            and_(
                SessionModel.user_id == user_id,
                SessionModel.status.in_([SessionStatus.ACTIVE, SessionStatus.IN_USE, SessionStatus.IDLE])
            )
        ).order_by(SessionModel.session_start.desc())
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        task_id: Optional[UUID] = None,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None
    ) -> Optional[SessionModel]:
        """Update session status"""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        session.status = status
        session.last_activity = datetime.now(timezone.utc)
        
        if task_id:
            session.task_id = task_id
        
        if error_message:
            session.last_error_message = error_message
            session.error_count += 1
        
        if error_type:
            session.last_error_type = error_type
        
        await self.db.flush()
        return session
    
    async def complete_session(
        self,
        session_id: str,
        termination_reason: str = "completed"
    ) -> Optional[SessionModel]:
        """Complete and close a session"""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        session.status = SessionStatus.COMPLETED
        session.session_end = datetime.now(timezone.utc)
        session.termination_reason = termination_reason
        
        # Calculate session duration
        if session.session_start:
            duration = session.session_end - session.session_start
            session.session_duration_seconds = int(duration.total_seconds())
        
        await self.db.flush()
        return session
    
    async def mark_session_in_use(
        self,
        session_id: str,
        task_id: UUID
    ) -> Optional[SessionModel]:
        """Mark session as in use for a task"""
        return await self.update_session_status(
            session_id,
            SessionStatus.IN_USE,
            task_id=task_id
        )
    
    async def mark_session_idle(self, session_id: str) -> Optional[SessionModel]:
        """Mark session as idle (not currently processing)"""
        return await self.update_session_status(session_id, SessionStatus.IDLE)
    
    async def increment_task_count(self, session_id: str) -> Optional[SessionModel]:
        """Increment the task completion counter"""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        session.tasks_completed += 1
        session.last_activity = datetime.now(timezone.utc)
        await self.db.flush()
        return session
    
    async def set_login_time(self, session_id: str, login_time_seconds: int) -> Optional[SessionModel]:
        """Set the login time for the session"""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        session.login_time_seconds = login_time_seconds
        await self.db.flush()
        return session
    
    async def get_user_session_stats(self, user_id: UUID) -> dict:
        """Get session statistics for a user"""
        # Total sessions
        total_query = select(func.count(SessionModel.id)).where(
            SessionModel.user_id == user_id
        )
        total_result = await self.db.execute(total_query)
        total_sessions = total_result.scalar() or 0
        
        # Active sessions
        active_query = select(func.count(SessionModel.id)).where(
            and_(
                SessionModel.user_id == user_id,
                SessionModel.status == SessionStatus.ACTIVE
            )
        )
        active_result = await self.db.execute(active_query)
        active_sessions = active_result.scalar() or 0
        
        # Concurrent sessions (active + in_use + idle)
        concurrent_query = select(func.count(SessionModel.id)).where(
            and_(
                SessionModel.user_id == user_id,
                SessionModel.status.in_([SessionStatus.ACTIVE, SessionStatus.IN_USE, SessionStatus.IDLE])
            )
        )
        concurrent_result = await self.db.execute(concurrent_query)
        concurrent_sessions = concurrent_result.scalar() or 0
        
        # Average tasks per session
        avg_tasks_query = select(func.avg(SessionModel.tasks_completed)).where(
            SessionModel.user_id == user_id
        )
        avg_tasks_result = await self.db.execute(avg_tasks_query)
        avg_tasks = float(avg_tasks_result.scalar() or 0)
        
        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "concurrent_sessions": concurrent_sessions,
            "avg_tasks_per_session": avg_tasks,
        }
    
    async def cleanup_expired_sessions(
        self,
        user_id: UUID,
        timeout_seconds: int = 3600
    ) -> int:
        """
        Close sessions that haven't been used for timeout_seconds
        Returns count of closed sessions
        """
        cutoff_time = datetime.now(timezone.utc)
        cutoff_delta = cutoff_time.replace(second=0, microsecond=0)
        from datetime import timedelta
        cutoff_time = cutoff_delta - timedelta(seconds=timeout_seconds)
        
        query = select(SessionModel).where(
            and_(
                SessionModel.user_id == user_id,
                SessionModel.status.in_([SessionStatus.ACTIVE, SessionStatus.IDLE]),
                SessionModel.last_activity < cutoff_time
            )
        )
        
        result = await self.db.execute(query)
        expired_sessions = result.scalars().all()
        
        for session in expired_sessions:
            await self.complete_session(session.session_id, "timeout")
        
        return len(expired_sessions)
    
    async def get_user_session_history(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[SessionModel]:
        """Get session history for a user"""
        query = select(SessionModel).where(
            SessionModel.user_id == user_id
        ).order_by(
            SessionModel.session_start.desc()
        ).limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def dispose_session(
        self,
        session_id: str,
        termination_reason: str = "task_completed"
    ) -> Optional[SessionModel]:
        """
        Dispose/close a session after task completion.
        
        Marks session as DISPOSED with termination reason and completion time.
        """
        session = await self.get_session(session_id)
        if not session:
            return None
        
        session.status = SessionStatus.DISPOSED
        session.session_end = datetime.now(timezone.utc)
        session.termination_reason = termination_reason
        session.last_activity = datetime.now(timezone.utc)
        
        # Calculate final duration if session was tracked
        if session.session_start:
            duration = session.session_end - session.session_start
            session.session_duration_seconds = int(duration.total_seconds())
        
        await self.db.flush()
        return session
    
    async def cleanup_disposed_sessions(
        self,
        user_id: UUID,
        keep_last_n: int = 5
    ) -> int:
        """
        Clean up disposed sessions for a user, keeping only last N.
        
        Args:
            user_id: User whose disposed sessions to clean
            keep_last_n: Number of most recent disposed sessions to keep
            
        Returns:
            Count of sessions deleted
        """
        # Get disposed sessions ordered by completion (oldest first)
        query = select(SessionModel).where(
            and_(
                SessionModel.user_id == user_id,
                SessionModel.status == SessionStatus.DISPOSED
            )
        ).order_by(
            SessionModel.session_end.asc()
        )
        
        result = await self.db.execute(query)
        disposed_sessions = result.scalars().all()
        
        # Delete all but the last N
        if len(disposed_sessions) > keep_last_n:
            sessions_to_delete = disposed_sessions[:-keep_last_n]
            for session in sessions_to_delete:
                await self.db.delete(session)
            
            return len(sessions_to_delete)
        
        return 0
    
    async def cleanup_all_disposed_sessions(
        self,
        keep_per_user: int = 5
    ) -> int:
        """
        Clean up disposed sessions for all users.
        
        Args:
            keep_per_user: Number of most recent disposed sessions to keep per user
            
        Returns:
            Total count of sessions deleted
        """
        # Get all users with disposed sessions
        query = select(SessionModel.user_id).where(
            SessionModel.status == SessionStatus.DISPOSED
        ).distinct()
        
        result = await self.db.execute(query)
        user_ids = result.scalars().all()
        
        total_deleted = 0
        for user_id in user_ids:
            deleted = await self.cleanup_disposed_sessions(user_id, keep_per_user)
            total_deleted += deleted
        
        return total_deleted
    
    async def mark_session_disposed(
        self,
        session_id: str,
        reason: str = "task_completed"
    ) -> Optional[SessionModel]:
        """Alias for dispose_session for backward compatibility"""
        return await self.dispose_session(session_id, reason)
    
    async def mark_session_tainted(
        self,
        session_id: str,
        issue_type: str,
        reason: str = "health_check_failed"
    ) -> Optional[SessionModel]:
        """Mark session as TAINTED due to health issue (429, expired, checkpoint)
        
        Args:
            session_id: Session identifier
            issue_type: Type of health issue (429_error, expired_session, linkedin_checkpoint)
            reason: Reason for marking tainted
        
        Returns:
            Updated SessionModel or None if not found
        """
        session = await self.get_session(session_id)
        if not session:
            return None
        
        session.status = SessionStatus.TAINTED
        session.last_health_issue = issue_type
        session.health_issues_detected += 1
        session.last_health_check = datetime.now(timezone.utc)
        session.termination_reason = reason
        
        await self.db.flush()
        await self.db.refresh(session)
        return session
    
    async def record_health_check(
        self,
        session_id: str,
        issue_type: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[SessionModel]:
        """Record a health check event on session
        
        Args:
            session_id: Session identifier
            issue_type: Type of issue detected (if any)
            description: Human-readable description
        
        Returns:
            Updated SessionModel or None if not found
        """
        import json
        
        session = await self.get_session(session_id)
        if not session:
            return None
        
        session.health_check_count += 1
        session.last_health_check = datetime.now(timezone.utc)
        
        if issue_type:
            session.health_issues_detected += 1
            session.last_health_issue = issue_type
        
        # Append to health check log
        check_event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "check_number": session.health_check_count,
            "issue_detected": issue_type,
            "description": description
        }
        
        if session.health_check_log:
            try:
                log = json.loads(session.health_check_log)
            except:
                log = []
        else:
            log = []
        
        log.append(check_event)
        session.health_check_log = json.dumps(log)
        
        await self.db.flush()
        await self.db.refresh(session)
        return session
    
    async def get_tainted_sessions_for_user(self, user_id: UUID) -> List[SessionModel]:
        """Get all tainted sessions for a user"""
        query = select(SessionModel).where(
            and_(
                SessionModel.user_id == user_id,
                SessionModel.status == SessionStatus.TAINTED
            )
        ).order_by(SessionModel.last_health_check.desc())
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def cleanup_tainted_sessions(self, user_id: UUID) -> int:
        """Dispose of tainted sessions for a user
        
        Args:
            user_id: User identifier
        
        Returns:
            Count of sessions marked disposed
        """
        tainted = await self.get_tainted_sessions_for_user(user_id)
        
        count = 0
        for session in tainted:
            await self.dispose_session(session.session_id, "tainted_cleanup")
            count += 1
        
        return count
