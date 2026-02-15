"""
Password Hasher Implementation
Using passlib with bcrypt
"""
from passlib.context import CryptContext

from application.services.auth.interfaces import IPasswordHasher


class BcryptPasswordHasher(IPasswordHasher):
    """Bcrypt password hasher"""
    
    def __init__(self):
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against bcrypt hash"""
        return self.pwd_context.verify(plain_password, hashed_password)
