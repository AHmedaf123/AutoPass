"""Value Objects - Immutable objects defined by their attributes"""

from .email import Email
from .salary_range import SalaryRange
from .job_status import JobStatus, ApplicationStatus
from .match_score import MatchScore
__all__ = [
    "Email",
    "SalaryRange",
    "JobStatus",
    "ApplicationStatus",
    "MatchScore",
]
