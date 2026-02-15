"""
ApplyQueue ORM Model
SQLAlchemy model for async job scraping task queue
"""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from enum import Enum

from core.database import Base


class TaskType(str, Enum):
    """Types of tasks that can be queued"""
    JOB_SCRAPING = "job_scraping"
    JOB_APPLICATION = "job_application"
    PROFILE_UPDATE = "profile_update"


class TaskPriority(int, Enum):
    """Priority levels for tasks (higher number = higher priority)"""
    LOW = 1          # Profile updates, etc.
    NORMAL = 5       # Job discovery/scraping
    HIGH = 10        # Job applications (Easy Apply)


class TaskStatus(str, Enum):
    """Status of queued tasks"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class ApplicationStep(str, Enum):
    """Steps during job application process"""
    NAVIGATION = "navigation"
    BUTTON_CLICK = "button_click"
    FORM_FILLING = "form_filling"
    SUBMISSION = "submission"
    COMPLETED = "completed"


class ApplyQueueModel(Base):
    """Task queue table for async job operations"""
    
    __tablename__ = "apply_queue"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Foreign Key
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # Task Details
    job_url = Column(String(1000), nullable=True)  # Optional for some task types
    job_id = Column(UUID(as_uuid=True), nullable=True)  # Job ID for application tasks
    task_type = Column(SQLEnum(TaskType), nullable=False, index=True)
    status = Column(SQLEnum(TaskStatus), nullable=False, default=TaskStatus.PENDING, index=True)
    priority = Column(Integer, nullable=False, default=5, index=True)  # Higher = more urgent
    
    # Session Tracking
    session_id = Column(String(255), nullable=True, index=True)  # LinkedIn session ID for tracking
    
    # Retry Logic
    retries = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    
    # Progress Tracking
    current_step = Column(String(255), nullable=True)
    progress_data = Column(Text, nullable=True)  # JSON string for additional data
    
    # AI Form Responses
    ai_response = Column(Text, nullable=True)  # JSON string: {field_id: answer, ...}
    
    # Error Tracking
    error_message = Column(Text, nullable=True)  # Latest error message
    error_log = Column(Text, nullable=True)  # JSON array of all errors [{timestamp, retry, message}]
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    next_attempt_time = Column(DateTime(timezone=True), nullable=True, index=True)  # For exponential backoff
    
    def __repr__(self):
        return f"<ApplyQueueModel {self.id} - {self.task_type.value} - {self.status.value}>"
