"""
ApplyQueue Repository Implementation
Repository for managing async task queue operations
"""
import json
from typing import Optional, List
from uuid import UUID
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from core.logging_config import logger
from infrastructure.persistence.models.apply_queue import (
    ApplyQueueModel,
    TaskType,
    TaskStatus
)


class ApplyQueueRepository:
    """Repository for ApplyQueue operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: UUID, task_type: TaskType, job_url: Optional[str] = None, 
                    job_id: Optional[UUID] = None, priority: int = 5,
                    session_id: Optional[str] = None,
                    progress_data: Optional[str] = None) -> ApplyQueueModel:
        """Create a new task in the queue with priority"""
        model = ApplyQueueModel(
            user_id=user_id,
            task_type=task_type,
            job_url=job_url,
            job_id=job_id,
            status=TaskStatus.PENDING,
            priority=priority,
            retries=0,
            max_retries=3,
            progress_data=progress_data,
            session_id=session_id
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return model

    async def get_by_id(self, task_id: UUID) -> Optional[ApplyQueueModel]:
        """Get a task by its ID"""
        result = await self.session.execute(
            select(ApplyQueueModel).where(ApplyQueueModel.id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_tasks(self, limit: int = 10) -> List[ApplyQueueModel]:
        """Get pending tasks ordered by priority (highest first), then FIFO
        
        Respects exponential backoff: only returns tasks where next_attempt_time is NULL or in the past
        """
        now = datetime.utcnow()
        result = await self.session.execute(
            select(ApplyQueueModel)
            .where(
                ApplyQueueModel.status == TaskStatus.PENDING,
                or_(
                    ApplyQueueModel.next_attempt_time.is_(None),
                    ApplyQueueModel.next_attempt_time <= now
                )
            )
            .order_by(ApplyQueueModel.priority.desc(), ApplyQueueModel.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_user_tasks(self, user_id: UUID, limit: int = 50) -> List[ApplyQueueModel]:
        """Get all tasks for a specific user"""
        result = await self.session.execute(
            select(ApplyQueueModel)
            .where(ApplyQueueModel.user_id == user_id)
            .order_by(ApplyQueueModel.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_user_pending_tasks(self, user_id: UUID) -> List[ApplyQueueModel]:
        """Get pending tasks for a specific user"""
        result = await self.session.execute(
            select(ApplyQueueModel)
            .where(
                and_(
                    ApplyQueueModel.user_id == user_id,
                    ApplyQueueModel.status == TaskStatus.PENDING
                )
            )
            .order_by(ApplyQueueModel.created_at.asc())
        )
        return list(result.scalars().all())

    async def mark_processing(self, task_id: UUID, session_id: Optional[str] = None) -> Optional[ApplyQueueModel]:
        """Mark a task as processing and optionally store session_id"""
        model = await self.get_by_id(task_id)
        if model and model.status == TaskStatus.PENDING:
            model.status = TaskStatus.PROCESSING
            model.started_at = datetime.utcnow()
            if session_id:
                model.session_id = session_id
            await self.session.flush()
            await self.session.refresh(model)
            return model
        return None

    async def mark_completed(self, task_id: UUID) -> Optional[ApplyQueueModel]:
        """Mark a task as completed with execution duration"""
        model = await self.get_by_id(task_id)
        if model:
            model.status = TaskStatus.COMPLETED
            completed_time = datetime.utcnow()
            model.completed_at = completed_time
            
            # Log execution duration if started_at is available
            if model.started_at:
                duration = (completed_time - model.started_at).total_seconds()
                logger.info(f"✅ Task {task_id} completed in {duration:.1f}s")
            
            await self.session.flush()
            await self.session.refresh(model)
            return model
        return None

    async def mark_failed(self, task_id: UUID, error_message: str) -> Optional[ApplyQueueModel]:
        """Mark a task as failed with error message"""
        model = await self.get_by_id(task_id)
        if model:
            model.status = TaskStatus.FAILED
            model.error_message = error_message
            model.last_error_at = datetime.utcnow()
            model.completed_at = datetime.utcnow()
            await self.session.flush()
            await self.session.refresh(model)
            return model
        return None

    async def increment_retry(self, task_id: UUID, error_message: str) -> Optional[ApplyQueueModel]:
        """Increment retry count and update error message with exponential backoff
        
        Backoff schedule: 2s, 4s, 8s, 16s, 32s
        """
        model = await self.get_by_id(task_id)
        if model:
            model.retries += 1
            model.error_message = error_message
            model.last_error_at = datetime.utcnow()
            
            # Append to error log (JSON array)
            error_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "retry": model.retries,
                "message": error_message
            }
            
            if model.error_log:
                try:
                    error_log = json.loads(model.error_log)
                except:
                    error_log = []
            else:
                error_log = []
            
            error_log.append(error_entry)
            model.error_log = json.dumps(error_log)
            
            if model.retries >= model.max_retries:
                # Exceeded max retries, mark as failed
                model.status = TaskStatus.FAILED
                model.completed_at = datetime.utcnow()
                model.next_attempt_time = None
            else:
                # Reset to pending for retry with exponential backoff
                model.status = TaskStatus.PENDING
                
                # Exponential backoff: 2^retry_count seconds (2s, 4s, 8s, 16s, 32s)
                delay_seconds = 2 ** model.retries
                model.next_attempt_time = datetime.utcnow() + timedelta(seconds=delay_seconds)
                
            await self.session.flush()
            await self.session.refresh(model)
            return model
        return None

    async def update_progress(self, task_id: UUID, current_step: str, progress_data: Optional[str] = None) -> Optional[ApplyQueueModel]:
        """Update task progress"""
        model = await self.get_by_id(task_id)
        if model:
            model.current_step = current_step
            if progress_data:
                model.progress_data = progress_data
            await self.session.flush()
            await self.session.refresh(model)
            return model
        return None
    
    async def update_application_step(self, task_id: UUID, step: str, additional_data: Optional[dict] = None) -> Optional[ApplyQueueModel]:
        """Update application step with optional additional data
        
        Args:
            task_id: Task UUID
            step: Application step (navigation, button_click, form_filling, submission, completed)
            additional_data: Optional dict with step-specific data
            
        Returns:
            Updated ApplyQueueModel or None
        """
        model = await self.get_by_id(task_id)
        if model:
            model.current_step = step
            
            # Merge additional data into progress_data
            if additional_data:
                try:
                    if model.progress_data:
                        progress = json.loads(model.progress_data)
                    else:
                        progress = {}
                    
                    progress["last_step"] = step
                    progress["last_step_timestamp"] = datetime.utcnow().isoformat()
                    progress.update(additional_data)
                    
                    model.progress_data = json.dumps(progress, ensure_ascii=False)
                except Exception as e:
                    logger.warning(f"Failed to update progress_data: {e}")
            
            await self.session.flush()
            await self.session.refresh(model)
            logger.info(f"📊 Task {task_id} step updated: {step}")
            return model
        return None

    async def update_session_id(self, task_id: UUID, session_id: str) -> Optional[ApplyQueueModel]:
        """Update task session_id for tracking"""
        model = await self.get_by_id(task_id)
        if model:
            model.session_id = session_id
            await self.session.flush()
            await self.session.refresh(model)
            return model
        return None

    async def update_ai_response(self, task_id: UUID, ai_responses: dict) -> Optional[ApplyQueueModel]:
        """Update task with AI-generated form responses
        
        Args:
            task_id: Task UUID
            ai_responses: Dictionary of field_id -> answer mapping
            
        Returns:
            Updated ApplyQueueModel or None
        """
        model = await self.get_by_id(task_id)
        if model:
            # Serialize responses to JSON
            model.ai_response = json.dumps(ai_responses, ensure_ascii=False)
            await self.session.flush()
            await self.session.refresh(model)
            
            logger.info(f"💾 Stored {len(ai_responses)} AI form responses for task {task_id}")
            return model
        return None
    
    async def get_ai_response(self, task_id: UUID) -> Optional[dict]:
        """Retrieve AI-generated form responses for a task
        
        Args:
            task_id: Task UUID
            
        Returns:
            Dictionary of field_id -> answer or None
        """
        model = await self.get_by_id(task_id)
        if model and model.ai_response:
            try:
                return json.loads(model.ai_response)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Failed to deserialize AI responses for task {task_id}: {e}")
                return None
        return None

    async def get_task_stats(self, user_id: Optional[UUID] = None) -> dict:
        """Get task queue statistics"""
        base_query = select(ApplyQueueModel)
        if user_id:
            base_query = base_query.where(ApplyQueueModel.user_id == user_id)
        
        result = await self.session.execute(base_query)
        all_tasks = list(result.scalars().all())
        
        stats = {
            "total": len(all_tasks),
            "pending": sum(1 for t in all_tasks if t.status == TaskStatus.PENDING),
            "processing": sum(1 for t in all_tasks if t.status == TaskStatus.PROCESSING),
            "completed": sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in all_tasks if t.status == TaskStatus.FAILED),
            "retrying": sum(1 for t in all_tasks if t.status == TaskStatus.RETRYING),
        }
        
        return stats

    async def cleanup_old_completed_tasks(self, days: int = 7) -> int:
        """Delete completed tasks older than specified days"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        result = await self.session.execute(
            select(ApplyQueueModel)
            .where(
                and_(
                    ApplyQueueModel.status == TaskStatus.COMPLETED,
                    ApplyQueueModel.completed_at < cutoff_date
                )
            )
        )
        tasks = result.scalars().all()
        
        count = len(tasks)
        for task in tasks:
            await self.session.delete(task)
        
        await self.session.flush()
        return count
    async def enqueue_health_check_retry(
        self,
        task_id: UUID,
        issue_type: str,
        cooldown_seconds: int,
        error_message: str
    ) -> Optional[ApplyQueueModel]:
        """Enqueue task retry with health-check cooldown
        
        Called when session health check detects issues (429, expired, checkpoint).
        Sets longer cooldown than exponential backoff to allow issues to resolve.
        
        Args:
            task_id: Task UUID to retry
            issue_type: Type of health issue (429_error, expired_session, linkedin_checkpoint)
            cooldown_seconds: Cooldown duration before retry
            error_message: Description of health issue
            
        Returns:
            Updated ApplyQueueModel or None if not found
        """
        model = await self.get_by_id(task_id)
        if not model:
            return None
        
        model.retries += 1
        model.error_message = f"Health check failed: {error_message} (Issue: {issue_type})"
        model.last_error_at = datetime.utcnow()
        
        # Append to error log
        error_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "retry": model.retries,
            "message": error_message,
            "issue_type": issue_type,
            "cooldown_seconds": cooldown_seconds,
            "reason": "health_check_tainted"
        }
        
        if model.error_log:
            try:
                error_log = json.loads(model.error_log)
            except:
                error_log = []
        else:
            error_log = []
        
        error_log.append(error_entry)
        model.error_log = json.dumps(error_log)
        
        if model.retries >= model.max_retries:
            # Exceeded max retries
            model.status = TaskStatus.FAILED
            model.completed_at = datetime.utcnow()
            model.next_attempt_time = None
            logger.error(f"💀 Task {task_id} failed permanently after {model.retries} retries (health check issues)")
        else:
            # Reset to pending with health-check cooldown
            model.status = TaskStatus.PENDING
            model.next_attempt_time = datetime.utcnow() + timedelta(seconds=cooldown_seconds)
            
            logger.info(f"🔄 Task {task_id} will retry in {cooldown_seconds}s (health issue: {issue_type})")
            logger.info(f"   Retry: {model.retries}/{model.max_retries}")
            logger.info(f"   Issue: {error_message}")
        
        await self.session.flush()
        await self.session.refresh(model)
        return model