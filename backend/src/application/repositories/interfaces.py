"""
Repository Interfaces (Abstract Base Classes)
Define contracts for data access without implementation details
"""
from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from domain.entities import User, JobListing, Application, SessionLog


class IUserRepository(ABC):
    """User repository interface"""
    
    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID"""
        pass
    
    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        pass
    
    @abstractmethod
    async def create(self, user: User) -> User:
        """Create new user"""
        pass
    
    @abstractmethod
    async def update(self, user: User) -> User:
        """Update existing user"""
        pass
    
    @abstractmethod
    async def delete(self, user_id: UUID) -> bool:
        """Delete user"""
        pass
    
    @abstractmethod
    async def exists_by_email(self, email: str) -> bool:
        """Check if user exists by email"""
        pass
    
    @abstractmethod
    async def update_linkedin_credentials(
        self,
        user_id: UUID,
        encrypted_email: str,
        encrypted_password: str
    ) -> User:
        """Update user's LinkedIn credentials (encrypted) - Legacy method"""
        pass
    
    @abstractmethod
    async def update_linkedin_username_password(
        self,
        user_id: UUID,
        linkedin_username: str,
        linkedin_password: str
    ) -> User:
        """Update user's LinkedIn username and password (plain text)"""
        pass
    
    @abstractmethod
    async def update_indeed_username_password(
        self,
        user_id: UUID,
        indeed_username: str,
        indeed_password: str
    ) -> User:
        """Update user's Indeed username and password (plain text)"""
        pass
    
    @abstractmethod
    async def update_glassdoor_username_password(
        self,
        user_id: UUID,
        glassdoor_username: str,
        glassdoor_password: str
    ) -> User:
        """Update user's Glassdoor username and password (plain text)"""
        pass
    
    @abstractmethod
    async def update_encrypted_indeed_credentials(
        self,
        user_id: UUID,
        encrypted_username: str,
        encrypted_password: str
    ) -> User:
        """Update user's encrypted Indeed credentials"""
        pass
    
    @abstractmethod
    async def update_encrypted_glassdoor_credentials(
        self,
        user_id: UUID,
        encrypted_username: str,
        encrypted_password: str
    ) -> User:
        """Update user's encrypted Glassdoor credentials"""
        pass
    
    @abstractmethod
    async def get_by_google_id(self, google_user_id: str) -> Optional[User]:
        """Get user by Google user ID"""
        pass
    
    @abstractmethod
    async def update_google_credentials(
        self,
        user_id: UUID,
        google_user_id: str,
        google_access_token: str,
        google_refresh_token: Optional[str] = None
    ) -> User:
        """Update user's Google OAuth credentials"""
        pass

    @abstractmethod
    async def update_session_outcome(
        self,
        user_id: UUID,
        cooldown_until: Optional[datetime],
        last_session_outcome: Optional[str],
    ) -> User:
        """Persist session outcome and cooldown metadata."""
        pass


class IJobRepository(ABC):
    """Job repository interface"""
    
    @abstractmethod
    async def get_by_id(self, job_id: UUID) -> Optional[JobListing]:
        """Get job by ID"""
        pass
    
    @abstractmethod
    async def find_matching_jobs(
        self, 
        user_id: UUID, 
        limit: int = 50,
        offset: int = 0
    ) -> List[JobListing]:
        """Find jobs matching user preferences"""
        pass
    
    @abstractmethod
    async def create(self, job: JobListing) -> JobListing:
        """Create new job"""
        pass
    
    @abstractmethod
    async def update(self, job: JobListing) -> JobListing:
        """Update existing job"""
        pass
    
    @abstractmethod
    async def find_by_external_id(self, source: str, external_id: str) -> Optional[JobListing]:
        """Find job by external ID"""
        pass
    
    @abstractmethod
    async def batch_create(self, jobs: List[JobListing]) -> List[JobListing]:
        """Create multiple jobs in batch"""
        pass
    
    @abstractmethod
    async def find_by_criteria(
        self,
        user_id: UUID,
        criteria: dict,
        limit: int = 50,
        offset: int = 0
    ) -> List[JobListing]:
        """Find jobs matching criteria with pagination"""
        pass


class IApplicationRepository(ABC):
    """Application repository interface"""
    
    @abstractmethod
    async def get_by_id(self, application_id: UUID) -> Optional[Application]:
        """Get application by ID"""
        pass
    
    @abstractmethod
    async def get_user_applications(
        self, 
        user_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[Application]:
        """Get all applications for a user"""
        pass
    
    @abstractmethod
    async def create(self, application: Application) -> Application:
        """Create new application"""
        pass
    
    @abstractmethod
    async def update(self, application: Application) -> Application:
        """Update existing application"""
        pass
    
    @abstractmethod
    async def exists_for_job(self, user_id: UUID, job_id: UUID) -> bool:
        """Check if user already applied to job"""
        pass


class ISessionLogRepository(ABC):
    """Session log repository interface"""
    
    @abstractmethod
    async def create(self, session_log: SessionLog) -> SessionLog:
        """Create new session log"""
        pass
    
    @abstractmethod
    async def get_by_session_id(self, session_id: str) -> Optional[SessionLog]:
        """Get session log by session ID"""
        pass
    
    @abstractmethod
    async def get_user_sessions(
        self, 
        user_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[SessionLog]:
        """Get all session logs for a user"""
        pass
    
    @abstractmethod
    async def update(self, session_log: SessionLog) -> SessionLog:
        """Update session log"""
        pass
    
    @abstractmethod
    async def get_by_status(
        self,
        status: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[SessionLog]:
        """Get session logs by status"""
        pass
    
    @abstractmethod
    async def get_user_error_sessions(
        self,
        user_id: UUID,
        limit: int = 50
    ) -> List[SessionLog]:
        """Get session logs with errors for a user"""
        pass
    
    @abstractmethod
    async def get_user_statistics(self, user_id: UUID) -> dict:
        """Get aggregated statistics for user's sessions"""
        pass
