"""
Dependency Injection Container
Manages service and repository instances
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from core.database import get_db
from application.repositories.interfaces import IUserRepository
from application.services.auth.interfaces import IAuthService, IJwtService, IPasswordHasher
from application.services.security.interfaces import IEncryptionService
from infrastructure.persistence.repositories.user import SQLAlchemyUserRepository
from infrastructure.security.password_hasher import BcryptPasswordHasher
from infrastructure.security.jwt_service import JwtService
from infrastructure.security.encryption import FernetEncryptionService


# Singleton instances
_password_hasher: IPasswordHasher | None = None
_jwt_service: IJwtService | None = None
_encryption_service: IEncryptionService | None = None


def get_password_hasher() -> IPasswordHasher:
    """Get password hasher instance (singleton)"""
    global _password_hasher
    if _password_hasher is None:
        _password_hasher = BcryptPasswordHasher()
    return _password_hasher


def get_jwt_service() -> IJwtService:
    """Get JWT service instance (singleton)"""
    global _jwt_service
    if _jwt_service is None:
        _jwt_service = JwtService()
    return _jwt_service


def get_encryption_service() -> IEncryptionService:
    """Get encryption service instance (singleton)"""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = FernetEncryptionService()
    return _encryption_service


def get_user_repository(
    session: AsyncSession = Depends(get_db)
) -> IUserRepository:
    """Get user repository instance (per-request)"""
    return SQLAlchemyUserRepository(session)


def get_auth_service(
    user_repo: IUserRepository = Depends(get_user_repository),
    password_hasher: IPasswordHasher = Depends(get_password_hasher)
) -> IAuthService:
    """Get auth service instance (per-request)"""
    from application.services.auth.impl import AuthService
    return AuthService(user_repo, password_hasher)
