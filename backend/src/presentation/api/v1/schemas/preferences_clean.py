"""
Clean Preferences Schemas
Simplified preferences management matching user requirements
"""
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from uuid import UUID


class PreferencesCreateRequest(BaseModel):
    """Create/Update user preferences"""
    
    # Job titles (comma-separated, max 3)
    job_titles: str = Field(..., description="Comma-separated job titles (max 3)", examples=["Software Engineer, Backend Developer, Python Developer"])
    
    # Location
    location_city: str = Field(..., description="City", examples=["New York"])
    location_country: str = Field(..., description="Country", examples=["USA"])
    
    # Work type (only one)
    work_type: str = Field(..., description="Work type: Remote, Hybrid, or Onsite")
    
    # Experience level (only one)
    experience_level: str = Field(..., description="Experience level: Internship, Entry Level, Associate, Mid-Senior, Director, Executive")
    
    # Salary preferences (for form filling)
    current_salary: Optional[int] = Field(None, ge=0, description="Current salary in USD")
    desired_salary: Optional[int] = Field(None, ge=0, description="Desired salary in USD")
    
    # Gender
    gender: Optional[str] = Field(None, description="Gender: Male, Female, Other")
    
    @field_validator('gender')
    @classmethod
    def validate_gender(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = ['Male', 'Female', 'Other']
        if v not in allowed:
            raise ValueError(f'gender must be one of: {', '.join(allowed)}')
        return v
    
    @field_validator('job_titles')
    @classmethod
    def validate_job_titles(cls, v: str) -> str:
        titles = [t.strip() for t in v.split(',') if t.strip()]
        if len(titles) == 0:
            raise ValueError('At least one job title is required')
        # Silently truncate to first 3 titles
        return ','.join(titles[:3])
    
    @field_validator('work_type')
    @classmethod
    def validate_work_type(cls, v: str) -> str:
        allowed = ['Remote', 'Hybrid', 'Onsite']
        if v not in allowed:
            raise ValueError(f'work_type must be one of: {", ".join(allowed)}')
        return v
    
    @field_validator('experience_level')
    @classmethod
    def validate_experience_level(cls, v: str) -> str:
        allowed = ['Internship', 'Entry Level', 'Associate', 'Mid-Senior', 'Director', 'Executive']
        if v not in allowed:
            raise ValueError(f'experience_level must be one of: {", ".join(allowed)}')
        return v


class PreferencesResponse(BaseModel):
    """Preferences response"""
    
    user_id: str
    job_titles: List[str]
    location_city: str
    location_country: str
    work_type: str
    experience_level: str
    current_salary: Optional[int] = None
    desired_salary: Optional[int] = None
    gender: Optional[str] = None
    resume_uploaded: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PreferencesUpdateRequest(BaseModel):
    """Update preferences (all fields optional)"""
    
    job_titles: Optional[str] = Field(None, description="Comma-separated job titles (max 3)")
    location_city: Optional[str] = None
    location_country: Optional[str] = None
    work_type: Optional[str] = None
    experience_level: Optional[str] = None
    current_salary: Optional[int] = Field(None, ge=0, description="Current salary in USD")
    desired_salary: Optional[int] = Field(None, ge=0, description="Desired salary in USD")
    gender: Optional[str] = Field(None, description="Gender: Male, Female, Other")
    
    @field_validator('gender')
    @classmethod
    def validate_gender(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = ['Male', 'Female', 'Other']
        if v not in allowed:
            raise ValueError(f'gender must be one of: {', '.join(allowed)}')
        return v
    
    @field_validator('job_titles')
    @classmethod
    def validate_job_titles(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        titles = [t.strip() for t in v.split(',') if t.strip()]
        if len(titles) == 0:
            raise ValueError('At least one job title is required')
        # Silently truncate to first 3 titles
        return ','.join(titles[:3])
    
    @field_validator('work_type')
    @classmethod
    def validate_work_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = ['Remote', 'Hybrid', 'Onsite']
        if v not in allowed:
            raise ValueError(f'work_type must be one of: {", ".join(allowed)}')
        return v
    
    @field_validator('experience_level')
    @classmethod
    def validate_experience_level(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = ['Internship', 'Entry Level', 'Associate', 'Mid-Senior', 'Director', 'Executive']
        if v not in allowed:
            raise ValueError(f'experience_level must be one of: {", ".join(allowed)}')
        return v
