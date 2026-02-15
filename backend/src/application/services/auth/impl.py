"""
Authentication Service Implementation
Concrete implementation of IAuthService
"""
from typing import Tuple, Optional
from uuid import UUID, uuid4
from datetime import datetime

from loguru import logger
from infrastructure.security.baseline_cookie_cipher import (
    BaselineCookieCipher,
    BaselineCookieCipherError,
)

from domain.entities import User
from domain.value_objects import Email
from core.exceptions import (
    AuthenticationException, 
    DuplicateResourceException,
    ResourceNotFoundException
)
from application.repositories.interfaces import IUserRepository
from .interfaces import IAuthService, IPasswordHasher
from .credential_verifier import CredentialVerifier


class AuthService(IAuthService):
    """Authentication service implementation"""
    
    def __init__(
        self,
        user_repository: IUserRepository,
        password_hasher: IPasswordHasher
    ):
        self.user_repo = user_repository
        self.password_hasher = password_hasher
        self.credential_verifier = CredentialVerifier()
    
    async def register(
        self, 
        email: str, 
        password: str, 
        full_name: str
    ) -> Tuple[User, str]:
        """Register a new user"""
        
        logger.info(f"Registering new user: {email}")
        
        # Validate email format
        try:
            email_vo = Email(email)
        except ValueError as e:
            raise AuthenticationException(f"Invalid email: {str(e)}")
        
        # Check if user already exists
        if await self.user_repo.exists_by_email(email):
            raise DuplicateResourceException("User", "email", email)
        
        # Hash password
        password_hash = self.password_hasher.hash_password(password)
        
        # Create user entity
        user = User(
            id=uuid4(),
            email=email_vo,
            password_hash=password_hash,
            full_name=full_name.strip(),
            target_job_title="",  # Set during onboarding
            industry="",  # Set during onboarding
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Persist user
        created_user = await self.user_repo.create(user)
        
        logger.info(f"User registered successfully: {email}")
        
        return created_user, "User registered successfully"
    
    async def login(self, email: str, password: str) -> Tuple[User, str]:
        """Authenticate user"""
        
        logger.info(f"Login attempt: {email}")
        
        # Find user
        user = await self.user_repo.get_by_email(email)
        if not user:
            logger.warning(f"Login failed: User not found - {email}")
            raise AuthenticationException("Invalid email or password")
        
        # Verify password
        if not self.password_hasher.verify_password(password, user.password_hash):
            logger.warning(f"Login failed: Invalid password - {email}")
            raise AuthenticationException("Invalid email or password")
        
        logger.info(f"User logged in successfully: {email}")
        
        return user, "Logged in successfully"
    
    async def login_with_linkedin(
        self, 
        email: str, 
        password: str
    ) -> Tuple[User, str]:
        """Authenticate using LinkedIn credentials"""
        
        logger.info(f"Attempting LinkedIn login for: {email}")
        
        # 1. Verify credentials via Selenium (returns normalized profile with cookies + fingerprint)
        is_valid, error_msg, profile = self.credential_verifier.verify_linkedin(email, password)
        
        if not is_valid:
            logger.warning(f"LinkedIn verification failed for {email}: {error_msg}")
            raise AuthenticationException(f"LinkedIn login failed: {error_msg}")
            
        # 2. Check if user exists or create new one
        try:
            user = await self.user_repo.get_by_email(email)
            message = "Logged in successfully"
            
            if not user:
                # Create new user
                logger.info(f"Creating new user from LinkedIn: {email}")
                
                # Mock password for the internal user account (since we use LinkedIn auth)
                # We generated a random secure password because they won't use it directly
                internal_password = str(uuid4())
                password_hash = self.password_hasher.hash_password(internal_password)
                
                new_user = User(
                    id=uuid4(),
                    email=Email(email),
                    password_hash=password_hash,
                    full_name="LinkedIn User", # Placeholder, ideally scraped from profile
                    target_job_title="",
                    industry="",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                user = await self.user_repo.create(new_user)
                message = "Account created via LinkedIn and logged in successfully"
            
            # 3. Update LinkedIn credentials and cookies (session cache)
            # Note: We rely on the repo to handle encryption of the password
            await self.user_repo.update_linkedin_credentials(
                user_id=user.id,
                linkedin_email=email,
                linkedin_password=password
            )
            
            # 4. Persist normalized browser profile (cookies + environment fingerprint)
            if profile:
                import json
                try:
                    cipher = BaselineCookieCipher()
                    profile_json = cipher.encrypt_profile(profile)
                except BaselineCookieCipherError as exc:
                    logger.error(f"Failed to encrypt baseline cookies: {exc}")
                    raise AuthenticationException("Failed to persist cookies securely")

                await self.user_repo.update_browser_profile(
                    user_id=user.id,
                    profile_json=profile_json
                )
                logger.info(f"Saved persistent browser profile for user {user.id}")

            return user, message

        except Exception as e:
            logger.error(f"Error during LinkedIn login process: {e}")
            raise AuthenticationException(f"System error during login: {str(e)}")
    
    async def login_with_google(
        self,
        google_user_id: str,
        email: str,
        full_name: str,
        access_token: str,
        refresh_token: Optional[str] = None
    ) -> Tuple[User, str]:
        """Authenticate using Google OAuth"""
        
        logger.info(f"Attempting Google OAuth login for: {email}")
        
        try:
            # Check if user exists by Google ID or email
            user = await self.user_repo.get_by_google_id(google_user_id)
            message = "Logged in successfully"
            
            if not user:
                # Try to find by email
                user = await self.user_repo.get_by_email(email)
                if user:
                    # Link Google account to existing user
                    await self.user_repo.update_google_credentials(
                        user_id=user.id,
                        google_user_id=google_user_id,
                        google_access_token=access_token,
                        google_refresh_token=refresh_token
                    )
                    message = "Google account linked successfully"
                else:
                    # Create new user
                    logger.info(f"Creating new user from Google OAuth: {email}")
                    
                    # Mock password for internal user account
                    internal_password = str(uuid4())
                    password_hash = self.password_hasher.hash_password(internal_password)
                    
                    new_user = User(
                        id=uuid4(),
                        email=Email(email),
                        password_hash=password_hash,
                        full_name=full_name.strip(),
                        target_job_title="",
                        industry="",
                        google_user_id=google_user_id,
                        google_access_token=access_token,
                        google_refresh_token=refresh_token,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    
                    user = await self.user_repo.create(new_user)
                    message = "Account created via Google and logged in successfully"
            
            # Update Google tokens if user exists
            else:
                await self.user_repo.update_google_credentials(
                    user_id=user.id,
                    google_user_id=google_user_id,
                    google_access_token=access_token,
                    google_refresh_token=refresh_token
                )
            
            return user, message

        except Exception as e:
            logger.error(f"Error during Google OAuth login process: {e}")
            raise AuthenticationException(f"System error during Google login: {str(e)}")
    
    async def link_google_account(
        self,
        user_id: UUID,
        google_user_id: str,
        email: str,
        access_token: str,
        refresh_token: Optional[str] = None
    ) -> None:
        """
        Link Google account to existing user
        
        Args:
            user_id: Existing user's ID
            google_user_id: Google user ID (sub)
            email: Google email
            access_token: Google access token
            refresh_token: Google refresh token (optional)
        """
        try:
            logger.info(f"Linking Google account {email} to user {user_id}")
            
            # Update user's Google credentials
            await self.user_repo.update_google_credentials(
                user_id=user_id,
                google_user_id=google_user_id,
                google_access_token=access_token,
                google_refresh_token=refresh_token
            )
            
            logger.info(f"Successfully linked Google account to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error linking Google account: {e}")
            raise AuthenticationException(f"Failed to link Google account: {str(e)}")
