"""
PreferenceService Implementation
Manages user preferences with resolution logic and caching
"""
from typing import Any, Dict, Optional
from uuid import UUID
from dataclasses import replace, asdict
from datetime import datetime

from application.services.preference import IPreferenceService
from application.repositories.interfaces import IUserRepository
from application.services.resume import IResumeService
from presentation.api.v1.schemas.preferences import PreferencesUpdateRequest
from domain.entities import User
from core.logging_config import logger


class PreferenceService(IPreferenceService):
    """Preference service implementation with caching"""
    
    def __init__(
        self,
        user_repository: IUserRepository,
        # preferences_repository removed - unified table
        resume_service: IResumeService,
        # cache_service will be added when we implement Redis cache
    ):
        """
        Initialize preference service
        
        Args:
            user_repository: User repository
            resume_service: Resume service for keyword extraction
        """
        self.user_repo = user_repository
        self.resume_service = resume_service
    
    async def update_preferences(
        self,
        user_id: UUID,
        preferences: PreferencesUpdateRequest
    ) -> User:
        """
        Update user preferences (unified table)
        
        Args:
            user_id: User ID
            preferences: New preferences schema
            
        Returns:
            Updated User entity
        """
        try:
            # Check if user exists
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")

            # Update fields
            updated_user = replace(
                user,
                job_title_priority_1 = preferences.job_title_priority_1 if preferences.job_title_priority_1 is not None else user.job_title_priority_1,
                job_title_priority_2 = preferences.job_title_priority_2 if preferences.job_title_priority_2 is not None else user.job_title_priority_2,
                job_title_priority_3 = preferences.job_title_priority_3 if preferences.job_title_priority_3 is not None else user.job_title_priority_3,
                
                exp_years_internship = preferences.exp_years_internship if preferences.exp_years_internship is not None else user.exp_years_internship,
                exp_years_entry_level = preferences.exp_years_entry_level if preferences.exp_years_entry_level is not None else user.exp_years_entry_level,
                exp_years_associate = preferences.exp_years_associate if preferences.exp_years_associate is not None else user.exp_years_associate,
                exp_years_mid_senior_level = preferences.exp_years_mid_senior_level if preferences.exp_years_mid_senior_level is not None else user.exp_years_mid_senior_level,
                exp_years_director = preferences.exp_years_director if preferences.exp_years_director is not None else user.exp_years_director,
                exp_years_executive = preferences.exp_years_executive if preferences.exp_years_executive is not None else user.exp_years_executive,
                
                pref_onsite = preferences.pref_onsite if preferences.pref_onsite is not None else user.pref_onsite,
                pref_hybrid = preferences.pref_hybrid if preferences.pref_hybrid is not None else user.pref_hybrid,
                pref_remote = preferences.pref_remote if preferences.pref_remote is not None else user.pref_remote,
                
                updated_at=datetime.utcnow()
            )
            
            result = await self.user_repo.update(updated_user)
            
            # TODO: Invalidate cache here
            
            logger.info(f"Updated unified profile/preferences for user {user_id}")
            return result
        
        except Exception as e:
            logger.error(f"Error updating preferences: {e}")
            raise

    async def get_resolved_preferences(
        self,
        user_id: UUID
    ) -> User:
        """
        Get resolved preferences (from User table)
        
        Args:
            user_id: User ID
            
        Returns:
            User entity (containing preferences)
        """
        try:
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")
                
            return user
        
        except Exception as e:
            logger.error(f"Error getting preferences: {e}")
            raise
