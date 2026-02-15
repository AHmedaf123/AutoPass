"""
Temporary Resume Generator Service
Creates ephemeral PDF/DOCX resumes from enhanced JSON data.
Files are NOT persisted to database and are cleaned up after use.
"""
import base64
import io
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
    from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("reportlab not available - PDF generation will be limited")


@dataclass
class TempResumeFile:
    """Container for temporary resume file information."""
    file_path: str
    file_base64: str
    format: str  # 'pdf' or 'docx'
    
    def cleanup(self) -> bool:
        """Remove the temporary file. Returns True if successful."""
        try:
            if os.path.exists(self.file_path):
                os.remove(self.file_path)
                logger.debug(f"Cleaned up temporary resume: {self.file_path}")
                return True
        except Exception as e:
            logger.warning(f"Failed to cleanup temp resume {self.file_path}: {e}")
        return False


class TempResumeGeneratorService:
    """
    Service for generating temporary resume files from JSON data.
    
    Key features:
    - Creates ATS-friendly PDF format
    - Generates ephemeral files (deleted after use)
    - No database persistence
    - LinkedIn-compatible layout
    """
    
    def __init__(self):
        """Initialize the resume generator service."""
        self.temp_dir = tempfile.gettempdir()
    
    def generate_temp_resume(
        self,
        resume_json: Dict[str, Any],
        format: str = "pdf"
    ) -> TempResumeFile:
        """
        Generate a temporary resume file from JSON data.
        
        Args:
            resume_json: Structured resume JSON data
            format: Output format ('pdf' or 'docx')
            
        Returns:
            TempResumeFile with path and base64 content
        """
        if format.lower() == "pdf":
            return self._generate_pdf(resume_json)
        else:
            raise ValueError(f"Unsupported format: {format}. Currently only 'pdf' is supported.")
    
    def _generate_pdf(self, resume_json: Dict[str, Any]) -> TempResumeFile:
        """
        Generate a PDF resume using reportlab.
        
        Args:
            resume_json: Structured resume JSON data
            
        Returns:
            TempResumeFile with PDF path and base64 content
        """
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError("reportlab is required for PDF generation. Install with: pip install reportlab")
        
        # Create temp file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".pdf",
            prefix=f"enhanced_resume_{timestamp}_",
            delete=False,
            dir=self.temp_dir
        )
        temp_path = temp_file.name
        temp_file.close()
        
        try:
            # Create PDF document
            doc = SimpleDocTemplate(
                temp_path,
                pagesize=letter,
                rightMargin=0.75*inch,
                leftMargin=0.75*inch,
                topMargin=0.75*inch,
                bottomMargin=0.75*inch
            )
            
            # Build content
            story = self._build_pdf_content(resume_json)
            
            # Generate PDF
            doc.build(story)
            
            # Read as base64
            with open(temp_path, "rb") as f:
                file_bytes = f.read()
                file_base64 = base64.b64encode(file_bytes).decode("utf-8")
            
            logger.info(f"Generated temporary enhanced resume PDF: {temp_path}")
            
            return TempResumeFile(
                file_path=temp_path,
                file_base64=file_base64,
                format="pdf"
            )
            
        except Exception as e:
            # Cleanup on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            logger.error(f"Failed to generate PDF resume: {e}")
            raise
    
    def _build_pdf_content(self, resume_json: Dict[str, Any]) -> List:
        """
        Build the PDF content from resume JSON.
        
        Args:
            resume_json: Structured resume data
            
        Returns:
            List of reportlab flowables
        """
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles for ATS optimization
        title_style = ParagraphStyle(
            'ResumeTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=4,
            alignment=TA_LEFT,  # Changed to LEFT to match test script
            textColor='#1a1a1a'
        )
        
        contact_style = ParagraphStyle(
            'ContactInfo',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=12,
            alignment=TA_LEFT,  # Changed to LEFT
            textColor='#333333'
        )
        
        section_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=12,
            spaceBefore=14,
            spaceAfter=6,
            textColor='#0066cc',
            borderWidth=0,
            borderPadding=0,
            borderColor='#0066cc'
        )
        
        body_style = ParagraphStyle(
            'BodyText',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=4,
            alignment=TA_JUSTIFY,
            leading=14
        )
        
        bullet_style = ParagraphStyle(
            'BulletText',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=3,
            leftIndent=15,
            leading=13
        )
        
        date_style = ParagraphStyle(
            'DateText',
            parent=body_style,
            fontSize=9,
            textColor='#666666'
        )
        
        # Basic Info / Header
        basic_info = resume_json.get("basic_info", {})
        
        # Handle multiple nested structures:
        # 1. basic_info.content.email (from enhanced resume)
        # 2. basic_info.contact.email (from OpenRouter parsing)
        # 3. basic_info.email (flat structure)
        if "content" in basic_info and isinstance(basic_info["content"], dict):
            basic_content = basic_info["content"]
            contact_info = basic_content
        elif "contact" in basic_info and isinstance(basic_info["contact"], dict):
            basic_content = basic_info
            contact_info = basic_info["contact"]
        else:
            basic_content = basic_info
            contact_info = basic_info
        
        # Extract contact details with multiple possible field names
        name = (
            basic_content.get("name") or 
            basic_content.get("full_name") or 
            f"{basic_content.get('first_name', '')} {basic_content.get('last_name', '')}".strip() or
            resume_json.get("name", "") or
            resume_json.get("full_name", "")
        )
        email = (
            contact_info.get("email") or 
            contact_info.get("email_address") or 
            basic_content.get("email") or
            resume_json.get("email", "")
        )
        phone = (
            contact_info.get("phone") or 
            contact_info.get("phone_number") or 
            basic_content.get("phone") or
            resume_json.get("phone", "")
        )
        location = (
            contact_info.get("location") or 
            contact_info.get("city") or 
            basic_content.get("location") or
            resume_json.get("location", "")
        )
        linkedin = (
            contact_info.get("linkedin") or 
            contact_info.get("linkedin_url") or 
            basic_content.get("linkedin") or
            resume_json.get("linkedin", "")
        )
        github = (
            contact_info.get("github") or 
            contact_info.get("github_url") or 
            basic_content.get("github") or
            resume_json.get("github", "")
        )
        
        # Debug logging
        logger.debug(f"PDF Generation - Contact Info: name={name}, email={email}, phone={phone}, location={location}, linkedin={linkedin}, github={github}")
        logger.debug(f"PDF Generation - basic_info structure: {basic_info}")
        
        if name:
            story.append(Paragraph(name.upper(), title_style))  # Uppercase like test script
        
        # Contact info - all in one centered row
        contact_parts = []
        if email:
            contact_parts.append(email)
        if phone:
            contact_parts.append(phone)
        if location:
            contact_parts.append(location)
        if linkedin:
            contact_parts.append(f"LinkedIn: {linkedin}")
        if github:
            contact_parts.append(f"GitHub: {github}")
        
        logger.debug(f"PDF Generation - Contact parts to add: {contact_parts}")
        
        if contact_parts:
            story.append(Paragraph(" | ".join(contact_parts), contact_style))
        else:
            logger.warning("No contact information found in resume JSON for PDF generation!")
        
        story.append(Spacer(1, 8))
        
        # Professional Summary
        summary_data = resume_json.get("summary", "")
        # Handle both flat and nested content structures
        if isinstance(summary_data, dict) and "content" in summary_data:
            summary = summary_data["content"]
        else:
            summary = summary_data
        
        if summary:
            story.append(Paragraph("PROFESSIONAL SUMMARY", section_style))
            story.append(Paragraph(summary, body_style))
        
        # Skills
        skills_data = resume_json.get("skills", [])
        # Handle both flat and nested content structures
        if isinstance(skills_data, dict) and "content" in skills_data:
            skills = skills_data["content"]
        else:
            skills = skills_data
        
        if skills:
            story.append(Paragraph("TECHNICAL SKILLS", section_style))
            if isinstance(skills, list):
                # Group skills in rows for better ATS readability
                skills_text = " • ".join(skills)  # Removed limit
                story.append(Paragraph(skills_text, body_style))
            elif isinstance(skills, dict):
                for category, skill_list in skills.items():
                    if isinstance(skill_list, list):
                        category_title = category.replace("_", " ").title()
                        story.append(Paragraph(f"<b>{category_title}:</b> {', '.join(skill_list)}", bullet_style))
        
        # Experience
        experience_data = resume_json.get("experience", [])
        # Handle both flat and nested content structures
        if isinstance(experience_data, dict) and "content" in experience_data:
            experience = experience_data["content"]
        else:
            experience = experience_data
        if experience:
            story.append(Paragraph("PROFESSIONAL EXPERIENCE", section_style))
            for exp in experience:
                if isinstance(exp, dict):
                    title = exp.get("title", exp.get("position", ""))
                    company = exp.get("company", "")
                    location = exp.get("location", "")
                    dates = exp.get("dates", "")
                    
                    # Job header
                    header = f"<b>{title}</b>"
                    if company:
                        header += f" | {company}"
                    if location:
                        header += f" | {location}"
                    story.append(Paragraph(header, body_style))
                    
                    if dates:
                        story.append(Paragraph(dates, date_style))
                    
                    # Achievements
                    achievements = exp.get("achievements", exp.get("description", []))
                    if achievements:
                        if isinstance(achievements, list):
                            for ach in achievements:  # Removed limit
                                story.append(Paragraph(f"• {ach}", bullet_style))
                        else:
                            story.append(Paragraph(f"• {achievements}", bullet_style))
        
        # Education
        education_data = resume_json.get("education", [])
        # Handle both flat and nested content structures
        if isinstance(education_data, dict) and "content" in education_data:
            education = education_data["content"]
        else:
            education = education_data
        
        if education:
            story.append(Paragraph("EDUCATION", section_style))
            for edu in education:
                if isinstance(edu, dict):
                    degree = edu.get("degree", "")
                    institution = edu.get("institution", "")
                    dates = edu.get("dates", "")
                    gpa = edu.get("gpa", "")
                    
                    edu_line = f"<b>{degree}</b>"
                    if institution:
                        edu_line += f" - {institution}"
                    if dates:
                        edu_line += f" ({dates})"
                    story.append(Paragraph(edu_line, body_style))
                    if gpa:
                        story.append(Paragraph(f"GPA: {gpa}", bullet_style))
        
        # Projects
        projects_data = resume_json.get("projects", [])
        # Handle both flat and nested content structures
        if isinstance(projects_data, dict) and "content" in projects_data:
            projects = projects_data["content"]
        else:
            projects = projects_data
        
        if projects:
            story.append(Paragraph("KEY PROJECTS", section_style))
            for proj in projects:  # Removed limit
                if isinstance(proj, dict):
                    name = proj.get("name", proj.get("title", ""))
                    description = proj.get("description", "")
                    link = proj.get("link", proj.get("url", proj.get("github", "")))
                    technologies = proj.get("technologies", proj.get("tech_stack", []))
                    
                    if name:
                        # Build project line with name and description
                        proj_text = f"<b>{name}</b>"
                        if description:
                            proj_text += f": {description}"
                        story.append(Paragraph(proj_text, bullet_style))
                        
                        # Add link if available
                        if link:
                            story.append(Paragraph(f"  🔗 {link}", bullet_style))
                        
                        # Add technologies if available
                        if technologies:
                            if isinstance(technologies, list):
                                tech_str = ", ".join(technologies)
                            else:
                                tech_str = str(technologies)
                            story.append(Paragraph(f"  Technologies: {tech_str}", bullet_style))
        
        # Certifications
        certifications_data = resume_json.get("certifications", [])
        # Handle both flat and nested content structures
        if isinstance(certifications_data, dict) and "content" in certifications_data:
            certifications = certifications_data["content"]
        else:
            certifications = certifications_data
        
        if certifications:
            story.append(Paragraph("CERTIFICATIONS", section_style))
            for cert in certifications:
                if isinstance(cert, str):
                    story.append(Paragraph(f"• {cert}", bullet_style))
                elif isinstance(cert, dict):
                    cert_name = cert.get("name", "")
                    story.append(Paragraph(f"• {cert_name}", bullet_style))
        
        # Languages (if present)
        languages_data = resume_json.get("languages", [])
        
        # Handle both flat and nested content structures
        if isinstance(languages_data, dict) and "content" in languages_data:
            languages = languages_data["content"]
        else:
            languages = languages_data
        
        if languages and len(languages) > 0:
            story.append(Paragraph("LANGUAGES", section_style))
            if isinstance(languages, list):
                lang_items = []
                for lang in languages:
                    if isinstance(lang, str):
                        lang_items.append(lang)
                    elif isinstance(lang, dict):
                        # Try multiple possible field names
                        name = lang.get("name") or lang.get("language") or ""
                        level = lang.get("level") or lang.get("proficiency") or ""
                        if name:
                            lang_items.append(f"{name}" + (f" ({level})" if level else ""))
                if lang_items:
                    story.append(Paragraph(" • ".join(lang_items), body_style))
        
        return story
    
    def generate_resume_text(self, resume_json: Dict[str, Any]) -> str:
        """
        Generate plain text representation of resume for AI form filling.
        
        Args:
            resume_json: Structured resume JSON data
            
        Returns:
            Plain text resume content
        """
        lines = []
        
        # Basic Info
        basic_info = resume_json.get("basic_info", {})
        
        # Handle both flat and nested content structures
        if "content" in basic_info and isinstance(basic_info["content"], dict):
            basic_content = basic_info["content"]
        else:
            basic_content = basic_info
        
        name = (
            basic_content.get("name") or 
            basic_content.get("full_name") or 
            f"{basic_content.get('first_name', '')} {basic_content.get('last_name', '')}".strip() or
            resume_json.get("name", "")
        )
        email = basic_content.get("email") or basic_content.get("email_address") or resume_json.get("email", "")
        phone = basic_content.get("phone") or basic_content.get("phone_number") or resume_json.get("phone", "")
        location = basic_content.get("location") or basic_content.get("city") or resume_json.get("location", "")
        
        if name:
            lines.append(f"Name: {name}")
        if email:
            lines.append(f"Email: {email}")
        if phone:
            lines.append(f"Phone: {phone}")
        if location:
            lines.append(f"Location: {location}")
        lines.append("")
        
        # Summary
        summary = resume_json.get("summary", "")
        if summary:
            lines.append("Summary:")
            lines.append(summary)
            lines.append("")
        
        # Experience
        experience = resume_json.get("experience", [])
        if experience:
            lines.append("Experience:")
            for exp in experience:
                if isinstance(exp, dict):
                    title = exp.get("title", exp.get("position", ""))
                    company = exp.get("company", "")
                    description = exp.get("description", "")
                    
                    lines.append(f"- {title} at {company}")
                    if description:
                        if isinstance(description, list):
                            for item in description:
                                lines.append(f"  {item}")
                        else:
                            lines.append(f"  {description}")
            lines.append("")
        
        # Education
        education = resume_json.get("education", [])
        if education:
            lines.append("Education:")
            for edu in education:
                if isinstance(edu, dict):
                    degree = edu.get("degree", "")
                    institution = edu.get("institution", "")
                    lines.append(f"- {degree} from {institution}")
            lines.append("")
        
        # Projects
        projects = resume_json.get("projects", [])
        if projects:
            lines.append("Projects:")
            for proj in projects:
                if isinstance(proj, dict):
                    name = proj.get("name", proj.get("title", ""))
                    description = proj.get("description", "")
                    link = proj.get("link", proj.get("url", proj.get("github", "")))
                    technologies = proj.get("technologies", proj.get("tech_stack", []))
                    
                    if name:
                        lines.append(f"- {name}")
                        if description:
                            lines.append(f"  {description}")
                        if link:
                            lines.append(f"  Link: {link}")
                        if technologies:
                            if isinstance(technologies, list):
                                lines.append(f"  Technologies: {', '.join(technologies)}")
                            else:
                                lines.append(f"  Technologies: {technologies}")
            lines.append("")
        
        # Skills
        skills = resume_json.get("skills", [])
        if skills:
            if isinstance(skills, list):
                lines.append(f"Skills: {', '.join(skills)}")
            else:
                lines.append(f"Skills: {skills}")
        
        return "\n".join(lines)


# Utility function for easy cleanup
def cleanup_temp_resume(temp_file: TempResumeFile) -> None:
    """
    Cleanup utility to remove temporary resume file.
    
    Args:
        temp_file: TempResumeFile to cleanup
    """
    if temp_file:
        temp_file.cleanup()
