"""
Resume Enhancement Service
AI-powered job-specific resume enhancement using OpenRouter LLM.
Generates enhanced summary and skills tailored to job descriptions.
"""
import httpx
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger

from core.config import settings


@dataclass
class EnhancedResumeContent:
    """Container for AI-enhanced resume content."""
    enhanced_summary: str
    enhanced_skills: List[str]
    original_summary: str
    original_skills: List[str]


class ResumeEnhancementService:
    """
    Service for AI-powered resume enhancement.
    
    Enhances user's summary and skills sections based on job description
    using OpenRouter LLM (GPT-4o-mini) for ATS optimization and keyword targeting.
    
    Key features:
    - Stateless enhancement (no DB persistence)
    - Job-specific optimization
    - ATS keyword targeting
    - No hallucination of experience
    """
    
    def __init__(self, openrouter_api_key: Optional[str] = None):
        """
        Initialize the resume enhancement service.
        
        Args:
            openrouter_api_key: OpenRouter API key. Falls back to settings if not provided.
        """
        self.api_key = openrouter_api_key or settings.OPENROUTER_API_KEY
        if not self.api_key:
            raise ValueError("OpenRouter API key is required for resume enhancement")
        
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "openai/gpt-4o-mini"
        self.max_retries = 3
    
    async def enhance_resume(
        self,
        resume_data: Dict[str, Any],
        job_description: str,
        job_title: Optional[str] = None,
        company: Optional[str] = None
    ) -> EnhancedResumeContent:
        """
        Enhance resume summary and skills based on job description.
        
        Args:
            resume_data: Structured resume JSON containing summary and skills
            job_description: Full job description text
            job_title: Optional job title for context
            company: Optional company name for context
            
        Returns:
            EnhancedResumeContent with original and enhanced fields
        """
        # Extract current summary and skills
        original_summary = resume_data.get("summary", "") or ""
        original_skills = resume_data.get("skills", []) or []

        # Robustly flatten/convert skills to a list of strings for prompt (copied from test script)
        flat_skills = []
        if isinstance(original_skills, dict):
            for category, skill_list in original_skills.items():
                if isinstance(skill_list, list):
                    flat_skills.extend(skill_list)
                elif isinstance(skill_list, str):
                    flat_skills.append(skill_list)
        elif isinstance(original_skills, list):
            for s in original_skills:
                if isinstance(s, str):
                    flat_skills.append(s)
                elif isinstance(s, dict):
                    flat_skills.extend([str(v) for v in s.values()])
        elif isinstance(original_skills, str):
            flat_skills = [original_skills]
        else:
            flat_skills = []

        logger.debug(f"[Enhance] Flattened skills type: {type(flat_skills)}, value: {flat_skills}")

        if not original_summary and not flat_skills:
            logger.warning("Resume has no summary or skills to enhance")
            return EnhancedResumeContent(
                enhanced_summary="",
                enhanced_skills=[],
                original_summary="",
                original_skills=[]
            )

        # Generate enhanced content via LLM (pass full resume for context)
        enhanced_summary, enhanced_skills = await self._call_llm_for_enhancement(
            resume_data=resume_data,
            original_summary=original_summary,
            original_skills=flat_skills,
            job_description=job_description,
            job_title=job_title,
            company=company
        )

        return EnhancedResumeContent(
            enhanced_summary=enhanced_summary,
            enhanced_skills=enhanced_skills,
            original_summary=original_summary,
            original_skills=flat_skills
        )
    
    async def _call_llm_for_enhancement(
        self,
        resume_data: Dict[str, Any],
        original_summary: str,
        original_skills: List[str],
        job_description: str,
        job_title: Optional[str] = None,
        company: Optional[str] = None
    ) -> Tuple[str, List[str]]:
        """
        Call OpenRouter LLM to enhance resume content.
        
        Args:
            resume_data: Full resume JSON with all sections for context
            original_summary: Current summary section
            original_skills: Current skills list
            job_description: Job description text
            job_title: Optional job title
            company: Optional company name
        
        Returns:
            Tuple of (enhanced_summary, enhanced_skills)
        """
        job_context = ""
        if job_title:
            job_context += f"Job Title: {job_title}\n"
        if company:
            job_context += f"Company: {company}\n"
        
        # Format the full resume context for the model
        resume_context = self._format_resume_context(resume_data)
        
        prompt = f"""You are an expert ATS (Applicant Tracking System) optimization specialist and resume writer.

Your task is to enhance ONLY the summary and skills sections of a resume to better align with a specific job description.

CRITICAL RULES:
1. Do NOT hallucinate or fabricate any experience, qualifications, or skills the candidate doesn't have
2. Do NOT add skills that aren't related to what the candidate already has
3. Only REWORD and ENHANCE existing content to better match job keywords
4. Preserve the truthfulness of the candidate's background
5. Use the FULL RESUME CONTEXT below to understand the candidate's REAL experience level and qualifications
6. DO NOT claim years of experience not supported by the actual work history
7. Focus on ATS keyword optimization and relevance
8. Make the summary more compelling while staying accurate
9. Reorganize skills to prioritize those mentioned in the job description

{job_context}

JOB DESCRIPTION:
{job_description[:3000]}

====================
FULL CANDIDATE RESUME (FOR CONTEXT - DO NOT MODIFY OTHER SECTIONS):
{resume_context}
====================

CURRENT SUMMARY TO ENHANCE:
{original_summary}

CURRENT SKILLS TO ENHANCE:
{', '.join(original_skills[:50])}

Provide your response in the following JSON format ONLY (no markdown, no explanations):
{{
    "enhanced_summary": "Your enhanced professional summary here (2-4 sentences, ATS-optimized, accurate to their actual experience)",
    "enhanced_skills": ["skill1", "skill2", "skill3", ...]
}}

Remember: 
- The enhanced summary MUST reflect the ACTUAL years of experience from their work history
- Incorporate relevant keywords from the JD naturally WITHOUT exaggerating qualifications
- Skills should be reordered to prioritize JD-relevant skills first
- You may slightly rephrase skills to match JD terminology (e.g., "Python" → "Python Programming")
- Do NOT add completely new skills the candidate doesn't have
- Keep the summary concise but impactful and TRUTHFUL"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://linkedin-easy-apply.com",
            "X-Title": "LinkedIn Resume Enhancement"
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"}
        }
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        self.api_url,
                        headers=headers,
                        json=payload
                    )
                    
                    if response.status_code == 429:
                        wait_time = 2 ** (attempt + 1)
                        logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                        import asyncio
                        await asyncio.sleep(wait_time)
                        continue
                    
                    response.raise_for_status()
                    
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    # Parse the JSON response
                    result = self._parse_enhancement_response(content)
                    
                    logger.info(f"Successfully enhanced resume - summary: {len(result[0])} chars, skills: {len(result[1])} items")
                    return result
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error during resume enhancement (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    raise
            except Exception as e:
                logger.error(f"Error during resume enhancement (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    raise
        
        # Fallback: return original content if all retries fail
        logger.warning("All enhancement attempts failed, returning original content")
        return original_summary, original_skills
    
    def _format_resume_context(self, resume_data: Dict[str, Any]) -> str:
        """
        Format the full resume data into a readable context for the LLM.
        
        Args:
            resume_data: Full resume JSON
            
        Returns:
            Formatted string with key resume sections
        """
        lines = []
        
        # Extract experience section
        experience_data = resume_data.get("experience", [])
        if isinstance(experience_data, dict) and "content" in experience_data:
            experience = experience_data["content"]
        else:
            experience = experience_data
        
        if experience and isinstance(experience, list):
            lines.append("PROFESSIONAL EXPERIENCE:")
            for exp in experience[:5]:  # Limit to 5 most recent
                if isinstance(exp, dict):
                    title = exp.get("title", exp.get("position", exp.get("role", "")))
                    company = exp.get("company", "")
                    dates = exp.get("dates", exp.get("duration", ""))
                    if title or company:
                        lines.append(f"  - {title} at {company} ({dates})")
            lines.append("")
        
        # Extract education section
        education_data = resume_data.get("education", [])
        if isinstance(education_data, dict) and "content" in education_data:
            education = education_data["content"]
        else:
            education = education_data
        
        if education and isinstance(education, list):
            lines.append("EDUCATION:")
            for edu in education[:3]:  # Limit to 3
                if isinstance(edu, dict):
                    degree = edu.get("degree", "")
                    institution = edu.get("institution", edu.get("school", ""))
                    dates = edu.get("dates", edu.get("year", ""))
                    if degree or institution:
                        lines.append(f"  - {degree} from {institution} ({dates})")
            lines.append("")
        
        # Extract projects section
        projects_data = resume_data.get("projects", [])
        if isinstance(projects_data, dict) and "content" in projects_data:
            projects = projects_data["content"]
        else:
            projects = projects_data
        
        if projects and isinstance(projects, list):
            lines.append("KEY PROJECTS:")
            for proj in projects[:3]:  # Limit to 3
                if isinstance(proj, dict):
                    name = proj.get("name", proj.get("title", proj.get("project_name", "")))
                    if name:
                        lines.append(f"  - {name}")
            lines.append("")
        
        # Extract certifications
        certifications_data = resume_data.get("certifications", [])
        if isinstance(certifications_data, dict) and "content" in certifications_data:
            certifications = certifications_data["content"]
        else:
            certifications = certifications_data
        
        if certifications and isinstance(certifications, list):
            lines.append("CERTIFICATIONS:")
            for cert in certifications[:3]:  # Limit to 3
                if isinstance(cert, str):
                    lines.append(f"  - {cert}")
                elif isinstance(cert, dict):
                    cert_name = cert.get("name", cert.get("title", ""))
                    if cert_name:
                        lines.append(f"  - {cert_name}")
            lines.append("")
        
        return "\n".join(lines) if lines else "No additional context available."
    
    def _parse_enhancement_response(self, content: str) -> Tuple[str, List[str]]:
        """
        Parse the LLM response to extract enhanced summary and skills.
        
        Args:
            content: Raw response content from LLM
            
        Returns:
            Tuple of (enhanced_summary, enhanced_skills)
        """
        try:
            # Clean up markdown code fences if present
            content = content.strip()
            if content.startswith("```"):
                lines = content.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
            
            # Parse JSON
            data = json.loads(content)
            
            enhanced_summary = data.get("enhanced_summary", "")
            enhanced_skills = data.get("enhanced_skills", [])
            
            # Validate and clean
            if not isinstance(enhanced_summary, str):
                enhanced_summary = str(enhanced_summary)
            
            if isinstance(enhanced_skills, str):
                enhanced_skills = [s.strip() for s in enhanced_skills.split(",") if s.strip()]
            elif not isinstance(enhanced_skills, list):
                enhanced_skills = []
            else:
                enhanced_skills = [str(s).strip() for s in enhanced_skills if s]
            
            return enhanced_summary, enhanced_skills
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse enhancement response as JSON: {e}")
            # Try regex extraction as fallback
            summary_match = re.search(r'"enhanced_summary"\s*:\s*"([^"]*)"', content)
            skills_match = re.search(r'"enhanced_skills"\s*:\s*\[([^\]]*)\]', content)
            
            summary = summary_match.group(1) if summary_match else ""
            skills_str = skills_match.group(1) if skills_match else ""
            skills = [s.strip().strip('"') for s in skills_str.split(",") if s.strip()]
            
            return summary, skills


def create_enhanced_resume_json(
    original_resume: Dict[str, Any],
    enhanced_content: EnhancedResumeContent,
    user_full_name: Optional[str] = None,
    user_email: Optional[str] = None,
    user_phone: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new resume JSON with enhanced summary and skills.
    
    This creates an IN-MEMORY copy - does NOT modify the original.
    
    Args:
        original_resume: The user's original resume JSON from database
        enhanced_content: The AI-enhanced summary and skills
        user_full_name: User's full name from user model (to ensure it's in PDF)
        user_email: User's email from user model (to ensure it's in PDF)
        user_phone: User's phone from user model (optional)
        
    Returns:
        New resume JSON with enhanced fields (ephemeral, not persisted)
    """
    import copy
    
    # Deep copy to ensure we don't modify the original
    enhanced_resume = copy.deepcopy(original_resume)
    
    # Log original resume structure for debugging
    logger.debug(f"Original resume keys: {list(original_resume.keys())}")
    logger.debug(f"Original basic_info: {original_resume.get('basic_info', 'NOT FOUND')}")
    
    # Replace summary with enhanced version
    if enhanced_content.enhanced_summary:
        enhanced_resume["summary"] = enhanced_content.enhanced_summary
    
    # Replace skills with enhanced version
    if enhanced_content.enhanced_skills:
        enhanced_resume["skills"] = enhanced_content.enhanced_skills
    
    # Ensure basic_info has user contact details (critical for PDF generation)
    # Initialize basic_info if not present
    if "basic_info" not in enhanced_resume:
        enhanced_resume["basic_info"] = {}
    
    # Get the original basic_info to preserve existing data
    original_basic_info = original_resume.get("basic_info", {})
    
    # Check for contact info in multiple locations:
    # 1. basic_info.contact (OpenRouter structure)
    # 2. contact at root level
    contact_in_basic = original_basic_info.get("contact", {})
    contact_at_root = original_resume.get("contact", {})
    
    # Determine if we're using nested structure
    has_nested_structure = "content" in enhanced_resume["basic_info"] and isinstance(enhanced_resume["basic_info"]["content"], dict)
    
    # Get or create the content dict
    if has_nested_structure:
        basic_content = enhanced_resume["basic_info"]["content"]
    else:
        # Create nested structure for consistency
        if not enhanced_resume["basic_info"] or not isinstance(enhanced_resume["basic_info"], dict):
            enhanced_resume["basic_info"] = {}
        
        # Check if original had nested structure
        if "content" in original_basic_info and isinstance(original_basic_info["content"], dict):
            # Preserve nested structure from original
            if "content" not in enhanced_resume["basic_info"]:
                enhanced_resume["basic_info"]["content"] = {}
            basic_content = enhanced_resume["basic_info"]["content"]
        else:
            # Use flat structure
            basic_content = enhanced_resume["basic_info"]
    
    # Extract existing contact info from original resume
    # Check multiple possible locations
    if "content" in original_basic_info and isinstance(original_basic_info["content"], dict):
        original_content = original_basic_info["content"]
    else:
        original_content = original_basic_info
    
    # Contact info might be in basic_info.contact
    contact_section = contact_in_basic if contact_in_basic else contact_at_root
    
    # Merge contact information (prioritize: original resume -> user model -> nothing)
    # Name
    if not basic_content.get("name") and not basic_content.get("full_name"):
        name_value = (
            original_content.get("name") or 
            original_content.get("full_name") or 
            user_full_name
        )
        if name_value:
            basic_content["name"] = name_value
            logger.debug(f"Set name in enhanced resume: {name_value}")
    
    # Email
    if not basic_content.get("email"):
        email_value = (
            original_content.get("email") or 
            contact_section.get("email") or 
            user_email
        )
        if email_value:
            basic_content["email"] = email_value
            logger.debug(f"Set email in enhanced resume: {email_value}")
    
    # Phone
    if not basic_content.get("phone") and not basic_content.get("phone_number"):
        phone_value = (
            original_content.get("phone") or 
            original_content.get("phone_number") or 
            contact_section.get("phone") or
            contact_section.get("phone_number") or
            user_phone
        )
        if phone_value:
            basic_content["phone"] = phone_value
            logger.debug(f"Set phone in enhanced resume: {phone_value}")
    
    # LinkedIn (from original resume)
    if not basic_content.get("linkedin") and not basic_content.get("linkedin_url"):
        linkedin_value = (
            original_content.get("linkedin") or 
            original_content.get("linkedin_url") or
            contact_section.get("linkedin") or
            contact_section.get("linkedin_url")
        )
        if linkedin_value:
            basic_content["linkedin"] = linkedin_value
            logger.debug(f"Set LinkedIn in enhanced resume: {linkedin_value}")
    
    # GitHub (from original resume)
    if not basic_content.get("github") and not basic_content.get("github_url"):
        github_value = (
            original_content.get("github") or 
            original_content.get("github_url") or
            contact_section.get("github") or
            contact_section.get("github_url")
        )
        if github_value:
            basic_content["github"] = github_value
            logger.debug(f"Set GitHub in enhanced resume: {github_value}")
    
    # Location (from original resume)
    if not basic_content.get("location"):
        location_value = (
            original_content.get("location") or 
            original_content.get("city") or
            contact_section.get("location") or
            contact_section.get("city")
        )
        if location_value:
            basic_content["location"] = location_value
            logger.debug(f"Set location in enhanced resume: {location_value}")
    
    # Log final contact info for debugging
    logger.info(f"Enhanced resume contact info - Name: {basic_content.get('name')}, Email: {basic_content.get('email')}, Phone: {basic_content.get('phone')}, LinkedIn: {basic_content.get('linkedin')}, GitHub: {basic_content.get('github')}")
    
    # Add metadata (useful for debugging, but not persisted)
    enhanced_resume["_enhancement_metadata"] = {
        "enhanced": True,
        "original_summary_length": len(enhanced_content.original_summary),
        "enhanced_summary_length": len(enhanced_content.enhanced_summary),
        "original_skills_count": len(enhanced_content.original_skills),
        "enhanced_skills_count": len(enhanced_content.enhanced_skills)
    }
    
    return enhanced_resume
