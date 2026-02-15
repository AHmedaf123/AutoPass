"""
Application Tracking Service Interface
Retrieves and filters user applications
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from uuid import UUID

from domain.entities import Application


class IApplicationTrackingService(ABC):
    """Application tracking service interface"""
    
    @abstractmethod
    async def get_applications(
        self,
        user_id: UUID,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Application]:
        """
        Get user's applications with optional filters
        
        Args:
            user_id: User ID
            filters: Optional filters (status, date_from, date_to)
            limit: Max results
            offset: Pagination offset
            
        Returns:
            List of Application entities
        """
        pass
    
    @abstractmethod
    async def get_application_details(
        self,
        application_id: UUID
    ) -> Application:
        """
        Get detailed application info
        
        Args:
            application_id: Application ID
            
        Returns:
            Application entity with job details
        """
        pass
