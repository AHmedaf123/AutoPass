"""
Resume Parsing Schemas
Detailed JSON structure for parsed resume data
"""
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field

# --- Sub-models ---

class ResumeMetadata(BaseModel):
    resume_id: str = ""
    user_id: str = ""
    source: str = "pdf"
    language: str = "en"
    parsed_at: str = ""
    parser_version: str = "v1.0"
    confidence_score: float = 0.0

class LocationDetails(BaseModel):
    city: str = ""
    state: str = ""
    country: str = ""
    postal_code: str = ""
    remote_preference: bool = False

class ContactDetails(BaseModel):
    email: str = ""
    phone: str = ""
    alternate_phone: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    website: str = ""

class PersonalInfo(BaseModel):
    full_name: str = ""
    first_name: str = ""
    last_name: str = ""
    headline: str = ""
    date_of_birth: str = ""
    gender: str = ""
    nationality: str = ""
    marital_status: str = ""
    location: LocationDetails = Field(default_factory=LocationDetails)
    contact: ContactDetails = Field(default_factory=ContactDetails)

class SummaryDetails(BaseModel):
    professional_summary: str = ""
    career_objective: str = ""
    years_of_experience: int = 0
    current_role: str = ""
    industries: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)

class Achievement(BaseModel):
    title: str = ""
    description: str = ""

class EmploymentHistory(BaseModel):
    company: str = ""
    company_type: str = ""
    role: str = ""
    employment_type: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    is_current: bool = False
    description: str = ""
    responsibilities: List[str] = Field(default_factory=list)
    achievements: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    domain: str = ""

class ExperienceDetails(BaseModel):
    total_experience_years: float = 0
    employment_history: List[EmploymentHistory] = Field(default_factory=list)

class EducationDetails(BaseModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    cgpa: str = ""
    grading_scale: str = ""
    start_date: str = ""
    end_date: str = ""
    is_completed: bool = True
    location: str = ""
    honors: List[str] = Field(default_factory=list)
    relevant_courses: List[str] = Field(default_factory=list)

class ProjectLinks(BaseModel):
    github: str = ""
    demo: str = ""
    documentation: str = ""

class ProjectDetails(BaseModel):
    project_name: str = ""
    project_type: str = ""
    description: str = ""
    role: str = ""
    start_date: str = ""
    end_date: str = ""
    technologies: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    domain: str = ""
    outcomes: List[str] = Field(default_factory=list)
    links: ProjectLinks = Field(default_factory=ProjectLinks)

class TechnicalSkills(BaseModel):
    programming_languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    libraries: List[str] = Field(default_factory=list)
    databases: List[str] = Field(default_factory=list)
    cloud_platforms: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    operating_systems: List[str] = Field(default_factory=list)

class LanguageSkill(BaseModel):
    language: str = ""
    proficiency: str = ""

class SkillsDetails(BaseModel):
    technical_skills: TechnicalSkills = Field(default_factory=TechnicalSkills)
    soft_skills: List[str] = Field(default_factory=list)
    domain_skills: List[str] = Field(default_factory=list)
    languages: List[LanguageSkill] = Field(default_factory=list)

class CertificationDetails(BaseModel):
    name: str = ""
    issuing_organization: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    credential_id: str = ""
    credential_url: str = ""

class PublicationDetails(BaseModel):
    title: str = ""
    journal: str = ""
    publication_date: str = ""
    authors: List[str] = Field(default_factory=list)
    doi: str = ""
    url: str = ""

class AwardDetails(BaseModel):
    title: str = ""
    issuer: str = ""
    date: str = ""
    description: str = ""

class VolunteeringDetails(BaseModel):
    organization: str = ""
    role: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""

class SalaryExpectations(BaseModel):
    currency: str = "USD"
    min: int = 0
    max: int = 0

class ResumePreferences(BaseModel):
    job_types: List[str] = Field(default_factory=list)
    preferred_locations: List[str] = Field(default_factory=list)
    salary_expectations: SalaryExpectations = Field(default_factory=SalaryExpectations)
    availability: str = ""

class ResumeScores(BaseModel):
    ats_score: float = 0.0
    skill_match_score: float = 0.0
    experience_relevance_score: float = 0.0

class RawData(BaseModel):
    original_text: str = ""
    unstructured_sections: List[str] = Field(default_factory=list)

# --- Main Schema ---

class ParsedResume(BaseModel):
    """Complete Parsed Resume Schema"""
    resume_metadata: ResumeMetadata = Field(default_factory=ResumeMetadata)
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    summary: SummaryDetails = Field(default_factory=SummaryDetails)
    experience: ExperienceDetails = Field(default_factory=ExperienceDetails)
    education: List[EducationDetails] = Field(default_factory=list)
    projects: List[ProjectDetails] = Field(default_factory=list)
    skills: SkillsDetails = Field(default_factory=SkillsDetails)
    certifications: List[CertificationDetails] = Field(default_factory=list)
    publications: List[PublicationDetails] = Field(default_factory=list)
    awards: List[AwardDetails] = Field(default_factory=list)
    volunteering: List[VolunteeringDetails] = Field(default_factory=list)
    preferences: ResumePreferences = Field(default_factory=ResumePreferences)
    resume_scores: ResumeScores = Field(default_factory=ResumeScores)
    raw_data: RawData = Field(default_factory=RawData)
