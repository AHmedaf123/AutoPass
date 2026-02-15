"""
File Storage Service
Wrapper for LocalFileStorageService with resume parsing
"""
import base64
from typing import Tuple, Dict, Optional
from uuid import UUID
from fastapi import UploadFile
import pdfplumber
from loguru import logger

from infrastructure.external.file_storage_service import LocalFileStorageService


class FileStorageService:
    """File storage service with resume parsing"""
    
    def __init__(self):
        self.local_storage = LocalFileStorageService()
    
    async def save_resume(
        self,
        user_id: UUID,
        file: UploadFile
    ) -> Tuple[str, str, Optional[Dict]]:
        """
        Save resume file and parse it
        
        Returns:
            Tuple of (file_path, base64_content, parsed_data)
        """
        # Save to local storage
        file_path = await self.local_storage.save_file(user_id, file, "resume")
        
        # Read file content for base64 encoding
        await file.seek(0)
        content = await file.read()
        base64_content = base64.b64encode(content).decode('utf-8')
        
        # Parse resume
        parsed_data = await self._parse_resume(content)
        
        return file_path, base64_content, parsed_data
    
    async def _parse_resume(self, content: bytes) -> Optional[Dict]:
        """
        Parse resume PDF and extract structured data
        
        Returns:
            Dict with extracted data or None
        """
        try:
            import io
            pdf_file = io.BytesIO(content)
            
            text = ""
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
            
            # Simple parsing (in production, use more sophisticated NLP)
            parsed = {
                "summary": text[:500],  # First 500 chars as summary
                "full_text": text,
                "skills": self._extract_skills(text),
                "experience": [],
                "education": []
            }
            
            return parsed
            
        except Exception as e:
            logger.error(f"Error parsing resume: {e}")
            return {"full_text": "", "summary": "", "skills": []}
    
    def _extract_skills(self, text: str) -> list:
        """Extract skills from text (simple keyword matching)"""
        skills_keywords = [
            "Python", "Java", "JavaScript", "React", "Node.js", "SQL",
            "AWS", "Docker", "Kubernetes", "Git", "Machine Learning",
            "Data Analysis", "FastAPI", "Django", "Flask"
        ]
        
        found_skills = []
        text_lower = text.lower()
        
        for skill in skills_keywords:
            if skill.lower() in text_lower:
                found_skills.append(skill)
        
        return found_skills
