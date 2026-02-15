"""
Resume Context Manager
Pre-indexed resume sections for efficient context injection.
Routes questions to relevant sections only - not full resume.
"""
import hashlib
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from loguru import logger


@dataclass
class ResumeSection:
    """A section of the resume"""
    name: str
    content: str
    keywords: List[str]
    token_estimate: int


class ResumeContextManager:
    """
    Pre-indexed resume for efficient context injection.
    
    Instead of sending full resume for every question:
    - Extract sections once at init
    - Route questions to relevant sections
    - Send only relevant context (70-80% token reduction)
    """
    
    # Question-to-section routing patterns
    SECTION_PATTERNS = {
        "experience": [
            r"experience", r"years?", r"worked", r"previous", r"current",
            r"role", r"position", r"job", r"employment", r"responsibilities"
        ],
        "skills": [
            r"skill", r"technolog", r"proficien", r"expert", r"familiar",
            r"knowledge", r"tools?", r"languages?", r"framework", r"software"
        ],
        "education": [
            r"education", r"degree", r"university", r"college", r"school",
            r"graduat", r"certific", r"course", r"training", r"academic"
        ],
        "contact": [
            r"email", r"phone", r"address", r"contact", r"linkedin",
            r"github", r"portfolio", r"website", r"location"
        ],
        "summary": [
            r"summary", r"objective", r"about", r"overview", r"profile",
            r"interested", r"why", r"motivation", r"goal"
        ],
        "availability": [
            r"start", r"available", r"notice", r"when", r"relocat",
            r"remote", r"hybrid", r"onsite", r"travel"
        ],
        "salary": [
            r"salary", r"compensation", r"expectation", r"rate", r"pay"
        ]
    }
    
    # Default answers for common non-resume questions
    DEFAULT_ANSWERS = {
        "salary": "Open to discussion based on total compensation and role responsibilities.",
        "availability": "Available to start within 2 weeks of offer acceptance.",
        "sponsorship": "I am authorized to work and do not require sponsorship.",
        "relocation": "Open to relocation for the right opportunity.",
        "remote": "I am comfortable with remote, hybrid, or on-site arrangements."
    }
    
    def __init__(self, resume_parsed: Optional[Dict[str, Any]] = None):
        """
        Initialize with parsed resume data.
        
        Args:
            resume_parsed: Parsed resume dictionary with sections
        """
        self.resume_parsed = resume_parsed or {}
        self.sections: Dict[str, ResumeSection] = {}
        self._hash: Optional[str] = None
        
        # Extract and index sections
        self._extract_sections()
    
    def _extract_sections(self) -> None:
        """Extract and compress resume sections"""
        
        # Contact info
        contact = self.resume_parsed.get("contact", {})
        if isinstance(contact, dict):
            contact_text = f"Name: {contact.get('name', '')}\nEmail: {contact.get('email', '')}\nPhone: {contact.get('phone', '')}\nLocation: {contact.get('location', '')}"
        else:
            contact_text = str(contact)
        
        self.sections["contact"] = ResumeSection(
            name="contact",
            content=contact_text[:300],
            keywords=["email", "phone", "name", "location"],
            token_estimate=len(contact_text.split())
        )
        
        # Skills
        skills = self.resume_parsed.get("skills", [])
        if isinstance(skills, list):
            skills_text = ", ".join(skills[:30])  # Top 30 skills
        else:
            skills_text = str(skills)
        
        self.sections["skills"] = ResumeSection(
            name="skills",
            content=skills_text[:500],
            keywords=skills[:15] if isinstance(skills, list) else [],
            token_estimate=len(skills_text.split())
        )
        
        # Experience (compressed)
        experience = self.resume_parsed.get("experience", [])
        exp_text = self._compress_experience(experience)
        
        self.sections["experience"] = ResumeSection(
            name="experience",
            content=exp_text[:800],
            keywords=["experience", "work", "job", "role"],
            token_estimate=len(exp_text.split())
        )
        
        # Education
        education = self.resume_parsed.get("education", [])
        edu_text = self._compress_education(education)
        
        self.sections["education"] = ResumeSection(
            name="education",
            content=edu_text[:400],
            keywords=["education", "degree", "university"],
            token_estimate=len(edu_text.split())
        )
        
        # Summary
        summary = self.resume_parsed.get("summary", "")
        if isinstance(summary, str):
            summary_text = summary[:500]
        else:
            summary_text = str(summary)[:500]
        
        self.sections["summary"] = ResumeSection(
            name="summary",
            content=summary_text,
            keywords=["summary", "profile", "about"],
            token_estimate=len(summary_text.split())
        )
        
        # Calculate total years of experience
        total_years = self._calculate_total_experience()
        self.sections["years"] = ResumeSection(
            name="years",
            content=f"Total years of experience: {total_years}",
            keywords=["years", "experience"],
            token_estimate=10
        )
        
        logger.info(f"Resume indexed: {len(self.sections)} sections, ~{self.total_tokens} tokens")
    
    def _compress_experience(self, experience: List[Any]) -> str:
        """Compress experience to essential info"""
        if not experience:
            return "No experience listed."
        
        lines = []
        for i, exp in enumerate(experience[:5]):  # Top 5 experiences
            if isinstance(exp, dict):
                title = exp.get("title", exp.get("position", "Role"))
                company = exp.get("company", exp.get("organization", "Company"))
                duration = exp.get("duration", exp.get("dates", ""))
                desc = exp.get("description", "")[:150]  # Truncate description
                
                lines.append(f"{i+1}. {title} at {company} ({duration})")
                if desc:
                    lines.append(f"   {desc}")
            else:
                lines.append(f"{i+1}. {str(exp)[:100]}")
        
        return "\n".join(lines)
    
    def _compress_education(self, education: List[Any]) -> str:
        """Compress education to essential info"""
        if not education:
            return "No education listed."
        
        lines = []
        for edu in education[:3]:  # Top 3 education entries
            if isinstance(edu, dict):
                degree = edu.get("degree", edu.get("title", "Degree"))
                institution = edu.get("institution", edu.get("school", "Institution"))
                year = edu.get("year", edu.get("graduation_year", ""))
                
                lines.append(f"- {degree} from {institution} ({year})")
            else:
                lines.append(f"- {str(edu)[:100]}")
        
        return "\n".join(lines)
    
    def _calculate_total_experience(self) -> int:
        """Calculate total years of experience"""
        experience = self.resume_parsed.get("experience", [])
        total = 0
        
        for exp in experience:
            if isinstance(exp, dict):
                years = exp.get("duration_years", exp.get("years", 0))
                if isinstance(years, (int, float)):
                    total += years
        
        return max(int(total), 1)  # At least 1 year
    
    @property
    def total_tokens(self) -> int:
        """Estimated total tokens across all sections"""
        return sum(s.token_estimate for s in self.sections.values())
    
    @property
    def resume_hash(self) -> str:
        """Hash of resume for caching"""
        if not self._hash:
            content = str(self.resume_parsed)
            self._hash = hashlib.md5(content.encode()).hexdigest()[:16]
        return self._hash
    
    def get_relevant_context(self, question: str) -> str:
        """
        Route question to relevant section only - not full resume.
        
        Args:
            question: The form question to answer
            
        Returns:
            Relevant resume context (minimal tokens)
        """
        q_lower = question.lower()
        
        # Check each section's patterns
        for section_name, patterns in self.SECTION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, q_lower):
                    if section_name in self.sections:
                        return self.sections[section_name].content
                    elif section_name in self.DEFAULT_ANSWERS:
                        return f"[Default answer for {section_name}]"
        
        # Default to summary
        return self.sections.get("summary", ResumeSection("", "No context", [], 0)).content
    
    def get_answer_hint(self, question: str) -> Optional[str]:
        """
        Get default answer hint for common non-resume questions.
        
        Args:
            question: The form question
            
        Returns:
            Default answer if available, None otherwise
        """
        q_lower = question.lower()
        
        for key, patterns in self.SECTION_PATTERNS.items():
            if key in self.DEFAULT_ANSWERS:
                for pattern in patterns:
                    if re.search(pattern, q_lower):
                        return self.DEFAULT_ANSWERS[key]
        
        return None
    
    def get_compressed_context(self, max_tokens: int = 500) -> str:
        """
        Get compressed context for batch answering.
        
        Prioritizes: skills, summary, experience
        """
        parts = []
        token_count = 0
        
        priority_order = ["skills", "summary", "experience", "education", "years"]
        
        for section_name in priority_order:
            if section_name in self.sections:
                section = self.sections[section_name]
                if token_count + section.token_estimate <= max_tokens:
                    parts.append(f"[{section_name.upper()}]\n{section.content}")
                    token_count += section.token_estimate
        
        return "\n\n".join(parts)
    
    def get_skills_list(self) -> List[str]:
        """Get list of skills for matching"""
        skills = self.resume_parsed.get("skills", [])
        if isinstance(skills, list):
            return skills[:20]
        return []
    
    def get_years_experience(self) -> int:
        """Get total years of experience"""
        return self._calculate_total_experience()
    
    def answer_quick(self, question: str) -> Optional[str]:
        """
        Quick answer for common questions without LLM.
        
        Returns answer if possible, None if LLM needed.
        """
        q_lower = question.lower()
        
        # Years of experience
        if re.search(r"years?\s*(of)?\s*experience", q_lower):
            return str(self.get_years_experience())
        
        # Email
        if re.search(r"email", q_lower):
            contact = self.resume_parsed.get("contact", {})
            if isinstance(contact, dict) and contact.get("email"):
                return contact["email"]
        
        # Phone
        if re.search(r"phone|mobile|contact number", q_lower):
            contact = self.resume_parsed.get("contact", {})
            if isinstance(contact, dict) and contact.get("phone"):
                return contact["phone"]
        
        # Name
        if re.search(r"full\s*name|your\s*name", q_lower):
            contact = self.resume_parsed.get("contact", {})
            if isinstance(contact, dict) and contact.get("name"):
                return contact["name"]
        
        # Salary (default)
        if re.search(r"salary|compensation|pay", q_lower):
            return self.DEFAULT_ANSWERS["salary"]
        
        # Start date (default)
        if re.search(r"start|available|when can you", q_lower):
            return self.DEFAULT_ANSWERS["availability"]
        
        # Sponsorship (default)
        if re.search(r"sponsor|visa|authorized|legally", q_lower):
            return self.DEFAULT_ANSWERS["sponsorship"]
        
        return None
