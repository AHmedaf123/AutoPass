"""
Authentication Service Interfaces
Abstract base classes for authentication services
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from uuid import UUID

from domain.entities import User
from domain.value_objects import Email


class IPasswordHasher(ABC):
    """Password hashing interface"""
    
    @abstractmethod
    def hash_password(self, password: str) -> str:
        """Hash a plain password"""
        pass
    
    @abstractmethod
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        pass


class IJwtService(ABC):
    """JWT token service interface"""
    
    @abstractmethod
    def create_access_token(self, user_id: UUID, email: str) -> str:
        """Create access token"""
        pass
    
    @abstractmethod
    def create_refresh_token(self, user_id: UUID) -> str:
        """Create refresh token"""
        pass
    
    @abstractmethod
    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode token"""
        pass


class IAuthService(ABC):
    """Authentication service interface"""
    
    @abstractmethod
    async def register(
        self, 
        email: str, 
        password: str, 
        full_name: str
    ) -> Tuple[User, str]:
        """
        Register a new user
        
        Returns:
            Tuple of (User, message)
        """
        pass
    
    @abstractmethod
    async def login(self, email: str, password: str) -> Tuple[User, str]:
        """
        Authenticate user
        
        Returns:
            Tuple of (User, message)
        """
        pass
    
    @abstractmethod
    async def login_with_linkedin(
        self, 
        email: str, 
        password: str
    ) -> Tuple[User, str]:
        """
        Authenticate using LinkedIn credentials.
        Verifies credentials, creates/updates user, and returns user + status message.
        
        Returns:
            Tuple of (User, message)
        """
        pass
    
    @abstractmethod
    async def login_with_google(
        self,
        google_user_id: str,
        email: str,
        full_name: str,
        access_token: str,
        refresh_token: Optional[str] = None
    ) -> Tuple[User, str]:
        """
        Authenticate using Google OAuth.
        Creates/updates user with Google credentials and returns user + status message.
        
        Returns:
            Tuple of (User, message)
        """
        pass
