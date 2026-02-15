"""
Resume Service Interface
Handles resume upload, parsing, and keyword extraction
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from uuid import UUID

from fastapi import UploadFile




class IResumeService(ABC):
    """Resume service interface"""
    
    @abstractmethod
    async def upload_resume(
        self,
        user_id: UUID,
        file: UploadFile
    ) -> Dict[str, Any]:
        """Upload and validate resume file, returning parsed data.

        Args:
            user_id: User ID
            file: Resume file (PDF)

        Returns:
            Parsed resume data as a dictionary
        """
        pass
    
    @abstractmethod
    async def parse_resume_to_schema(
        self,
        file_path: str,
        user_id: UUID,
        file_content: bytes = None
    ) -> Any:  # Returning Any to avoid circular dependency with Presentation layer, or could type ignore
        """
        Parse resume PDF into detailed schema
        
        Args:
            file_path: Path to resume file
            user_id: User ID
            file_content: Optional file content bytes
            
        Returns:
            ParsedResume object
        """
        pass
