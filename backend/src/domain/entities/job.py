"""
Job Domain Entity
Immutable job posting business object
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from ..value_objects import SalaryRange, JobStatus
from ..enums import WorkType


@dataclass(frozen=True)
class Job:
    """Job posting domain entity - immutable"""
    
    id: UUID
    title: str
    company: str
    location: str
    description: str
    
    # Job details
    employment_type: str  # full-time, part-time, contract
    experience_level: str  # entry, mid, senior, lead
    industry: str
    subfields: Optional[List[str]] = None  # Industry-specific subfields
    
    # Salary
    salary_range: Optional[SalaryRange] = None
    
    # URLs
    job_url: str = ""
    company_url: Optional[str] = None
    
    # Source
    source: str = "linkedin"  # linkedin, indeed
    external_id: Optional[str] = None
    
    # Status
    status: JobStatus = JobStatus.ACTIVE
    
    # Metadata
    skills_required: List[str] = None
    benefits: List[str] = None
    remote_allowed: bool = False
    work_type: Optional[WorkType] = None
    
    # AI Match Score (0-100)
    match_score: Optional[float] = None
    
    # Application status (success, failed, pending)
    apply_status: Optional[str] = None
    
    # Timestamps
    posted_date: Optional[datetime] = None
    expires_date: Optional[datetime] = None
    fetched_at: datetime = None
    
    def __post_init__(self):
        """Validate job data"""
        if not self.title or len(self.title.strip()) == 0:
            raise ValueError("Job title cannot be empty")
        
        if not self.company or len(self.company.strip()) == 0:
            raise ValueError("Company name cannot be empty")
        
        if self.match_score is not None:
            if not (0 <= self.match_score <= 100):
                raise ValueError("Match score must be between 0 and 100")
    
    def is_active(self) -> bool:
        """Check if job is still active"""
        if self.status != JobStatus.ACTIVE:
            return False
        
        if self.expires_date and self.expires_date < datetime.utcnow():
            return False
        
        return True
    
    def is_good_match(self, threshold: float = 70.0) -> bool:
        """Check if job is a good match based on score"""
        return self.match_score is not None and self.match_score >= threshold
    
    def __str__(self) -> str:
        return f"Job({self.title} at {self.company})"
