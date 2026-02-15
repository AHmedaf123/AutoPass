"""
Preference Service Interface
Manages user preferences and resolution logic
"""
from abc import ABC, abstractmethod
from typing import Any, Dict
from uuid import UUID

from presentation.api.v1.schemas.preferences import PreferencesUpdateRequest
from domain.entities import User


class IPreferenceService(ABC):
    """Preference service interface"""
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
