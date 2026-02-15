"""
Job Filters ORM Model
SQLAlchemy model for tracking applied LinkedIn search filters (audit trail)
"""
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from core.database import Base


class JobFilterModel(Base):
    """Job filters audit table - tracks applied search filters for auditing"""
    
    __tablename__ = "job_filters"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Foreign Key
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # Filter Details
    filter_name = Column(String(100), nullable=False)  # e.g., "experience_level", "work_type", "location"
    filter_value = Column(String(500), nullable=False)  # e.g., "Mid-Senior level", "Remote", "Pakistan"
    
    # Applied timestamp
    applied_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # Optional: Task ID for tracking which scraping task used these filters
    task_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    
    # Optional: Search URL for reference
    search_url = Column(String(2000), nullable=True)
    
    # Optional: Job title associated with this filter application
    job_title = Column(String(255), nullable=True)
    
    # Verification status (whether filters were confirmed on page)
    verified = Column(String(20), default="pending", nullable=False)  # "pending", "verified", "failed"
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Composite index for efficient queries
    __table_args__ = (
        Index('idx_user_filter_applied', 'user_id', 'filter_name', 'applied_at'),
        Index('idx_task_filters', 'task_id', 'applied_at'),
    )
    
    def __repr__(self):
        return f"<JobFilterModel user_id={self.user_id} filter={self.filter_name}={self.filter_value}>"
