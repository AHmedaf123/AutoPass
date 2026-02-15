"""
Session Log ORM Model
SQLAlchemy model for session activity tracking and logging
"""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from core.database import Base


class SessionLogModel(Base):
    """Session log table ORM model for tracking session activities"""
    
    __tablename__ = "session_logs"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Foreign Keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    
    # Session Lifecycle
    status = Column(String(50), nullable=False)  # CREATING, ACTIVE, IN_USE, COMPLETED, EXPIRED, ERROR
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)  # When session became active
    completed_at = Column(DateTime(timezone=True), nullable=True)  # When session was disposed
    last_used = Column(DateTime(timezone=True), nullable=True)
    
    # Task Information
    task_name = Column(String(255), nullable=True)
    task_started_at = Column(DateTime(timezone=True), nullable=True)
    task_completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Counters
    tasks_completed = Column(Integer, default=0)
    retries = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    
    # Error Tracking
    error_message = Column(Text, nullable=True)
    error_type = Column(String(100), nullable=True)  # e.g., LoginError, TimeoutError, etc.
    
    # Activity Log (JSON array of events)
    activity_log = Column(JSON, default=list)  # List of activity events
    
    # Session Metadata
    browser_type = Column(String(50), default="chrome")
    headless = Column(Integer, default=1)  # 0=False, 1=True
    session_duration_seconds = Column(Integer, nullable=True)
    
    # Performance Metrics
    login_time_seconds = Column(Integer, nullable=True)
    task_duration_seconds = Column(Integer, nullable=True)
    idle_time_seconds = Column(Integer, nullable=True)
    
    # Cleanup info
    termination_reason = Column(String(255), nullable=True)  # auto_disposal, timeout, user_logout, etc.
    
    def __repr__(self):
        return f"<SessionLogModel {self.session_id} - {self.status}>"
