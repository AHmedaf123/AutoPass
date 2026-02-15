"""
Task Queue Service
Service for managing async job scraping tasks
"""
import json
from typing import Optional, List
from uuid import UUID

from loguru import logger

from infrastructure.persistence.repositories.apply_queue import ApplyQueueRepository
from infrastructure.persistence.models.apply_queue import TaskType, TaskStatus, TaskPriority
from sqlalchemy.ext.asyncio import AsyncSession


class TaskQueueService:
    """Service for managing task queue operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.queue_repo = ApplyQueueRepository(session)

    async def enqueue_job_scraping_task(
        self,
        user_id: UUID,
        job_titles: List[str],
        location: str,
        experience_level: Optional[str] = None,
        work_type: Optional[str] = None,
        search_urls: Optional[List[dict]] = None,
    ) -> UUID:
        """
        Enqueue a job scraping task
        
        Args:
            user_id: User UUID
            job_titles: List of job titles to search
            location: Location to search
            experience_level: Optional experience level filter
            work_type: Optional work type filter
            search_urls: Pre-generated LinkedIn search URLs (list of dicts with 'job_title' and 'url')
            
        Returns:
            Task ID (UUID)
        """
        # Store search parameters as JSON in progress_data
        search_params = {
            "job_titles": job_titles,
            "location": location,
            "experience_level": experience_level,
            "work_type": work_type,
            "search_urls": search_urls or [],  # Store pre-generated URLs
        }
        
        progress_data = json.dumps(search_params)
        
        logger.info(f"Enqueuing job scraping task for user {user_id}")
        logger.debug(f"Search params: {search_params}")
        
        if search_urls:
            logger.info(f"Task includes {len(search_urls)} pre-generated LinkedIn URLs")
        
        task = await self.queue_repo.create(
            user_id=user_id,
            task_type=TaskType.JOB_SCRAPING,
            job_url=None,  # Not applicable for scraping tasks
            priority=TaskPriority.NORMAL.value,  # Normal priority for job discovery
            progress_data=progress_data
        )
        
        await self.session.commit()
        
        logger.info(f"✅ Task {task.id} enqueued successfully")
        return task.id

    async def enqueue_job_application_task(
        self,
        user_id: UUID,
        job_id: UUID,
        job_url: str,
        session_id: Optional[str] = None,
    ) -> UUID:
        """
        Enqueue a job application task (Easy Apply)
        
        Args:
            user_id: User UUID
            job_id: Job UUID from database
            job_url: Job URL to apply to
            session_id: Active LinkedIn session identifier
            
        Returns:
            Task ID (UUID)
        """
        logger.info(f"Enqueuing job application task for user {user_id} using session {session_id}")
        
        task = await self.queue_repo.create(
            user_id=user_id,
            task_type=TaskType.JOB_APPLICATION,
            job_url=job_url,
            job_id=job_id,
            priority=TaskPriority.HIGH.value,  # HIGH priority for Easy Apply tasks
            session_id=session_id
        )
        
        await self.session.commit()
        
        logger.info(f"✅ Task {task.id} enqueued successfully with HIGH priority")
        return task.id

    async def get_task_status(self, task_id: UUID) -> Optional[dict]:
        """
        Get status of a specific task
        
        Args:
            task_id: Task UUID
            
        Returns:
            Dictionary with task status information
        """
        task = await self.queue_repo.get_by_id(task_id)
        
        if not task:
            return None
        
        return {
            "task_id": str(task.id),
            "user_id": str(task.user_id),
            "task_type": task.task_type.value,
            "status": task.status.value,
            "current_step": task.current_step,
            "retries": task.retries,
            "max_retries": task.max_retries,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }

    async def get_user_tasks(self, user_id: UUID, limit: int = 50) -> List[dict]:
        """
        Get all tasks for a user
        
        Args:
            user_id: User UUID
            limit: Maximum number of tasks to return
            
        Returns:
            List of task status dictionaries
        """
        tasks = await self.queue_repo.get_user_tasks(user_id, limit)
        
        return [
            {
                "task_id": str(task.id),
                "task_type": task.task_type.value,
                "status": task.status.value,
                "current_step": task.current_step,
                "retries": task.retries,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
            for task in tasks
        ]

    async def get_queue_stats(self, user_id: Optional[UUID] = None) -> dict:
        """
        Get task queue statistics
        
        Args:
            user_id: Optional user UUID to filter stats
            
        Returns:
            Dictionary with queue statistics
        """
        stats = await self.queue_repo.get_task_stats(user_id)
        return stats

    async def cancel_pending_tasks(self, user_id: UUID) -> int:
        """
        Cancel all pending tasks for a user
        
        Args:
            user_id: User UUID
            
        Returns:
            Number of tasks cancelled
        """
        tasks = await self.queue_repo.get_user_pending_tasks(user_id)
        
        count = 0
        for task in tasks:
            await self.queue_repo.mark_failed(task.id, "Cancelled by user")
            count += 1
        
        await self.session.commit()
        
        logger.info(f"Cancelled {count} pending tasks for user {user_id}")
        return count
