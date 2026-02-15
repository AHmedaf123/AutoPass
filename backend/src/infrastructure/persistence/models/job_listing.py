"""
JobListing Model (Persistence)
Centralized table for unique job postings shared across users.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean, UniqueConstraint, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from core.database import Base

class JobListingModel(Base):
    __tablename__ = "job_listings"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Deduplication Key: (platform + external_id)
    external_id = Column(String(255), nullable=False, index=True)
    platform = Column(String(50), nullable=False)  # "linkedin", "indeed", etc.
    
    # Job Details
    title = Column(String(500), nullable=False)
    company = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    work_type = Column(String(50), nullable=True)  # "Remote", "Hybrid", "Onsite"
    
    # Salary
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    salary_currency = Column(String(10), nullable=True, default="USD")
    
    # Description
    description = Column(Text, nullable=True)
    description_html = Column(Text, nullable=True)  # HTML version of description
    
    # LinkedIn-specific fields
    apply_link = Column(String(1000), nullable=True)  # Direct apply link
    easy_apply = Column(Boolean, default=False, nullable=False)  # Easy Apply availability
    insights = Column(JSON, default=[], nullable=False)  # Job insights
    skills = Column(JSON, default=[], nullable=False)  # Required skills
    
    # Metadata
    url = Column(String(1000), nullable=False)
    posted_date = Column(DateTime(timezone=True), nullable=True)
    
    # Pagination & Scraping Audit Trail
    page_number = Column(Integer, nullable=True, index=True)  # Which page was this job found on
    scraped_at = Column(DateTime(timezone=True), nullable=True, index=True)  # When was this job scraped
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('platform', 'external_id', name='uq_job_listing_platform_external_id'),
    )

    def __repr__(self):
        return f"<JobListingModel {self.title} at {self.company}>"
