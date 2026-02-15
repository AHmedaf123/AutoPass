"""
UserJob Repository Implementation
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from sqlalchemy import select, and_, update, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.persistence.models.user_job import UserJobModel
from domain.entities.user_job import UserJob
from domain.enums import ApplicationStatus

class UserJobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, entity: UserJob) -> UserJob:
        """Convenience alias for create"""
        return await self.create(entity)

    async def create(self, entity: UserJob) -> UserJob:
        model = self._to_model(entity)
        self.session.add(model)
        # Flush to check for uniqueness?
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def exists(self, user_id: UUID, job_id: UUID) -> bool:
        result = await self.session.execute(
            select(UserJobModel)
            .where(and_(UserJobModel.user_id == user_id, UserJobModel.job_id == job_id))
            .order_by(UserJobModel.created_at.desc())
        )
        # Use first to avoid MultipleRowsFound when duplicates exist
        return result.scalars().first() is not None

    async def get_by_user_id(self, user_id: UUID) -> List[UserJob]:
        result = await self.session.execute(
            select(UserJobModel).where(UserJobModel.user_id == user_id)
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]
    
    async def get_by_user_and_job(self, user_id: UUID, job_id: UUID) -> Optional[UserJob]:
        """Get UserJob by user_id and job_id combination
        
        Note: If multiple entries exist (duplicates), returns the first one
        and logs a warning about duplicates for cleanup
        """
        result = await self.session.execute(
            select(UserJobModel).where(
                and_(UserJobModel.user_id == user_id, UserJobModel.job_id == job_id)
            ).order_by(UserJobModel.created_at.desc())
        )
        models = result.scalars().all()
        
        if not models:
            return None
        
        if len(models) > 1:
            from core.logging_config import logger
            logger.warning(f"Found {len(models)} duplicate UserJob entries for user={user_id}, job={job_id}. Returning latest one.")
        
        return self._to_entity(models[0]) if models else None
    
    async def update_status(
        self, 
        user_id: UUID, 
        job_id: UUID, 
        status: ApplicationStatus,
        applied_at: Optional[datetime] = None
    ) -> bool:
        """
        Update application status for a user-job pair.
        
        Args:
            user_id: User ID
            job_id: Job ID
            status: New application status
            applied_at: Timestamp when applied (defaults to now if status is APPLIED)
            
        Returns:
            True if updated, False if not found
        """
        # If status is APPLIED and no applied_at provided, use current time
        if status == ApplicationStatus.APPLIED and applied_at is None:
            applied_at = datetime.utcnow()
        
        stmt = (
            update(UserJobModel)
            .where(
                and_(
                    UserJobModel.user_id == user_id,
                    UserJobModel.job_id == job_id
                )
            )
            .values(
                status=status.value,
                applied_at=applied_at,
                is_new=False  # Mark as no longer new after status change
            )
        )
        
        result = await self.session.execute(stmt)
        await self.session.flush()
        
        return result.rowcount > 0
    
    async def get_pending_jobs(self, user_id: UUID, limit: int = 50) -> List[UserJob]:
        """Get pending (not yet applied) jobs for a user"""
        from sqlalchemy import func
        
        # Get the latest UserJob per job_id for pending jobs
        subquery = (
            select(
                UserJobModel.job_id,
                func.max(UserJobModel.created_at).label('max_created_at')
            )
            .where(
                and_(
                    UserJobModel.user_id == user_id,
                    UserJobModel.status == ApplicationStatus.PENDING.value
                )
            )
            .group_by(UserJobModel.job_id)
            .limit(limit)
            .subquery()
        )
        
        result = await self.session.execute(
            select(UserJobModel)
            .join(
                subquery,
                and_(
                    UserJobModel.job_id == subquery.c.job_id,
                    UserJobModel.created_at == subquery.c.max_created_at
                )
            )
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    def _to_model(self, entity: UserJob) -> UserJobModel:
        return UserJobModel(
            id=entity.id,
            user_id=entity.user_id,
            job_id=entity.job_id,
            status=entity.status.value,
            match_score=entity.match_score,
            is_new=entity.is_new,
            created_at=entity.created_at,
            applied_at=entity.applied_at
        )

    def _to_entity(self, model: UserJobModel) -> UserJob:
        return UserJob(
            id=model.id,
            user_id=model.user_id,
            job_id=model.job_id,
            status=ApplicationStatus(model.status),
            match_score=model.match_score,
            is_new=model.is_new,
            created_at=model.created_at,
            applied_at=model.applied_at
        )

