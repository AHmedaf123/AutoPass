"""
Preference Schemas
Pyd antic schemas for user preferences API
"""
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

from domain.enums import Industry, WorkType, WorkModel, JobType, ExperienceLevel, INDUSTRY_SUBFIELDS


class PreferencesUpdateRequest(BaseModel):
    """Request schema for updating user preferences - Enhanced"""
    
    job_titles: List[str] = Field(..., min_length=1, max_length=10, description="Job titles (Ordered by priority: 1st, 2nd, 3rd...)")
    locations: List[str] = Field(..., min_length=1, max_length=10, description="Locations (1-10)")
    location_radius: Optional[str] = Field(None, description="Search radius (e.g., '25 mi', '50 km')")
    work_types: List[WorkType] = Field(..., min_length=1, description="Work types (legacy)")
    work_models: Optional[List[WorkModel]] = Field(None, description="Detailed work models")
    industries: List[Industry] = Field(..., min_length=1, description="Industries")
    subfields: Optional[List[str]] = Field(None, description="BLS occupational titles (subfields)")
    job_types: Optional[List[JobType]] = Field(None, description="Job types (Internship, Full Time, etc.)")
    experience_levels: Optional[List[ExperienceLevel]] = Field(None, description="Experience levels (Categorical)")
    years_of_experience: Optional[int] = Field(None, ge=0, description="Years of experience (Numeric)")
    target_salary: Optional[int] = Field(None, ge=0, description="Target salary")
    salary_currency: Optional[str] = Field("USD", description="Salary currency")
    current_salary: Optional[int] = Field(None, ge=0, description="Current salary (for form filling)")
    desired_salary: Optional[int] = Field(None, ge=0, description="Desired salary (for form filling)")
    
    @field_validator('subfields')
    @classmethod
    def validate_subfields(cls, v, info):
        """Validate subfields against selected industries"""
        if not v:
            return v
        
        # Get industries from context
        industries = info.data.get('industries', [])
        if not industries:
            return v
        
        # Validate each subfield
        valid_subfields = set()
        for industry in industries:
            valid_subfields.update(INDUSTRY_SUBFIELDS.get(industry, []))
        
        for subfield in v:
            if subfield not in valid_subfields:
                raise ValueError(
                    f"Subfield '{subfield}' not valid for selected industries. "
                    f"Valid subfields: {sorted(valid_subfields)}"
                )
        
        return v
    
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_titles": ["Software Engineer", "Backend Developer"],
                "locations": ["San Francisco", "Remote"],
                "location_radius": "25 mi",
                "work_types": ["Remote", "Hybrid"],
                "work_models": ["Hybrid", "Open to Remote"],
                "industries": ["Technology & IT"],
                "subfields": [
                    "Software Developers, Quality Assurance Analysts, and Testers",
                    "Database Administrators and Architects"
                ],
                "job_types": ["Full Time", "Contract"],
                "experience_levels": ["Mid Level", "Senior Level"],
                "min_salary": 100000,
                "max_salary": 150000
            }
        }


class PreferencesResponse(BaseModel):
    """Response schema for preferences"""
    
    job_titles: List[str]
    locations: List[str]
    location_radius: Optional[str] = None
    work_types: List[str]
    work_models: Optional[List[str]] = None
    industries: List[str]
    subfields: Optional[List[str]]
    job_types: Optional[List[str]] = None
    experience_levels: Optional[List[str]] = None
    years_of_experience: Optional[int] = None
    target_salary: Optional[int]
    salary_currency: Optional[str] = "USD"
    current_salary: Optional[int] = None
    desired_salary: Optional[int] = None
    source: str = Field(..., description="Source: preferences_screen, onboarding, or resume_keywords")
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_titles": ["Software Engineer"],
                "locations": ["Remote"],
                "work_types": ["Remote"],
                "industries": ["Technology & IT"],
                "subfields": ["Software Developers, Quality Assurance Analysts, and Testers"],
                "min_salary": 120000,
                "max_salary": 180000,
                "current_salary": 100000,
                "desired_salary": 150000,
                "source": "preferences_screen"
            }
        }


class LinkedInCredentialsRequest(BaseModel):
    """Request schema for LinkedIn credentials"""
    
    email: str = Field(..., description="LinkedIn email")
    password: str = Field(..., min_length=6, description="LinkedIn password")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "secure_password_123"
            }
        }


class LinkedInCredentialsResponse(BaseModel):
    """Response schema for LinkedIn credentials update"""
    
    message: str
    credentials_set: bool
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "LinkedIn credentials updated successfully",
                "credentials_set": True
            }
        }
