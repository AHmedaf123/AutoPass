"""
Application ORM Model
SQLAlchemy model for job applications
"""
import uuid
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from core.database import Base


class ApplicationModel(Base):
    """Job application table ORM model"""
    
    __tablename__ = "applications"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Foreign Keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_listings.id"), nullable=False, index=True)
    
    # Application Details
    status = Column(String(50), nullable=False, default="pending", index=True)
    applied_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Resume Used
    resume_url = Column(String(500), nullable=False)
    cover_letter = Column(Text, nullable=True)
    
    # Tracking
    source_application_id = Column(String(255), nullable=True)
    confirmation_email = Column(String(500), nullable=True)
    
    # Follow-up
    last_status_check = Column(DateTime(timezone=True), nullable=True)
    interview_scheduled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Timestamps
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<ApplicationModel {self.id} - {self.status}>"
