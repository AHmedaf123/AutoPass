"""
Domain Enums - Extended
Business enumerations with enhanced preferences support
"""
from enum import Enum
from typing import Dict, List

# ... (existing Industry enum and INDUSTRY_SUBFIELDS - keep as is)

class WorkType(str, Enum):
    """Work type preferences for jobs"""
    REMOTE = "Remote"
    HYBRID = "Hybrid"
    ONSITE = "Onsite"


class WorkModel(str, Enum):
    """Detailed work models for user preferences"""
    ONSITE = "Onsite"
    HYBRID = "Hybrid"
    OPEN_TO_REMOTE = "Open to Remote"
    FULLY_REMOTE = "Fully Remote"


class JobType(str, Enum):
    """Job type classifications"""
    INTERNSHIP = "Internship"
    CONTRACT = "Contract"
    FULL_TIME = "Full Time"
    PART_TIME = "Part Time"
    TEMPORARY = "Temporary"


class ExperienceLevel(str, Enum):
    """Experience level classifications"""
    ENTRY_LEVEL = "Entry Level"
    INTERN_GRAD = "Intern/Grad."
    MID_LEVEL = "Mid Level"
    SENIOR_LEVEL = "Senior Level"
    LEAD_STAFF = "Lead/Staff"
    EXECUTIVE = "Executive"


class ApplicationStatus(str, Enum):
    """Status of job application"""
    PENDING = "Pending"
    APPLIED = "Applied"
    EXPIRED = "Expired"
    INTERVIEWING = "Interviewing"
    REJECTED = "Rejected"
    ACCEPTED = "Accepted"
