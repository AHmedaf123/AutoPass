"""
Job Preferences ORM Model
User-defined job search preferences.
"""
import uuid
from sqlalchemy import Column, Integer, DateTime, JSON, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from core.database import Base

class JobPreferencesModel(Base):
    __tablename__ = "job_preferences"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Key to User
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Preferences
    job_titles = Column(JSON, nullable=True)
    locations = Column(JSON, nullable=True)
    work_types = Column(JSON, nullable=True)
    industries = Column(JSON, nullable=True)
    
    # Salary
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    
    # Current and Desired Salary
    current_salary = Column(Integer, nullable=True, comment="User's current salary (used for form filling)")
    desired_salary = Column(Integer, nullable=True, comment="User's desired salary (used for form filling)")
    
    # Gender
    gender = Column(String(20), nullable=True, comment="Gender: Male, Female, Other")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationship
    user = relationship("UserModel", backref="job_preferences")
    
    def __repr__(self):
        return f"<JobPreferencesModel for user {self.user_id}>"
