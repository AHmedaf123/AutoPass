"""
LocalFileStorageService
Handles file upload, validation, and storage on local filesystem
"""
import os
import aiofiles
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import UploadFile, HTTPException

from core.config import settings
from core.logging_config import logger


class LocalFileStorageService:
    """Local filesystem storage service"""
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize file storage service
        
        Args:
            base_path: Base directory for file storage (default from settings)
        """
        self.base_path = Path(base_path or getattr(settings, 'UPLOAD_DIR', './uploads/resumes'))
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def save_file(
        self,
        user_id: UUID,
        file: UploadFile,
        file_type: str = "resume"
    ) -> str:
        """
        Save uploaded file to local storage
        
        Args:
            user_id: User ID for file organization
            file: Uploaded file
            file_type: Type of file (resume, cover_letter, etc.)
            
        Returns:
            Absolute file path where file is saved
        """
        # Validate file
        await self._validate_file(file, file_type)
        
        # Create user directory
        user_dir = self.base_path / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        file_extension = Path(file.filename).suffix
        filename = f"{file_type}{file_extension}"
        file_path = user_dir / filename
        
        # Save file
        try:
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            logger.info(f"File saved successfully: {file_path}")
            return str(file_path.absolute())
        
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    async def get_file_path(
        self,
        user_id: UUID,
        file_type: str = "resume"
    ) -> Optional[str]:
        """
        Get path to existing file
        
        Args:
            user_id: User ID
            file_type: Type of file
            
        Returns:
            Absolute file path or None if not found
        """
        user_dir = self.base_path / str(user_id)
        if not user_dir.exists():
            return None
        
        # Look for file with any extension
        for ext in ['.pdf', '.PDF']:
            file_path = user_dir / f"{file_type}{ext}"
            if file_path.exists():
                return str(file_path.absolute())
        
        return None
    
    async def delete_file(
        self,
        user_id: UUID,
        file_type: str = "resume"
    ) -> bool:
        """Delete file from storage"""
        file_path = await self.get_file_path(user_id, file_type)
        if file_path and Path(file_path).exists():
            try:
                Path(file_path).unlink()
                logger.info(f"File deleted: {file_path}")
                return True
            except Exception as e:
                logger.error(f"Error deleting file: {e}")
                return False
        return False
    
    async def _validate_file(
        self,
        file: UploadFile,
        file_type: str
    ) -> None:
        """
        Validate uploaded file
        
        Args:
            file: Uploaded file
            file_type: Expected file type
            
        Raises:
            HTTPException if validation fails
        """
        # Validate file type
        if file_type == "resume":
            allowed_extensions = ['.pdf', '.PDF']
            max_size_mb = getattr(settings, 'MAX_RESUME_SIZE_MB', 5)
        else:
            allowed_extensions = ['.pdf', '.PDF']
            max_size_mb = 5
        
        # Check extension
        file_extension = Path(file.filename).suffix
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Only {', '.join(allowed_extensions)} allowed."
            )
        
        # Check file size (read content to get size)
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning
        
        max_size_bytes = max_size_mb * 1024 * 1024
        if file_size > max_size_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is {max_size_mb}MB."
            )
