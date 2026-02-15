"""
UserJob Model (Persistence)
Junction table linking Users to JobListings.
"""
import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from core.database import Base
from domain.enums import ApplicationStatus


class UserJobModel(Base):
    __tablename__ = "user_jobs"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Foreign Keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Personalized Data
    status = Column(String(50), default=ApplicationStatus.PENDING.value, nullable=False)
    match_score = Column(Integer, nullable=False, default=0)
    is_new = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("UserModel", backref="user_jobs")
    job = relationship("JobListingModel", backref="user_associations")
    
    def __repr__(self):
        return f"<UserJobModel User:{self.user_id} Job:{self.job_id}>"
