"""
Job Filter Repository
Handles database operations for filter audit trail
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from infrastructure.persistence.models.job_filter import JobFilterModel


class JobFilterRepository:
    """Repository for job_filters table operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        user_id: UUID,
        filter_name: str,
        filter_value: str,
        task_id: Optional[UUID] = None,
        search_url: Optional[str] = None,
        job_title: Optional[str] = None,
        verified: str = "pending"
    ) -> JobFilterModel:
        """
        Create a new filter audit record
        
        Args:
            user_id: User UUID
            filter_name: Name of filter (e.g., "experience_level", "work_type")
            filter_value: Value of filter (e.g., "Mid-Senior level", "Remote")
            task_id: Optional task ID that applied this filter
            search_url: Optional LinkedIn search URL
            job_title: Optional job title being searched
            verified: Verification status ("pending", "verified", "failed")
            
        Returns:
            JobFilterModel instance
        """
        filter_record = JobFilterModel(
            user_id=user_id,
            filter_name=filter_name,
            filter_value=filter_value,
            task_id=task_id,
            search_url=search_url,
            job_title=job_title,
            verified=verified
        )
        
        self.session.add(filter_record)
        await self.session.flush()
        
        logger.debug(f"Created filter audit: {filter_name}={filter_value} for user {user_id}")
        return filter_record
    
    async def create_bulk(
        self,
        user_id: UUID,
        filters: List[dict],
        task_id: Optional[UUID] = None,
        search_url: Optional[str] = None,
        job_title: Optional[str] = None
    ) -> List[JobFilterModel]:
        """
        Create multiple filter audit records at once
        
        Args:
            user_id: User UUID
            filters: List of dicts with 'filter_name', 'filter_value', 'verified' keys
            task_id: Optional task ID
            search_url: Optional search URL
            job_title: Optional job title
            
        Returns:
            List of JobFilterModel instances
        """
        records = []
        for filter_data in filters:
            filter_record = JobFilterModel(
                user_id=user_id,
                filter_name=filter_data.get("filter_name"),
                filter_value=filter_data.get("filter_value"),
                task_id=task_id,
                search_url=search_url,
                job_title=job_title,
                verified=filter_data.get("verified", "pending")
            )
            self.session.add(filter_record)
            records.append(filter_record)
        
        await self.session.flush()
        logger.info(f"Created {len(records)} filter audit records for user {user_id}")
        return records
    
    async def update_verification_status(
        self,
        filter_id: UUID,
        verified: str
    ) -> Optional[JobFilterModel]:
        """
        Update verification status of a filter record
        
        Args:
            filter_id: Filter record UUID
            verified: New status ("verified", "failed")
            
        Returns:
            Updated JobFilterModel or None
        """
        result = await self.session.execute(
            select(JobFilterModel).where(JobFilterModel.id == filter_id)
        )
        filter_record = result.scalars().first()
        
        if filter_record:
            filter_record.verified = verified
            await self.session.flush()
            logger.debug(f"Updated filter {filter_id} verification to: {verified}")
        
        return filter_record
    
    async def get_by_task_id(self, task_id: UUID) -> List[JobFilterModel]:
        """
        Get all filter records for a specific task
        
        Args:
            task_id: Task UUID
            
        Returns:
            List of JobFilterModel instances
        """
        result = await self.session.execute(
            select(JobFilterModel)
            .where(JobFilterModel.task_id == task_id)
            .order_by(JobFilterModel.applied_at.desc())
        )
        return list(result.scalars().all())
    
    async def get_by_user(
        self,
        user_id: UUID,
        limit: int = 100
    ) -> List[JobFilterModel]:
        """
        Get filter records for a user (most recent first)
        
        Args:
            user_id: User UUID
            limit: Maximum number of records to return
            
        Returns:
            List of JobFilterModel instances
        """
        result = await self.session.execute(
            select(JobFilterModel)
            .where(JobFilterModel.user_id == user_id)
            .order_by(JobFilterModel.applied_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_by_user_and_filter(
        self,
        user_id: UUID,
        filter_name: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[JobFilterModel]:
        """
        Get specific filter records for a user within date range
        
        Args:
            user_id: User UUID
            filter_name: Filter name to search for
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            List of JobFilterModel instances
        """
        query = select(JobFilterModel).where(
            and_(
                JobFilterModel.user_id == user_id,
                JobFilterModel.filter_name == filter_name
            )
        )
        
        if start_date:
            query = query.where(JobFilterModel.applied_at >= start_date)
        if end_date:
            query = query.where(JobFilterModel.applied_at <= end_date)
        
        query = query.order_by(JobFilterModel.applied_at.desc())
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_verification_stats(self, user_id: UUID) -> dict:
        """
        Get verification statistics for a user
        
        Args:
            user_id: User UUID
            
        Returns:
            Dictionary with verification counts
        """
        result = await self.session.execute(
            select(JobFilterModel)
            .where(JobFilterModel.user_id == user_id)
        )
        all_filters = list(result.scalars().all())
        
        stats = {
            "total": len(all_filters),
            "verified": sum(1 for f in all_filters if f.verified == "verified"),
            "failed": sum(1 for f in all_filters if f.verified == "failed"),
            "pending": sum(1 for f in all_filters if f.verified == "pending")
        }
        
        return stats
