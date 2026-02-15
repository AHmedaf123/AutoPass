"""
Dependency Injection
FastAPI dependencies for services, repositories, and utilities
"""
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.database import get_db
from domain.entities import User
from application.repositories.interfaces import (
    IUserRepository,
    IJobRepository
)
from infrastructure.persistence.repositories.user import SQLAlchemyUserRepository
from infrastructure.persistence.repositories.job import SQLAlchemyJobRepository

# Services
from application.services.preference import IPreferenceService
from application.services.resume import IResumeService
from application.services.ai_match import IAIMatchService
from application.services.auto_apply import IAutoApplyService
from application.services.application_tracking import IApplicationTrackingService

from infrastructure.services.preference_service import PreferenceService
from infrastructure.services.resume_service import ResumeService
from infrastructure.services.ai_match_service import AIMatchService
from infrastructure.services.auto_apply_service import AutoApplyService
from infrastructure.services.application_tracking_service import ApplicationTrackingService
from infrastructure.external.file_storage_service import LocalFileStorageService

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


# ============================================================================
# Authentication Dependencies
# ============================================================================

async def get_current_user(
    x_user_id: str = Header(..., alias="X-User-ID"),
    session: AsyncSession = Depends(get_db),
    user_repo: IUserRepository = Depends(lambda: get_user_repository)
) -> User:
    """
    Get current authenticated user from X-User-ID header
    
    Raises:
        HTTPException: If user ID is invalid or user not found
    """
    try:
        from uuid import UUID
        
        # Validate UUID format
        try:
            user_uuid = UUID(x_user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid User ID format"
            )
        
        # Get user from database
        user = await user_repo(session).get_by_id(user_uuid)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        return user
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate user"
        )


# ============================================================================
# Repository Dependencies
# ============================================================================

def get_user_repository(
    session: AsyncSession = Depends(get_db)
) -> IUserRepository:
    """Get user repository instance"""
    return SQLAlchemyUserRepository(session)


def get_job_repository(
    session: AsyncSession = Depends(get_db)
) -> IJobRepository:
    """Get job repository instance"""
    return SQLAlchemyJobRepository(session)


def get_preference_service(
    user_repo: IUserRepository = Depends(get_user_repository),
    session: AsyncSession = Depends(get_db)
) -> IPreferenceService:
    """Get preference service instance"""
    # Create resume service for keyword extraction
    file_storage = LocalFileStorageService()
    resume_service = ResumeService(user_repo, file_storage)
    
    return PreferenceService(user_repo, resume_service)


def get_resume_service(
    user_repo: IUserRepository = Depends(get_user_repository),
) -> IResumeService:
    """Get resume service instance"""
    file_storage = LocalFileStorageService()
    return ResumeService(user_repo, file_storage)


def get_ai_match_service() -> IAIMatchService:
    """Get AI match service instance (singleton)"""
    # Singleton pattern for model loading
    if not hasattr(get_ai_match_service, "_instance"):
        get_ai_match_service._instance = AIMatchService()
    return get_ai_match_service._instance


def get_application_tracking_service(
    job_repo: IJobRepository = Depends(get_job_repository)
) -> IApplicationTrackingService:
    """Get application tracking service instance"""
    return ApplicationTrackingService(job_repo)


def get_auto_apply_service(
    job_repo: IJobRepository = Depends(get_job_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
    session: AsyncSession = Depends(get_db)
) -> IAutoApplyService:
    """Get auto-apply service instance with full dependencies"""
    from infrastructure.persistence.repositories.job_listing import JobListingRepository
    from infrastructure.persistence.repositories.user_job import UserJobRepository
    
    job_listing_repo = JobListingRepository(session)
    user_job_repo = UserJobRepository(session)
    
    return AutoApplyService(
        job_repository=job_repo,
        user_repository=user_repo,
        job_listing_repository=job_listing_repo,
        user_job_repository=user_job_repo
    )
