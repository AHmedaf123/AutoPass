"""
User ORM Model
SQLAlchemy model for persistence
"""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from core.database import Base


class UserModel(Base):
    """User table ORM model"""
    
    __tablename__ = "users"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Authentication
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    
    # Personal Information
    full_name = Column(String(255), nullable=False)
    
    # Career Information
    current_job_title = Column(String(255), nullable=True)
    target_job_title = Column(String(255), nullable=False, default="")
    industry = Column(String(100), nullable=False, default="")
    salary_expectation = Column(Integer, nullable=True)  # Annual USD
    
    # Resume
    resume_url = Column(String(500), nullable=True)
    resume_base64 = Column(Text, nullable=True) # Large base64 string
    resume_parsed_data = Column(JSON, nullable=True)
    
    # Push Notifications
    fcm_token = Column(String(500), nullable=True)
    
    # LinkedIn credentials (plain text - stored securely)
    linkedin_username = Column(String(255), nullable=True)
    linkedin_password = Column(String(255), nullable=True)
    
    # Indeed credentials (plain text - stored securely)
    indeed_username = Column(String(255), nullable=True)
    indeed_password = Column(String(255), nullable=True)
    
    # Glassdoor credentials (plain text - stored securely)
    glassdoor_username = Column(String(255), nullable=True)
    glassdoor_password = Column(String(255), nullable=True)
    
    # Encrypted Indeed credentials
    encrypted_indeed_username = Column(Text, nullable=True)
    encrypted_indeed_password = Column(Text, nullable=True)
    
    # Encrypted Glassdoor credentials
    encrypted_glassdoor_username = Column(Text, nullable=True)
    encrypted_glassdoor_password = Column(Text, nullable=True)
    
    # Google OAuth credentials
    google_user_id = Column(String(255), nullable=True, index=True)
    google_access_token = Column(Text, nullable=True)
    google_refresh_token = Column(Text, nullable=True)
    
    # LinkedIn credentials (encrypted) - Legacy, keeping for backwards compatibility
    encrypted_linkedin_email = Column(Text, nullable=True)
    encrypted_linkedin_password = Column(Text, nullable=True)
    
    # Persistent browser profile (normalized cookies + environment fingerprint as JSON)
    persistent_browser_profile = Column(Text, nullable=True)

    # Session cooldown + outcome tracking
    cooldown_until = Column(DateTime(timezone=True), nullable=True)
    last_session_outcome = Column(String(50), nullable=True)
    
    # Direct Preferences (Merged from old table)
    job_title_priority_1 = Column(String(255), nullable=True)
    job_title_priority_2 = Column(String(255), nullable=True)
    job_title_priority_3 = Column(String(255), nullable=True)
    
    # Experience (Years by level - integer counts)
    exp_years_internship = Column(Integer, nullable=True)
    exp_years_entry_level = Column(Integer, nullable=True)
    exp_years_associate = Column(Integer, nullable=True)
    exp_years_mid_senior_level = Column(Integer, nullable=True)
    exp_years_director = Column(Integer, nullable=True)
    exp_years_executive = Column(Integer, nullable=True)
    
    # Work Type Preferences (Booleans)
    pref_onsite = Column(Integer, default=0) # 0=False, 1=True
    pref_hybrid = Column(Integer, default=0)
    pref_remote = Column(Integer, default=0)
    
    # Salary Preferences (for form filling)
    current_salary = Column(Integer, nullable=True, comment="Current salary in USD (for form filling)")
    desired_salary = Column(Integer, nullable=True, comment="Desired salary in USD (for form filling)")
    
    # Gender
    gender = Column(String(20), nullable=True, comment="Gender: Male, Female, Other")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<UserModel {self.email}>"
