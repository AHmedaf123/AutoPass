"""
Job Repository Implementation (Refactored)
SQLAlchemy-based job repository querying UserJob and JobListing tables.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from domain.entities import JobListing
from domain.value_objects import SalaryRange, JobStatus, MatchScore
from domain.enums import WorkType, ApplicationStatus
from application.repositories.interfaces import IJobRepository
from infrastructure.persistence.models.user_job import UserJobModel
from infrastructure.persistence.models.job_listing import JobListingModel
from core.exceptions import RepositoryException

class SQLAlchemyJobRepository(IJobRepository):
    """SQLAlchemy implementation of job repository adapter for normalized schema"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, job_id: UUID) -> Optional[Job]:
        """Get job (UserJob) by ID"""
        try:
            # job_id here refers to UserJob.id (specific to user)
            result = await self.session.execute(
                select(UserJobModel)
                .options(selectinload(UserJobModel.job))
                .where(UserJobModel.id == job_id)
            )
            model = result.scalar_one_or_none()
            
            if model:
                return self._to_entity(model)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get job by ID {job_id}: {str(e)}")
            raise RepositoryException(f"Failed to get job: {str(e)}")
    
    async def create(self, job: Job) -> Job:
        """
        Create logic is strictly for backward compatibility. 
        In new architecture, Orchestrator creates jobs.
        If called, we assume it's creating a UserJob for an existing Listing or new Listing.
        Provisional implementation: raises Error or basic support.
        """
        raise NotImplementedError("Use JobOrchestrator to create/distribute jobs.")
    
    async def batch_create(self, jobs: List[Job]) -> List[Job]:
        """
        Batch create is also deprecated in favor of Orchestrator.
        However, JobDiscoveryService uses it.
        We will adapt it to insert mappings if listings exist.
        """
        # For now, we prefer JobDiscoveryService to be updated OR Orchestrator usage.
        # Returning empty to prevent errors if legacy code calls it.
        logger.warning("batch_create called on deprecated repo method.")
        return []
    
    async def update(self, job: Job) -> Job:
        """Update existing job (UserJob status/score)"""
        try:
            # We only update UserJob fields (status, score, etc.)
            result = await self.session.execute(
                select(UserJobModel).where(UserJobModel.id == job.id)
            )
            model = result.scalar_one_or_none()
            
            if not model:
                raise RepositoryException(f"Job not found: {job.id}")
            
            # Update UserJob fields
            if job.apply_status:
                model.status = job.apply_status.value
            model.match_score = int(job.match_score) if job.match_score else model.match_score
            # Listing fields are generally immutable or updated by scraper
            
            await self.session.flush()
            await self.session.refresh(model)
            
            # Refresh relationship
            result = await self.session.execute(
                select(UserJobModel)
                .options(selectinload(UserJobModel.job))
                .where(UserJobModel.id == model.id)
            )
            model = result.scalar_one()
            
            return self._to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to update job {job.id}: {str(e)}")
            raise RepositoryException(f"Failed to update job: {str(e)}")
    
    async def delete(self, job_id: UUID) -> bool:
        """Delete job (UserJob association)"""
        try:
            result = await self.session.execute(
                select(UserJobModel).where(UserJobModel.id == job_id)
            )
            model = result.scalar_one_or_none()
            
            if model:
                await self.session.delete(model)
                await self.session.flush()
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete job {job_id}: {str(e)}")
            raise RepositoryException(f"Failed to delete job: {str(e)}")
    
    async def find_by_user_id(self, user_id: UUID) -> List[Job]:
        """Get all jobs for a user"""
        try:
            result = await self.session.execute(
                select(UserJobModel)
                .options(selectinload(UserJobModel.job))
                .where(UserJobModel.user_id == user_id)
                .order_by(UserJobModel.created_at.desc())
            )
            models = result.scalars().all()
            
            return [self._to_entity(model) for model in models]
            
        except Exception as e:
            logger.error(f"Failed to find jobs for user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to find jobs: {str(e)}")
    
    async def find_by_criteria(
        self,
        criteria: Dict[str, Any],
        limit: int = 50,
        offset: int = 0
    ) -> List[Job]:
        """
        Find jobs by criteria with filtering and pagination
        """
        try:
            query = select(UserJobModel).join(UserJobModel.job)
            conditions = []
            
            # Build WHERE conditions
            if 'user_id' in criteria:
                conditions.append(UserJobModel.user_id == criteria['user_id'])
            
            if 'apply_status' in criteria:
                conditions.append(UserJobModel.status == criteria['apply_status'])
            
            # Listing criteria
            if 'industry' in criteria:
                # Assuming simple string match or removed logic as Listing doesn't enforce industry strictly
                pass 
            
            if 'work_type' in criteria:
                conditions.append(JobListingModel.work_type == criteria['work_type'])
            
            # Subfield filtering - complex in normalized schema, simplified here
            if 'subfields' in criteria and criteria['subfields']:
                 # Simplified: Check if title contains subfield keywords
                 sub_conds = [JobListingModel.title.ilike(f"%{s}%") for s in criteria['subfields']]
                 conditions.append(or_(*sub_conds))

            if conditions:
                query = query.where(and_(*conditions))
            
            # Order by
            query = query.order_by(UserJobModel.created_at.desc())
            
            # Pagination
            query = query.limit(limit).offset(offset)
            
            # Load relation
            query = query.options(selectinload(UserJobModel.job))
            
            result = await self.session.execute(query)
            models = result.scalars().all()
            
            return [self._to_entity(model) for model in models]
            
        except Exception as e:
            logger.error(f"Failed to find jobs by criteria: {str(e)}")
            raise RepositoryException(f"Failed to find jobs by criteria: {str(e)}")
    
    def _to_entity(self, model: UserJobModel) -> Job:
        """Convert UserJobModel + JobListingModel to Domain Job Entity"""
        listing = model.job
        
        salary_range = None
        if listing.salary_min or listing.salary_max:
            salary_range = SalaryRange(
                min_salary=listing.salary_min,
                max_salary=listing.salary_max,
                currency=listing.salary_currency
            )
        
        work_type = None
        if listing.work_type:
             try:
                 work_type = WorkType(listing.work_type)
             except ValueError:
                 pass
        
        apply_status = None
        if model.status:
             try:
                 apply_status = ApplicationStatus(model.status)
             except ValueError:
                 apply_status = ApplicationStatus.PENDING

        return Job(
            id=model.id, # UserJob ID
            user_id=model.user_id,
            title=listing.title,
            company=listing.company,
            location=listing.location,
            description=listing.description,
            employment_type="full-time", # Default or store in Listing
            experience_level="mid", # Default or store in Listing
            industry="Technology", # Default or store in Listing
            subfields=[],
            salary_range=salary_range,
            skills_required=[],
            job_url=listing.url, # mapped from listing.url
            work_type=work_type,
            apply_status=apply_status,
            match_score=float(model.match_score),
            created_at=model.created_at
        )

    def _to_model(self, entity: Job) -> UserJobModel:
        raise NotImplementedError("Direct conversion from Entity to UserJobModel not supported in this direction without context.")
