"""
Application Domain Entity
Immutable job application business object
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from ..value_objects import ApplicationStatus


@dataclass(frozen=True)
class Application:
    """Job application domain entity - immutable"""
    
    id: UUID
    user_id: UUID
    job_id: UUID
    
    # Application details
    status: ApplicationStatus
    applied_at: datetime
    
    # Resume used
    resume_url: str
    cover_letter: Optional[str] = None
    
    # Tracking
    source_application_id: Optional[str] = None  # External application ID
    confirmation_email: Optional[str] = None
    
    # Follow-up
    last_status_check: Optional[datetime] = None
    interview_scheduled_at: Optional[datetime] = None
    
    # Notes
    notes: Optional[str] = None
    
    # Timestamps
    updated_at: datetime = None
    
    def __post_init__(self):
        """Validate application data"""
        if not self.resume_url or len(self.resume_url.strip()) == 0:
            raise ValueError("Resume URL cannot be empty")
    
    def is_pending(self) -> bool:
        """Check if application is pending"""
        return self.status == ApplicationStatus.PENDING
    
    def is_successful(self) -> bool:
        """Check if application progressed beyond applied"""
        return self.status in {
            ApplicationStatus.REVIEWING,
            ApplicationStatus.INTERVIEWING,
            ApplicationStatus.OFFERED
        }
    
    def is_terminal(self) -> bool:
        """Check if application is in terminal state"""
        return self.status in {
            ApplicationStatus.OFFERED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN
        }
    
    def __str__(self) -> str:
        return f"Application({self.id}, status={self.status.value})"
