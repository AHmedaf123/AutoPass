"""
JobListing Domain Entity
Immutable centralized job posting.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from ..value_objects import SalaryRange
from ..enums import WorkType

@dataclass(frozen=True)
class JobListing:
    """Centralized job listing domain entity"""
    
    id: Optional[UUID] = None
    external_id: str = ""
    platform: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    
    # Optional Details
    salary_range: Optional[SalaryRange] = None
    work_type: Optional[str] = None
    
    # New LinkedIn-specific fields
    description_html: Optional[str] = None
    apply_link: Optional[str] = None
    easy_apply: bool = False
    insights: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    
    # Salary breakdown
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = "USD"
    
    # Pagination & Scraping Audit Trail
    page_number: Optional[int] = None  # Which page was this job found on
    scraped_at: Optional[datetime] = None  # When was this job scraped
    
    # Timestamps
    posted_date: Optional[datetime] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    
    def __str__(self) -> str:
        return f"JobListing({self.title} at {self.company})"
