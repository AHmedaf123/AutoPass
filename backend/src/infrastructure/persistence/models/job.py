"""
Job ORM Model
SQLAlchemy model for job postings
"""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, JSON, Boolean, Float, ARRAY, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from core.database import Base


class JobModel(Base):
    """Job posting table ORM model"""
    
    __tablename__ = "jobs"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Basic Info
    title = Column(String(500), nullable=False, index=True)
    company = Column(String(255), nullable=False, index=True)
    location = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    
    # Job Details
    employment_type = Column(String(50), nullable=False, default="full-time")
    experience_level = Column(String(50), nullable=False, default="mid")
    industry = Column(String(100), nullable=False, index=True)
    subfields = Column(JSON, nullable=True)  # List[str] (Industry-specific subfields)
    
    # Salary
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    
    # URLs
    job_url = Column(String(1000), nullable=False)
    company_url = Column(String(1000), nullable=True)
    
    # Source
    source = Column(String(50), nullable=False, default="linkedin", index=True)
    external_id = Column(String(255), nullable=True, index=True)
    
    # Status
    status = Column(String(50), nullable=False, default="active", index=True)
    
    # Metadata (stored as JSON arrays)
    skills_required = Column(ARRAY(String), nullable=True)
    benefits = Column(ARRAY(String), nullable=True)
    remote_allowed = Column(Boolean, nullable=False, default=False)
    work_type = Column(String(50), nullable=True)  # Remote, Hybrid, Onsite
    
    # AI Match Score
    match_score = Column(Float, nullable=True)
    
    # Application Status
    apply_status = Column(String(50), nullable=True)  # success, failed, pending
    
    # Timestamps
    posted_date = Column(DateTime(timezone=True), nullable=True)
    expires_date = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<JobModel {self.title} at {self.company}>"
