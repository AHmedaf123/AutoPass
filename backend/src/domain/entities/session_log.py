"""
Session Log Domain Entity
Business logic for session activity tracking
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID


@dataclass
class SessionLogActivity:
    """Single activity event in session log"""
    timestamp: datetime
    event_type: str  # login_started, login_success, task_started, task_completed, etc.
    description: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SessionLog:
    """Domain entity for session logging and activity tracking"""
    
    # Identifiers
    user_id: UUID
    session_id: str
    
    # Timestamps
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    
    # Status
    status: str = "CREATING"  # CREATING, ACTIVE, IN_USE, COMPLETED, EXPIRED, ERROR
    
    # Task Information
    task_name: Optional[str] = None
    task_started_at: Optional[datetime] = None
    task_completed_at: Optional[datetime] = None
    
    # Counters
    tasks_completed: int = 0
    retries: int = 0
    errors_count: int = 0
    
    # Error Information
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    
    # Activity Log
    activity_log: List[Dict[str, Any]] = None
    
    # Session Metadata
    browser_type: str = "chrome"
    headless: bool = True
    session_duration_seconds: Optional[int] = None
    
    # Performance Metrics
    login_time_seconds: Optional[int] = None
    task_duration_seconds: Optional[int] = None
    idle_time_seconds: Optional[int] = None
    
    # Termination Info
    termination_reason: Optional[str] = None  # auto_disposal, timeout, user_logout, error
    
    def __post_init__(self):
        """Initialize activity_log if not provided"""
        if self.activity_log is None:
            self.activity_log = []
    
    def add_activity(self, event_type: str, description: str, metadata: Optional[Dict[str, Any]] = None):
        """Record an activity event"""
        activity = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "description": description,
            "metadata": metadata or {}
        }
        self.activity_log.append(activity)
    
    def record_login_started(self):
        """Record login start"""
        self.add_activity("login_started", "LinkedIn login process started")
    
    def record_login_success(self, login_time_seconds: int):
        """Record successful login"""
        self.login_time_seconds = login_time_seconds
        self.started_at = datetime.utcnow()
        self.add_activity(
            "login_success",
            f"LinkedIn login succeeded in {login_time_seconds}s",
            {"login_time_seconds": login_time_seconds}
        )
    
    def record_login_failed(self, error: str):
        """Record login failure"""
        self.status = "ERROR"
        self.error_message = error
        self.error_type = "LoginError"
        self.errors_count += 1
        self.add_activity("login_failed", f"LinkedIn login failed: {error}")
    
    def record_task_started(self, task_name: str):
        """Record task start"""
        self.task_name = task_name
        self.task_started_at = datetime.utcnow()
        self.status = "IN_USE"
        self.add_activity("task_started", f"Task '{task_name}' started")
    
    def record_task_completed(self, task_name: str, duration_seconds: int, error: Optional[str] = None):
        """Record task completion"""
        self.task_completed_at = datetime.utcnow()
        self.task_duration_seconds = duration_seconds
        self.tasks_completed += 1
        
        if error:
            self.status = "ERROR"
            self.error_message = error
            self.error_type = "TaskError"
            self.errors_count += 1
            self.add_activity(
                "task_failed",
                f"Task '{task_name}' failed after {duration_seconds}s: {error}",
                {"task_name": task_name, "duration": duration_seconds}
            )
        else:
            self.status = "COMPLETED"
            self.add_activity(
                "task_completed",
                f"Task '{task_name}' completed successfully in {duration_seconds}s",
                {"task_name": task_name, "duration": duration_seconds}
            )
    
    def record_retry(self, reason: str, retry_count: int):
        """Record a retry attempt"""
        self.retries += 1
        self.add_activity(
            "retry",
            f"Retry #{retry_count}: {reason}",
            {"retry_number": retry_count, "reason": reason}
        )
    
    def record_session_expired(self, reason: str):
        """Record session expiration"""
        self.status = "EXPIRED"
        self.termination_reason = reason
        self.add_activity("session_expired", f"Session expired: {reason}")
    
    def record_session_disposed(self, reason: str, final_duration: int):
        """Record session disposal"""
        self.completed_at = datetime.utcnow()
        self.session_duration_seconds = final_duration
        self.termination_reason = reason
        self.add_activity(
            "session_disposed",
            f"Session disposed: {reason} (total duration: {final_duration}s)",
            {"duration": final_duration, "reason": reason}
        )
    
    def record_error(self, error_type: str, error_message: str, metadata: Optional[Dict[str, Any]] = None):
        """Record an error"""
        self.errors_count += 1
        self.error_type = error_type
        self.error_message = error_message
        self.add_activity(
            "error",
            f"{error_type}: {error_message}",
            metadata
        )
    
    def record_idle_time(self, idle_seconds: int):
        """Record idle period"""
        self.idle_time_seconds = idle_seconds
        self.add_activity(
            "idle_detected",
            f"Session idle for {idle_seconds}s",
            {"idle_seconds": idle_seconds}
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "user_id": str(self.user_id),
            "session_id": self.session_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "task_name": self.task_name,
            "task_started_at": self.task_started_at.isoformat() if self.task_started_at else None,
            "task_completed_at": self.task_completed_at.isoformat() if self.task_completed_at else None,
            "tasks_completed": self.tasks_completed,
            "retries": self.retries,
            "errors_count": self.errors_count,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "activity_log": self.activity_log,
            "browser_type": self.browser_type,
            "headless": self.headless,
            "session_duration_seconds": self.session_duration_seconds,
            "login_time_seconds": self.login_time_seconds,
            "task_duration_seconds": self.task_duration_seconds,
            "idle_time_seconds": self.idle_time_seconds,
            "termination_reason": self.termination_reason,
        }
