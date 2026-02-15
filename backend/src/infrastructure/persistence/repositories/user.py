"""
User Repository Implementation
SQLAlchemy-based user repository
"""
from typing import Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from cryptography.fernet import Fernet

from domain.entities import User
from domain.value_objects import Email, SalaryRange
from application.repositories.interfaces import IUserRepository
from infrastructure.persistence.models.user import UserModel
from core.exceptions import RepositoryException
from core.config import settings


class SQLAlchemyUserRepository(IUserRepository):
    """SQLAlchemy implementation of user repository"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()
            
            if model:
                return self._to_entity(model)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user by ID {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to get user: {str(e)}")
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.email == email)
            )
            model = result.scalar_one_or_none()
            
            if model:
                return self._to_entity(model)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user by email {email}: {str(e)}")
            raise RepositoryException(f"Failed to get user: {str(e)}")
    
    async def create(self, user: User) -> User:
        """Create new user"""
        try:
            model = self._to_model(user)
            self.session.add(model)
            await self.session.flush()
            await self.session.refresh(model)
            
            return self._to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to create user {user.email}: {str(e)}")
            raise RepositoryException(f"Failed to create user: {str(e)}")
    
    async def update(self, user: User) -> User:
        """Update existing user"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user.id)
            )
            model = result.scalar_one_or_none()
            
            if not model:
                raise RepositoryException(f"User not found: {user.id}")
            
            # Update fields
            model.email = str(user.email)
            model.full_name = user.full_name
            model.current_job_title = user.current_job_title
            model.target_job_title = user.target_job_title
            model.industry = user.industry
            model.salary_expectation = user.salary_expectation.min_salary if user.salary_expectation else None
            model.resume_url = user.resume_url
            model.resume_base64 = user.resume_base64
            model.resume_parsed_data = user.resume_parsed_data
            model.fcm_token = user.fcm_token
            model.job_title_priority_1 = user.job_title_priority_1
            model.job_title_priority_2 = user.job_title_priority_2
            model.job_title_priority_3 = user.job_title_priority_3
            
            model.exp_years_internship = user.exp_years_internship
            model.exp_years_entry_level = user.exp_years_entry_level
            model.exp_years_associate = user.exp_years_associate
            model.exp_years_mid_senior_level = user.exp_years_mid_senior_level
            model.exp_years_director = user.exp_years_director
            model.exp_years_executive = user.exp_years_executive
            
            model.pref_onsite = 1 if user.pref_onsite else 0
            model.pref_hybrid = 1 if user.pref_hybrid else 0
            model.pref_remote = 1 if user.pref_remote else 0
            
            model.current_salary = user.current_salary
            model.desired_salary = user.desired_salary
            model.gender = user.gender
            
            await self.session.flush()
            await self.session.refresh(model)
            
            return self._to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to update user {user.id}: {str(e)}")
            raise RepositoryException(f"Failed to update user: {str(e)}")
    
    async def delete(self, user_id: UUID) -> bool:
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()
            
            if model:
                await self.session.delete(model)
                await self.session.flush()
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to delete user: {str(e)}")
    
    async def exists_by_email(self, email: str) -> bool:
        try:
            result = await self.session.execute(
                select(UserModel.id).where(UserModel.email == email)
            )
            return result.scalar_one_or_none() is not None
            
        except Exception as e:
            logger.error(f"Failed to check user existence {email}: {str(e)}")
            raise RepositoryException(f"Failed to check user existence: {str(e)}")
    
    async def update_linkedin_credentials(
        self,
        user_id: UUID,
        linkedin_email: str,
        linkedin_password: str
    ) -> User:
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()
            
            if not model:
                raise RepositoryException(f"User not found: {user_id}")
            email_bytes = linkedin_email.encode('utf-8')
            password_bytes = linkedin_password.encode('utf-8')
            model.encrypted_linkedin_email = email_bytes
            model.encrypted_linkedin_password = password_bytes
            
            await self.session.flush()
            await self.session.refresh(model)
            
            logger.info(f"Updated LinkedIn credentials for user {user_id}")
            return self._to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to update LinkedIn credentials for user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to update LinkedIn credentials: {str(e)}")
    
    async def update_linkedin_username_password(
        self,
        user_id: UUID,
        linkedin_username: str,
        linkedin_password: str
    ) -> User:
        """Update user's LinkedIn username and password (plain text)"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()
            
            if not model:
                raise RepositoryException(f"User not found: {user_id}")
            
            model.linkedin_username = linkedin_username
            model.linkedin_password = linkedin_password
            
            await self.session.flush()
            await self.session.refresh(model)
            
            logger.info(f"Updated LinkedIn username/password for user {user_id}")
            return self._to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to update LinkedIn username/password for user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to update LinkedIn username/password: {str(e)}")
    
    async def update_indeed_username_password(
        self,
        user_id: UUID,
        indeed_username: str,
        indeed_password: str
    ) -> User:
        """Update user's Indeed username and password (plain text)"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()
            
            if not model:
                raise RepositoryException(f"User not found: {user_id}")
            
            model.indeed_username = indeed_username
            model.indeed_password = indeed_password
            
            await self.session.flush()
            await self.session.refresh(model)
            
            logger.info(f"Updated Indeed username/password for user {user_id}")
            return self._to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to update Indeed username/password for user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to update Indeed username/password: {str(e)}")
    
    async def update_glassdoor_username_password(
        self,
        user_id: UUID,
        glassdoor_username: str,
        glassdoor_password: str
    ) -> User:
        """Update user's Glassdoor username and password (plain text)"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()
            
            if not model:
                raise RepositoryException(f"User not found: {user_id}")
            
            model.glassdoor_username = glassdoor_username
            model.glassdoor_password = glassdoor_password
            
            await self.session.flush()
            await self.session.refresh(model)
            
            logger.info(f"Updated Glassdoor username/password for user {user_id}")
            return self._to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to update Glassdoor username/password for user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to update Glassdoor username/password: {str(e)}")
    
    async def update_encrypted_indeed_credentials(
        self,
        user_id: UUID,
        encrypted_username: str,
        encrypted_password: str
    ) -> User:
        """Update user's encrypted Indeed credentials"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()
            
            if not model:
                raise RepositoryException(f"User not found: {user_id}")
            
            model.encrypted_indeed_username = encrypted_username
            model.encrypted_indeed_password = encrypted_password
            
            await self.session.flush()
            await self.session.refresh(model)
            
            logger.info(f"Updated encrypted Indeed credentials for user {user_id}")
            return self._to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to update encrypted Indeed credentials for user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to update encrypted Indeed credentials: {str(e)}")
    
    async def update_encrypted_glassdoor_credentials(
        self,
        user_id: UUID,
        encrypted_username: str,
        encrypted_password: str
    ) -> User:
        """Update user's encrypted Glassdoor credentials"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()
            
            if not model:
                raise RepositoryException(f"User not found: {user_id}")
            
            model.encrypted_glassdoor_username = encrypted_username
            model.encrypted_glassdoor_password = encrypted_password
            
            await self.session.flush()
            await self.session.refresh(model)
            
            logger.info(f"Updated encrypted Glassdoor credentials for user {user_id}")
            return self._to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to update encrypted Glassdoor credentials for user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to update encrypted Glassdoor credentials: {str(e)}")

    async def update_browser_profile(
        self,
        user_id: UUID,
        profile_json: str
    ) -> User:
        """Update user's persistent browser profile (normalized cookies + fingerprint)"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()
            
            if not model:
                raise RepositoryException(f"User not found: {user_id}")
            
            model.persistent_browser_profile = profile_json
            
            await self.session.flush()
            await self.session.refresh(model)
            
            logger.info(f"Updated persistent browser profile for user {user_id}")
            return self._to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to update browser profile for user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to update browser profile: {str(e)}")
    
    async def get_by_google_id(self, google_user_id: str) -> Optional[User]:
        """Get user by Google user ID"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.google_user_id == google_user_id)
            )
            model = result.scalar_one_or_none()
            
            if model:
                return self._to_entity(model)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user by Google ID {google_user_id}: {str(e)}")
            raise RepositoryException(f"Failed to get user: {str(e)}")
    
    async def update_google_credentials(
        self,
        user_id: UUID,
        google_user_id: str,
        google_access_token: str,
        google_refresh_token: Optional[str] = None
    ) -> User:
        """Update user's Google OAuth credentials"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()
            
            if not model:
                raise RepositoryException(f"User not found: {user_id}")
            
            model.google_user_id = google_user_id
            model.google_access_token = google_access_token
            if google_refresh_token:
                model.google_refresh_token = google_refresh_token
            
            await self.session.flush()
            await self.session.refresh(model)
            
            logger.info(f"Updated Google OAuth credentials for user {user_id}")
            return self._to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to update Google credentials for user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to update Google credentials: {str(e)}")

    async def update_session_outcome(
        self,
        user_id: UUID,
        cooldown_until: Optional[datetime],
        last_session_outcome: Optional[str],
    ) -> User:
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()

            if not model:
                raise RepositoryException(f"User not found: {user_id}")

            model.cooldown_until = cooldown_until
            model.last_session_outcome = last_session_outcome

            await self.session.flush()
            await self.session.refresh(model)

            logger.info(
                f"Updated session outcome for user {user_id} (cooldown_until={cooldown_until}, outcome={last_session_outcome})"
            )
            return self._to_entity(model)
        except Exception as e:
            logger.error(f"Failed to update session outcome for user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to update session outcome: {str(e)}")
    
    async def update_persistent_browser_profile(self, user_id: UUID, encrypted_profile: str) -> User:
        """Update user's persistent browser profile (LinkedIn session cookies)"""
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            model = result.scalar_one_or_none()

            if not model:
                raise RepositoryException(f"User not found: {user_id}")

            model.persistent_browser_profile = encrypted_profile

            await self.session.flush()
            await self.session.refresh(model)

            logger.info(f"Updated persistent browser profile for user {user_id}")
            return self._to_entity(model)
        except Exception as e:
            logger.error(f"Failed to update browser profile for user {user_id}: {str(e)}")
            raise RepositoryException(f"Failed to update browser profile: {str(e)}")
    
    def _to_entity(self, model: UserModel) -> User:
        """Convert ORM model to domain entity"""
        salary_range = None
        if model.salary_expectation:
            salary_range = SalaryRange(min_salary=model.salary_expectation)
        
        return User(
            id=model.id,
            email=Email(model.email),
            password_hash=model.password_hash,
            full_name=model.full_name,
            target_job_title=model.target_job_title,
            industry=model.industry,
            current_job_title=model.current_job_title,
            salary_expectation=salary_range,
            resume_url=model.resume_url,
            resume_base64=model.resume_base64,
            resume_parsed_data=model.resume_parsed_data,
            fcm_token=model.fcm_token,
            linkedin_username=model.linkedin_username,
            linkedin_password=model.linkedin_password,
            indeed_username=model.indeed_username,
            indeed_password=model.indeed_password,
            glassdoor_username=model.glassdoor_username,
            glassdoor_password=model.glassdoor_password,
            encrypted_indeed_username=model.encrypted_indeed_username,
            encrypted_indeed_password=model.encrypted_indeed_password,
            encrypted_glassdoor_username=model.encrypted_glassdoor_username,
            encrypted_glassdoor_password=model.encrypted_glassdoor_password,
            google_user_id=model.google_user_id,
            google_access_token=model.google_access_token,
            google_refresh_token=model.google_refresh_token,
            encrypted_linkedin_email=model.encrypted_linkedin_email,
            encrypted_linkedin_password=model.encrypted_linkedin_password,
            persistent_browser_profile=model.persistent_browser_profile,
            cooldown_until=model.cooldown_until,
            last_session_outcome=model.last_session_outcome,
            job_title_priority_1=model.job_title_priority_1,
            job_title_priority_2=model.job_title_priority_2,
            job_title_priority_3=model.job_title_priority_3,
            exp_years_internship=model.exp_years_internship,
            exp_years_entry_level=model.exp_years_entry_level,
            exp_years_associate=model.exp_years_associate,
            exp_years_mid_senior_level=model.exp_years_mid_senior_level,
            exp_years_director=model.exp_years_director,
            exp_years_executive=model.exp_years_executive,
            pref_onsite=bool(model.pref_onsite),
            pref_hybrid=bool(model.pref_hybrid),
            pref_remote=bool(model.pref_remote),
            current_salary=model.current_salary,
            desired_salary=model.desired_salary,
            gender=model.gender,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
    
    def _to_model(self, entity: User) -> UserModel:
        """Convert domain entity to ORM model"""
        return UserModel(
            id=entity.id,
            email=str(entity.email),
            password_hash=entity.password_hash,
            full_name=entity.full_name,
            target_job_title=entity.target_job_title,
            industry=entity.industry,
            current_job_title=entity.current_job_title,
            salary_expectation=entity.salary_expectation.min_salary if entity.salary_expectation else None,
            resume_url=entity.resume_url,
            resume_base64=entity.resume_base64,
            resume_parsed_data=entity.resume_parsed_data,
            fcm_token=entity.fcm_token,
            linkedin_username=entity.linkedin_username,
            linkedin_password=entity.linkedin_password,
            indeed_username=entity.indeed_username,
            indeed_password=entity.indeed_password,
            glassdoor_username=entity.glassdoor_username,
            glassdoor_password=entity.glassdoor_password,
            encrypted_indeed_username=entity.encrypted_indeed_username,
            encrypted_indeed_password=entity.encrypted_indeed_password,
            encrypted_glassdoor_username=entity.encrypted_glassdoor_username,
            encrypted_glassdoor_password=entity.encrypted_glassdoor_password,
            google_user_id=entity.google_user_id,
            google_access_token=entity.google_access_token,
            google_refresh_token=entity.google_refresh_token,
            encrypted_linkedin_email=entity.encrypted_linkedin_email,
            encrypted_linkedin_password=entity.encrypted_linkedin_password,
            persistent_browser_profile=entity.persistent_browser_profile,
            
            job_title_priority_1=entity.job_title_priority_1,
            job_title_priority_2=entity.job_title_priority_2,
            job_title_priority_3=entity.job_title_priority_3,
            
            exp_years_internship=entity.exp_years_internship,
            exp_years_entry_level=entity.exp_years_entry_level,
            exp_years_associate=entity.exp_years_associate,
            exp_years_mid_senior_level=entity.exp_years_mid_senior_level,
            exp_years_director=entity.exp_years_director,
            exp_years_executive=entity.exp_years_executive,
            
            pref_onsite=1 if entity.pref_onsite else 0,
            pref_hybrid=1 if entity.pref_hybrid else 0,
            pref_remote=1 if entity.pref_remote else 0,
            current_salary=entity.current_salary,
            desired_salary=entity.desired_salary,
            gender=entity.gender,
            cooldown_until=entity.cooldown_until,
            last_session_outcome=entity.last_session_outcome
        )


# Alias for convenience
UserRepository = SQLAlchemyUserRepository

