"""
Job Status Enums
Status enumerations for jobs and applications
"""
from enum import Enum


class JobStatus(str, Enum):
    """Job posting status"""
    ACTIVE = "active"
    EXPIRED = "expired"
    FILLED = "filled"
    REMOVED = "removed"


class ApplicationStatus(str, Enum):
    """Job application status"""
    PENDING = "pending"
    APPLIED = "applied"
    EXPIRED = "expired"
    REVIEWING = "reviewing"
    INTERVIEWING = "interviewing"
    OFFERED = "offered"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
