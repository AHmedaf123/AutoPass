"""
User Domain Entity
Immutable user business object
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from ..value_objects import Email, SalaryRange


@dataclass(frozen=True)
class User:
    """User domain entity - immutable"""
    
    id: UUID
    email: Email
    password_hash: str
    full_name: str
    
    # Career information
    target_job_title: str
    industry: str
    current_job_title: Optional[str] = None
    salary_expectation: Optional[SalaryRange] = None
    
    # Resume
    resume_url: Optional[str] = None
    resume_base64: Optional[str] = None # Base64 encoded PDF
    resume_parsed_data: Optional[dict] = None
    
    # Push notifications
    fcm_token: Optional[str] = None
    
    # LinkedIn credentials (plain text)
    linkedin_username: Optional[str] = None
    linkedin_password: Optional[str] = None
    
    # Indeed credentials (plain text)
    indeed_username: Optional[str] = None
    indeed_password: Optional[str] = None
    
    # Glassdoor credentials (plain text)
    glassdoor_username: Optional[str] = None
    glassdoor_password: Optional[str] = None
    
    # Encrypted Indeed credentials
    encrypted_indeed_username: Optional[str] = None
    encrypted_indeed_password: Optional[str] = None
    
    # Encrypted Glassdoor credentials
    encrypted_glassdoor_username: Optional[str] = None
    encrypted_glassdoor_password: Optional[str] = None
    
    # Google OAuth credentials
    google_user_id: Optional[str] = None
    google_access_token: Optional[str] = None
    google_refresh_token: Optional[str] = None
    
    # LinkedIn credentials (encrypted) - Legacy, keeping for backwards compatibility
    encrypted_linkedin_email: Optional[str] = None
    encrypted_linkedin_password: Optional[str] = None
    
    # Persistent browser profile (normalized cookies + environment fingerprint as JSON)
    persistent_browser_profile: Optional[str] = None

    # Session lifecycle
    cooldown_until: Optional[datetime] = None
    last_session_outcome: Optional[str] = None
    
    # Direct Preferences
    job_title_priority_1: Optional[str] = None
    job_title_priority_2: Optional[str] = None
    job_title_priority_3: Optional[str] = None
    
    # Experience (Years by level)
    exp_years_internship: Optional[int] = None
    exp_years_entry_level: Optional[int] = None
    exp_years_associate: Optional[int] = None
    exp_years_mid_senior_level: Optional[int] = None
    exp_years_director: Optional[int] = None
    exp_years_executive: Optional[int] = None
    
    # Work Type Preferences
    pref_onsite: Optional[bool] = False
    pref_hybrid: Optional[bool] = False
    pref_remote: Optional[bool] = False
    
    # Salary Preferences (for form filling)
    current_salary: Optional[int] = None
    desired_salary: Optional[int] = None
    
    # Gender
    gender: Optional[str] = None
    
    # Timestamps
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        """Validate user data"""
        # Validation for required fields during registration
        if not self.full_name or len(self.full_name.strip()) == 0:
            raise ValueError("Full name cannot be empty")
    
    def has_completed_onboarding(self) -> bool:
        """Check if user completed onboarding"""
        return bool(
            self.target_job_title and 
            self.industry and 
            self.resume_url
        )
    
    def has_linkedin_credentials(self) -> bool:
        """Check if user has stored LinkedIn credentials"""
        # Check new format first, then fall back to legacy encrypted format
        return bool(
            (self.linkedin_username and self.linkedin_password) or
            (self.encrypted_linkedin_email and self.encrypted_linkedin_password)
        )
    
    def __str__(self) -> str:
        return f"User({self.email}, {self.full_name})"
