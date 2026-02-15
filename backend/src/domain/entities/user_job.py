"""
UserJob Domain Entity
User-specific association with a job listing.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from ..enums import ApplicationStatus
from .job_listing import JobListing

@dataclass
class UserJob:
    """User-Job association domain entity"""
    
    id: UUID
    user_id: UUID
    job_id: UUID
    
    # Status
    status: ApplicationStatus = ApplicationStatus.PENDING
    match_score: int = 0
    is_new: bool = True
    
    # Timestamps
    created_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    
    # Relationship
    job_listing: Optional[JobListing] = None  # Loaded eagerly when needed
    
    def __str__(self) -> str:
        return f"UserJob(User: {self.user_id}, Job: {self.job_listing.title if self.job_listing else self.job_id})"
