"""
JWT Service Implementation
Using RS256 algorithm with public/private keys
"""
from datetime import datetime, timedelta
from typing import Tuple, Dict
from uuid import UUID

from jose import jwt, JWTError
from loguru import logger

from core.config import settings
from core.exceptions import AuthenticationException
from application.services.auth.interfaces import IJwtService


class JwtService(IJwtService):
    """JWT service using RS256 algorithm"""
    
    def __init__(self):
        # For development, we'll use HS256 if RSA keys not provided
        # In production, RSA keys MUST be provided
        self.algorithm = "HS256" if not settings.JWT_PRIVATE_KEY else "RS256"
        
        if self.algorithm == "RS256":
            self.private_key = settings.JWT_PRIVATE_KEY
            self.public_key = settings.JWT_PUBLIC_KEY
        else:
            # Fallback to symmetric key for development
            self.secret_key = "dev-secret-key-change-in-production-12345678"
            logger.warning("Using HS256 for JWT (development only). Use RS256 in production!")
    
    def create_access_token(self, user_id: UUID) -> str:
        """Create access token"""
        expires_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        expire = datetime.utcnow() + expires_delta
        
        payload = {
            "sub": str(user_id),
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        }
        
        if self.algorithm == "RS256":
            return jwt.encode(payload, self.private_key, algorithm=self.algorithm)
        else:
            return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(self, user_id: UUID) -> str:
        """Create refresh token"""
        expires_delta = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        expire = datetime.utcnow() + expires_delta
        
        payload = {
            "sub": str(user_id),
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh"
        }
        
        if self.algorithm == "RS256":
            return jwt.encode(payload, self.private_key, algorithm=self.algorithm)
        else:
            return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Dict:
        """Verify and decode token"""
        try:
            if self.algorithm == "RS256":
                payload = jwt.decode(token, self.public_key, algorithms=[self.algorithm])
            else:
                payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            return payload
            
        except JWTError as e:
            logger.warning(f"JWT verification failed: {str(e)}")
            raise AuthenticationException("Invalid or expired token")
    
    def create_token_pair(self, user_id: UUID) -> Tuple[str, str]:
        """Create both access and refresh tokens"""
        access_token = self.create_access_token(user_id)
        refresh_token = self.create_refresh_token(user_id)
        return access_token, refresh_token
