"""
ResumeService Implementation
Handles resume upload, PDF parsing, and keyword extraction
"""
from typing import Dict, Any
from uuid import UUID
import pdfplumber
from fastapi import UploadFile, HTTPException

from application.services.resume import IResumeService
from application.repositories.interfaces import IUserRepository
from infrastructure.external.file_storage_service import LocalFileStorageService
from domain.value_objects import SalaryRange
from domain.enums import Industry, WorkType, INDUSTRY_SUBFIELDS
from core.logging_config import logger


import base64
from datetime import datetime
from presentation.schemas.resume import (
    ParsedResume, PersonalInfo, ContactDetails, SummaryDetails,
    ExperienceDetails, EducationDetails, SkillsDetails, TechnicalSkills,
    ResumeMetadata, ResumePreferences, RawData, LocationDetails
)

class ResumeService(IResumeService):
    """Resume service implementation"""
    
    def __init__(
        self,
        user_repository: IUserRepository,
        file_storage: LocalFileStorageService
    ):
        """
        Initialize resume service
        
        Args:
            user_repository: User repository
            file_storage: File storage service
        """
        self.user_repo = user_repository
        self.file_storage = file_storage
    
    async def upload_resume(
        self,
        user_id: UUID,
        file: UploadFile
    ) -> Dict[str, Any]:
        """
        Upload and parse resume
        
        Args:
            user_id: User ID
            file: Resume file (PDF)
            
        Returns:
            File path where resume is stored
        """
        try:
            # 1. Read file content
            file_content = await file.read()
            # Reset cursor for storage service
            await file.seek(0)
            
            # 2. Encode to Base64
            resume_base64 = base64.b64encode(file_content).decode('utf-8')
            
            # 3. Save file using file storage service
            file_path = await self.file_storage.save_file(user_id, file, "resume")
            
            # 4. Update user record with resume path and base64
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # 5. Parse resume (New Logic)
            parsed_data = await self.parse_resume_to_schema(file_path, user_id, file_content)
            
            # 6. Create updated user
            from dataclasses import replace
            updated_user = replace(
                user,
                resume_url=file_path,
                resume_base64=resume_base64,
                resume_parsed_data=parsed_data.model_dump()
            )
            
            await self.user_repo.update(updated_user)
            
            logger.info(f"Resume uploaded and parsed for user {user_id}")
            # Return parsed resume data as a dictionary so API layers
            # can reuse the structured output directly
            return parsed_data.model_dump()
        
        except Exception as e:
            logger.error(f"Error uploading resume: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to upload resume: {str(e)}")
    
    async def parse_resume_to_schema(
        self,
        file_path: str,
        user_id: UUID,
        file_content: bytes = None # Optional content if already read
    ) -> ParsedResume:
        """
        Parse resume PDF into detailed schema
        """
        try:
            text_content = ""
            
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_content += page_text + "\n"
            
            # Initialize empty schema components - Best effort extraction
            # 1. Personal Info
            personal_info = self._extract_personal_info(text_content)
            
            # 2. Skills
            skills = self._extract_skills_detailed(text_content)
            
            # 3. Experience (Heuristic)
            experience = self._extract_experience_blocks(text_content)
            
            # 4. Education (Heuristic)
            education = self._extract_education_blocks(text_content)
            
            # 5. Metadata
            metadata = ResumeMetadata(
                user_id=str(user_id),
                source="pdf",
                parsed_at=datetime.utcnow().isoformat(),
                confidence_score=0.85 # Placeholder
            )
            
            # 6. Raw Data
            raw_data = RawData(original_text=text_content)

            return ParsedResume(
                resume_metadata=metadata,
                personal_info=personal_info,
                skills=skills,
                experience=experience,
                education=education,
                raw_data=raw_data
                # Other fields empty/default for now
            )
        
        except Exception as e:
            logger.error(f"Error parsing resume to schema: {e}")
            # Return empty structure on failure to avoid breaking upload
            return ParsedResume()
    
    def _extract_personal_info(self, text: str) -> PersonalInfo:
        """Extract personal info using heuristics"""
        import re
        
        # Email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_match = re.search(email_pattern, text)
        email = email_match.group(0) if email_match else ""
        
        # Phone
        phone_pattern = r'(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}'
        phone_match = re.search(phone_pattern, text)
        phone = phone_match.group(0) if phone_match else ""
        
        # Links
        linkedin_pattern = r'linkedin\.com/in/[\w-]+'
        github_pattern = r'github\.com/[\w-]+'
        
        linkedin_match = re.search(linkedin_pattern, text)
        github_match = re.search(github_pattern, text)
        
        linkedin = "https://" + linkedin_match.group(0) if linkedin_match else ""
        github = "https://" + github_match.group(0) if github_match else ""
        
        # Name (First line heuristic + simple NER placeholder)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        full_name = lines[0] if lines else ""
        # Heuristic: Name usually isn't longer than 40 chars or contains digits
        if len(full_name) > 40 or any(char.isdigit() for char in full_name): 
             full_name = "" 
        
        name_parts = full_name.split()
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
        
        return PersonalInfo(
            full_name=full_name,
            first_name=first_name,
            last_name=last_name,
            contact=ContactDetails(
                email=email,
                phone=phone,
                linkedin_url=linkedin,
                github_url=github
            )
        )

    def _extract_skills_detailed(self, text: str) -> SkillsDetails:
        """Extract skills using comprehensive keyword matching"""
        text_lower = text.lower()
        
        # Extended skill keywords
        languages = ["python", "javascript", "java", "c++", "c#", "go", "ruby", "typescript", "swift", "kotlin", "sql", "rust", "php", "html", "css"]
        frameworks = ["react", "angular", "vue", "django", "flask", "fastapi", "spring", "express", "rails", "next.js", "node.js", ".net", "pytorch", "tensorflow"]
        tools = ["git", "docker", "kubernetes", "aws", "azure", "gcp", "jenkins", "jira", "terraform", "ansible", "redis", "postgres", "mongodb"]
        soft_skills_list = ["leadership", "communication", "teamwork", "problem solving", "adaptability", "critical thinking", "time management"]
        
        found_langs = [skill for skill in languages if skill in text_lower]
        found_fw = [skill for skill in frameworks if skill in text_lower]
        found_tools = [skill for skill in tools if skill in text_lower]
        found_soft = [skill for skill in soft_skills_list if skill in text_lower]
        
        return SkillsDetails(
            technical_skills=TechnicalSkills(
                programming_languages=list(set(found_langs)),
                frameworks=list(set(found_fw)),
                tools=list(set(found_tools)),
                databases=[s for s in ["postgres", "mongodb", "mysql", "redis", "dynamodb"] if s in text_lower],
                cloud_platforms=[s for s in ["aws", "azure", "gcp", "google cloud"] if s in text_lower]
            ),
            soft_skills=list(set(found_soft))
        )

    def _extract_experience_blocks(self, text: str) -> ExperienceDetails:
        """Extract experience blocks (Heuristic)"""
        import re
        
        # Attempt to find "Experience" section
        experience_pattern = r"(?i)(experience|work history|employment)([\s\S]*?)(EDUCATION|SKILLS|PROJECTS|$)"
        match = re.search(experience_pattern, text)
        
        employment_history = []
        if match:
            content = match.group(2).strip()
            # Split by dates roughly: (Jan 2020 - Present) or (2019-2021)
            # This is very loose regex for demo purposes
            date_pattern = r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s?\d{4}|Present|Current)"
            
            # Simple line-by-line block builder (Naive)
            lines = content.split('\n')
            current_block = {}
            for line in lines:
                if len(line.strip()) < 3: continue
                # If line is short and has date-like structure, assume header
                if re.search(date_pattern, line):
                    if current_block:
                         # Save previous block
                         employment_history.append(EmploymentHistory(
                             role=current_block.get('role', 'Role'),
                             company=current_block.get('company', 'Company'),
                             description=current_block.get('desc', '')
                         ))
                         current_block = {}
                    
                    # Assume this line is Role/Company
                    current_block['role'] = line.strip() 
                    current_block['company'] = "Extracted Company" # Hard to parse exact company without NER
                    current_block['desc'] = ""
                else:
                    if current_block:
                        current_block['desc'] = (current_block.get('desc', '') + " " + line.strip()).strip()

            # Add last block
            if current_block:
                  employment_history.append(EmploymentHistory(
                             role=current_block.get('role', 'Role'),
                             company=current_block.get('company', 'Company'),
                             description=current_block.get('desc', '')
                         ))
        
        # Calculate total years (wild guess based on number of blocks * 1.5 years)
        total_years = len(employment_history) * 1.5
        
        return ExperienceDetails(
            total_experience_years=total_years,
            employment_history=employment_history
        )

    def _extract_education_blocks(self, text: str) -> List[EducationDetails]:
        """Extract education blocks"""
        import re
        education_pattern = r"(?i)(education)([\s\S]*?)(EXPERIENCE|SKILLS|PROJECTS|$)"
        match = re.search(education_pattern, text)
        
        education_list = []
        if match:
            content = match.group(2).strip()
            # Naively look for keywords: University, College, Bachelor, Master
            lines = content.split('\n')
            for line in lines:
                if any(k in line.lower() for k in ["university", "college", "institute", "school"]):
                    education_list.append(EducationDetails(
                        institution=line.strip(),
                        degree="Degree Extracted", # Placeholder
                        is_completed=True
                    ))
                    
        return education_list
