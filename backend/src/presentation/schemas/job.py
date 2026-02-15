"""
Job Schemas
Pydantic schemas for job discovery and application API
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

from domain.enums import ApplicationStatus


class JobResponse(BaseModel):
    """Response schema for a single job"""
    
    id: UUID
    title: str
    company: str
    location: str
    description: str
    employment_type: str
    experience_level: str
    industry: str
    subfields: Optional[List[str]] = Field(None, description="BLS occupational titles")
    min_salary: Optional[int]
    max_salary: Optional[int]
    skills_required: Optional[List[str]]
    linkedin_url: str
    work_type: Optional[str]
    apply_status: Optional[str]
    match_score: Optional[float] = Field(None, description="AI match score (0-100)")
    created_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "title": "Senior Software Engineer",
                "company": "Tech Corp",
                "location": "San Francisco, CA",
                "description": "We are seeking an experienced software engineer...",
                "employment_type": "full-time",
                "experience_level": "senior",
                "industry": "Technology & IT",
                "subfields": ["Software Developers, Quality Assurance Analysts, and Testers"],
                "min_salary": 150000,
                "max_salary": 200000,
                "skills_required": ["Python", "FastAPI", "PostgreSQL"],
                "linkedin_url": "https://linkedin.com/jobs/view/123456",
                "work_type": "Remote",
                "apply_status": "Pending",
                "match_score": 85.5,
                "created_at": "2025-12-24T10:00:00Z"
            }
        }


class JobListResponse(BaseModel):
    """Paginated response for job list"""
    
    jobs: List[JobResponse]
    total: int
    limit: int
    offset: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "jobs": [],
                "total": 100,
                "limit": 50,
                "offset": 0
            }
        }


class JobDiscoveryRequest(BaseModel):
    """Request schema for job discovery"""
    
    limit: int = Field(50, ge=1, le=100, description="Max jobs to discover")
    force_refresh: bool = Field(False, description="Force LinkedIn fetch, ignore cache")
    
    class Config:
        json_schema_extra = {
            "example": {
                "limit": 50,
                "force_refresh": False
            }
        }


class JobDiscoveryResponse(BaseModel):
    """Response schema for job discovery"""
    
    jobs_discovered: int
    jobs_qualified: int = Field(..., description="Jobs meeting min match score threshold")
    message: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "jobs_discovered": 75,
                "jobs_qualified": 42,
                "message": "Discovered 42 qualified jobs matching your preferences"
            }
        }


class AutoApplyRequest(BaseModel):
    """Request schema for auto-apply"""
    
    job_ids: List[UUID] = Field(..., min_length=1, max_length=20, description="Job IDs to apply to (max 20)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_ids": [
                    "123e4567-e89b-12d3-a456-426614174000",
                    "123e4567-e89b-12d3-a456-426614174001"
                ]
            }
        }


class AutoApplyResponse(BaseModel):
    """Response schema for auto-apply"""
    
    results: dict = Field(..., description="Job ID -> Application Status mapping")
    total_jobs: int
    successful: int
    failed: int
    message: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "results": {
                    "123e4567-e89b-12d3-a456-426614174000": "Applied",
                    "123e4567-e89b-12d3-a456-426614174001": "Pending"
                },
                "total_jobs": 2,
                "successful": 1,
                "failed": 1,
                "message": "Applied to 1 out of 2 jobs"
            }
        }


class ApplicationResponse(BaseModel):
    """Response schema for a single application"""
    
    id: UUID
    job: JobResponse
    applied_at: Optional[datetime]
    status: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "job": {},
                "applied_at": "2025-12-24T10:30:00Z",
                "status": "Applied"
            }
        }


class ApplicationListResponse(BaseModel):
    """Paginated response for application list"""
    
    applications: List[JobResponse]  # Simplified - just jobs with apply_status
    total: int
    limit: int
    offset: int
    stats: dict = Field(..., description="Application statistics by status")
    
    class Config:
        json_schema_extra = {
            "example": {
                "applications": [],
                "total": 50,
                "limit": 20,
                "offset": 0,
                "stats": {
                    "pending": 10,
                    "applied": 30,
                    "interviewing": 8,
                    "rejected": 2,
                    "accepted": 0
                }
            }
        }
