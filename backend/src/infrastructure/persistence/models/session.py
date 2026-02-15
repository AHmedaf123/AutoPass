"""
Session ORM Model
SQLAlchemy model for tracking concurrent Selenium sessions per user
"""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from enum import Enum

from core.database import Base


class SessionStatus(str, Enum):
    """Status of Selenium sessions"""
    ACTIVE = "active"
    IDLE = "idle"
    IN_USE = "in_use"
    COMPLETED = "completed"
    FAILED = "failed"
    TAINTED = "tainted"  # Session detected as unhealthy (429, expired, checkpoint)
    DISPOSED = "disposed"


class SessionModel(Base):
    """Sessions table ORM model for tracking concurrent Selenium sessions per user"""
    
    __tablename__ = "sessions"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Session Identification
    session_id = Column(String(255), nullable=False, unique=True, index=True)  # Unique session identifier
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)  # User who owns this session
    
    # Session Status
    status = Column(SQLEnum(SessionStatus), nullable=False, default=SessionStatus.ACTIVE, index=True)
    
    # Session Lifecycle Timestamps
    session_start = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    session_end = Column(DateTime(timezone=True), nullable=True, index=True)
    last_activity = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Task Tracking
    task_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Current task if in_use
    tasks_completed = Column(Integer, default=0)  # Counter for tasks completed in this session
    
    # Browser/Driver Info
    browser_type = Column(String(50), default="chrome")
    headless = Column(Integer, default=1)  # 0=False, 1=True
    
    # Performance Metrics
    session_duration_seconds = Column(Integer, nullable=True)  # Calculated on session_end
    login_time_seconds = Column(Integer, nullable=True)
    
    # Error Tracking
    error_count = Column(Integer, default=0)
    last_error_message = Column(Text, nullable=True)
    last_error_type = Column(String(100), nullable=True)
    
    # Health Check Tracking
    health_check_count = Column(Integer, default=0)  # Number of health checks performed
    health_issues_detected = Column(Integer, default=0)  # Count of 429/expired/checkpoint issues
    last_health_check = Column(DateTime(timezone=True), nullable=True)  # When last health check occurred
    last_health_issue = Column(String(100), nullable=True)  # Type: 429_error, expired_session, linkedin_checkpoint
    health_check_log = Column(Text, nullable=True)  # JSON array of health check events
    
    # Additional Session Metadata (avoid reserved SQLAlchemy name 'metadata')
    session_metadata = Column(Text, nullable=True)  # JSON string for additional session data
    termination_reason = Column(String(255), nullable=True)  # Why session ended (auto_disposal, timeout, user_logout, etc.)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<SessionModel {self.session_id} - user={self.user_id} - {self.status.value}>"
