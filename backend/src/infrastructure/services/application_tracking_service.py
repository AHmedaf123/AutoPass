"""
ApplicationTrackingService Implementation
Retrieves and filters user job applications
"""
from typing import List, Optional
from uuid import UUID

from application.services.application_tracking import IApplicationTrackingService
from application.repositories.interfaces import IJobRepository
from domain.entities import JobListing
from domain.enums import ApplicationStatus
from core.logging_config import logger


class ApplicationTrackingService(IApplicationTrackingService):
    """Application tracking service for querying user applications"""
    
    def __init__(
        self,
        job_repository: IJobRepository,
    ):
        """
        Initialize application tracking service
        
        Args:
            job_repository: Job repository
        """
        self.job_repo = job_repository
    
    async def get_applications(
        self,
        user_id: UUID,
        status: Optional[ApplicationStatus] = None
    ) -> List[Job]:
        """
        Get all job applications for a user, optionally filtered by status
        
        Args:
            user_id: User ID
            status: Optional application status filter
            
        Returns:
            List of Job entities
        """
        try:
            logger.info(f"Retrieving applications for user {user_id}, status filter: {status}")
            
            # Build search criteria
            criteria = {'user_id': user_id}
            if status:
                criteria['apply_status'] = status.value
            
            # Query repository
            jobs = await self.job_repo.find_by_criteria(criteria)
            
            logger.info(f"Found {len(jobs)} applications for user {user_id}")
            return jobs
        
        except Exception as e:
            logger.error(f"Error retrieving applications for user {user_id}: {e}")
            raise
    
    async def get_application_stats(
        self,
        user_id: UUID
    ) -> dict:
        """
        Get application statistics for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with counts by status
        """
        try:
            logger.info(f"Calculating application stats for user {user_id}")
            
            # Get all applications
            all_jobs = await self.job_repo.find_by_criteria({'user_id': user_id})
            
            # Count by status
            stats = {
                'total': len(all_jobs),
                'pending': 0,
                'applied': 0,
                'interviewing': 0,
                'rejected': 0,
                'accepted': 0,
            }
            
            for job in all_jobs:
                if job.apply_status:
                    status_key = job.apply_status.value.lower()
                    if status_key in stats:
                        stats[status_key] += 1
            
            logger.info(f"Application stats for user {user_id}: {stats}")
            return stats
        
        except Exception as e:
            logger.error(f"Error calculating application stats for user {user_id}: {e}")
            raise
