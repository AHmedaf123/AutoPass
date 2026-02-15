"""
Auto-Apply Service Interface
Defines the contract for automated job application services
"""
from abc import ABC, abstractmethod
from typing import Dict, List
from uuid import UUID

from domain.enums import ApplicationStatus


class IAutoApplyService(ABC):
    """Interface for auto-apply services"""
    
    @abstractmethod
    async def apply_to_jobs(
        self,
        user_id: UUID,
        job_ids: List[UUID]
    ) -> Dict[UUID, ApplicationStatus]:
        """
        Apply to multiple jobs automatically
        
        Args:
            user_id: User ID
            job_ids: List of job IDs to apply to
            
        Returns:
            Dictionary mapping job_id to application status
        """
        pass
