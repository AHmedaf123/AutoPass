"""
Authentication Request/Response Schemas
Pydantic v2 models with strict validation
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict


class ClientSideLoginRequest(BaseModel):
    """Client-side login request with cookies from browser"""
    
    email: EmailStr
    cookies: List[Dict[str, Any]] = Field(
        ..., 
        description="Cookies extracted from browser after LinkedIn login. Must include 'li_at' or 'JSESSIONID'."
    )
    user_agent: Optional[str] = Field(
        None, 
        description="Browser user agent string (optional, will use default if not provided)"
    )
    
    @field_validator('cookies')
    @classmethod
    def validate_cookies(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate cookies format"""
        if not v or len(v) == 0:
            raise ValueError('At least one cookie is required')
        
        # Validate each cookie has a name
        for cookie in v:
            if 'name' not in cookie:
                raise ValueError('Each cookie must have a "name" field')
            if 'value' not in cookie:
                raise ValueError('Each cookie must have a "value" field')
        
        return v


class LoginResponse(BaseModel):
    """Login response with user ID"""
    
    user_id: str
    message: str | None = None


class SessionResponse(BaseModel):
    """LinkedIn session response"""
    
    session_id: str
    message: str
    expires_in_minutes: int = 30


class CooldownResponse(BaseModel):
    """User cooldown status response"""
    
    is_on_cooldown: bool
    cooldown_until: str | None = None
    remaining_seconds: int
    remaining_minutes: int


class SessionStatusResponse(BaseModel):
    """LinkedIn session status response"""
    
    session_id: str
    user_id: str
    status: str
    created_at: str
    last_used: str
    uptime_seconds: float
    idle_seconds: float
    task_name: str | None = None
    task_started_at: str | None = None
    task_completed_at: str | None = None
    error_message: str | None = None


class SessionStatisticsResponse(BaseModel):
    """Session statistics response"""
    
    total_sessions: int
    active_sessions: int
    completed_sessions: int
    expired_sessions: int
    error_sessions: int
    idle_sessions: list[str]
    total_users: int
    timestamp: str


class UserResponse(BaseModel):
    """User information response"""
    
    id: str
    email: str
    full_name: str
    target_job_title: str
    industry: str
    current_job_title: str | None = None
    salary_expectation: int | None = None
    has_completed_onboarding: bool


class SessionLogActivityResponse(BaseModel):
    """Single activity event in session log"""
    
    timestamp: str
    event_type: str
    description: str
    metadata: Dict[str, Any] | None = None


class SessionLogResponse(BaseModel):
    """Complete session log response"""
    
    session_id: str
    user_id: str
    status: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    task_name: str | None = None
    task_started_at: str | None = None
    task_completed_at: str | None = None
    tasks_completed: int
    retries: int
    errors_count: int
    error_message: str | None = None
    error_type: str | None = None
    activity_log: List[Dict[str, Any]]
    browser_type: str
    headless: bool
    session_duration_seconds: int | None = None
    login_time_seconds: int | None = None
    task_duration_seconds: int | None = None
    idle_time_seconds: int | None = None
    termination_reason: str | None = None


class SessionLogsListResponse(BaseModel):
    """List of session logs"""
    
    sessions: List[SessionLogResponse]
    total: int
    has_more: bool


class UserSessionStatisticsResponse(BaseModel):
    """User session statistics aggregated"""
    
    total_sessions: int
    total_tasks: int
    total_retries: int
    total_errors: int
    avg_session_duration: float
    avg_login_time: float
    avg_task_duration: float
