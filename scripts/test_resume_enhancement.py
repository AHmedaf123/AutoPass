"""
Test Script: Resume Enhancement with PDF Generation
Fetches job JD, enhances resume, and generates both original and enhanced PDFs
"""
import asyncio
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env from backend directory
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Configuration
USER_ID = "80ab4bc5-0d49-48e2-8786-a8f2e07056cb"
JOB_ID = "a99aac04-a892-44a0-9076-9538ed5ffa38"
DATABASE_URL = "postgresql+asyncpg://postgres:itechgemini@localhost:5433/jobapplier"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def fetch_job_description(session: AsyncSession, job_id: str) -> dict:
    """Fetch job details from database"""
    result = await session.execute(
        text(f"SELECT id, title, company, description FROM job_listings WHERE id = '{job_id}'")
    )
    row = result.fetchone()
    if row:
        return {
            "id": str(row[0]),
            "title": row[1],
            "company": row[2],
            "description": row[3]
        }
    return None


async def fetch_user_resume(session: AsyncSession, user_id: str) -> dict:
    """Fetch user resume data from database"""
    result = await session.execute(
        text(f"SELECT id, full_name, email, resume_parsed_data FROM users WHERE id = '{user_id}'")
    )
    row = result.fetchone()
    if row:
        import json
        resume_data = row[3]
        if isinstance(resume_data, str):
            resume_data = json.loads(resume_data)
        return {
            "id": str(row[0]),
            "full_name": row[1],
            "email": str(row[2]),
            "resume_data": resume_data
        }
    return None


async def enhance_resume_with_ai(resume_data: dict, job_description: str, job_title: str, company: str) -> dict:
    """Call OpenRouter to enhance resume summary and skills"""
    import httpx
    import json
    
    openrouter_key = OPENROUTER_API_KEY
    if not openrouter_key:
        raise ValueError("OpenRouter API key not configured")
    
    original_summary = resume_data.get("summary", "") or ""
    original_skills = resume_data.get("skills", []) or []

    # Robustly flatten/convert skills to a list of strings for prompt
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

    skills_for_prompt = ', '.join(flat_skills[:50])

    prompt = f"""You are an expert ATS (Applicant Tracking System) optimization specialist and resume writer.

Your task is to enhance ONLY the summary and skills sections of a resume to better align with a specific job description.

CRITICAL RULES:
1. Do NOT hallucinate or fabricate any experience, qualifications, or skills the candidate doesn't have
2. Do NOT add skills that aren't related to what the candidate already has
3. Only REWORD and ENHANCE existing content to better match job keywords
4. Preserve the truthfulness of the candidate's background
5. Focus on ATS keyword optimization and relevance
6. Make the summary more compelling while staying accurate
7. Reorganize skills to prioritize those mentioned in the job description

Job Title: {job_title}
Company: {company}

JOB DESCRIPTION:
{job_description[:4000]}

CANDIDATE'S CURRENT SUMMARY:
{original_summary}

CANDIDATE'S CURRENT SKILLS:
{skills_for_prompt}

Provide your response in the following JSON format ONLY (no markdown, no explanations):
{{
    "enhanced_summary": "Your enhanced professional summary here (2-4 sentences, ATS-optimized)",
    "enhanced_skills": ["skill1", "skill2", "skill3", ...]
}}

Remember: 
- The enhanced summary should incorporate relevant keywords from the JD naturally
- Skills should be reordered to prioritize JD-relevant skills first
- Do NOT add completely new skills the candidate doesn't have
- Keep the summary concise but impactful"""

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 2000,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        data = response.json()
        content_text = data["choices"][0]["message"]["content"]
        
        # Parse JSON response
        import re
        content_text = content_text.strip()
        if content_text.startswith("```"):
            lines = content_text.splitlines()
            lines = lines[1:-1] if lines[-1].startswith("```") else lines[1:]
            content_text = "\n".join(lines)
        
        return json.loads(content_text)


def generate_ats_pdf(resume_data: dict, full_name: str, email: str, output_path: str, is_enhanced: bool = False):
    """Generate ATS-friendly PDF resume"""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER
    from reportlab.lib.colors import HexColor
    
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.6*inch,
        leftMargin=0.6*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles for ATS optimization
    title_style = ParagraphStyle(
        'ResumeTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=4,
        alignment=TA_CENTER,
        textColor=HexColor('#1a1a1a')
    )
    
    contact_style = ParagraphStyle(
        'ContactInfo',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=12,
        alignment=TA_CENTER,
        textColor=HexColor('#333333')
    )
    
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=12,
        spaceBefore=14,
        spaceAfter=6,
        textColor=HexColor('#0066cc'),
        borderWidth=0,
        borderPadding=0,
        borderColor=HexColor('#0066cc')
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
    
    story = []
    
    # Header
    basic_info = resume_data.get("basic_info", {})
    name = basic_info.get("name", full_name) or full_name
    story.append(Paragraph(name.upper(), title_style))
    
    # Contact info - all in one centered row
    contact = basic_info.get("contact", {})
    user_email = contact.get("email", email) or email
    phone = contact.get("phone", "")
    linkedin = contact.get("linkedin", "")
    github = contact.get("github", "")
    
    contact_parts = []
    if user_email:
        contact_parts.append(user_email)
    if phone:
        contact_parts.append(phone)
    if linkedin:
        contact_parts.append(f"LinkedIn: {linkedin}")
    if github:
        contact_parts.append(f"GitHub: {github}")
    
    if contact_parts:
        story.append(Paragraph(" | ".join(contact_parts), contact_style))
    
    story.append(Spacer(1, 8))
    
    # Professional Summary
    summary = resume_data.get("summary", "")
    if summary:
        story.append(Paragraph("PROFESSIONAL SUMMARY", section_style))
        story.append(Paragraph(summary, body_style))
    
    # Skills
    skills = resume_data.get("skills", [])
    if skills:
        story.append(Paragraph("TECHNICAL SKILLS", section_style))
        if isinstance(skills, list):
            # Group skills in rows for better ATS readability
            skills_text = " • ".join(skills[:20])
            story.append(Paragraph(skills_text, body_style))
        elif isinstance(skills, dict):
            for category, skill_list in skills.items():
                if isinstance(skill_list, list):
                    category_title = category.replace("_", " ").title()
                    story.append(Paragraph(f"<b>{category_title}:</b> {', '.join(skill_list)}", bullet_style))
    
    # Experience
    experience = resume_data.get("experience", [])
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
                    date_style = ParagraphStyle('DateText', parent=body_style, fontSize=9, textColor=HexColor('#666666'))
                    story.append(Paragraph(dates, date_style))
                
                # Achievements
                achievements = exp.get("achievements", exp.get("description", []))
                if achievements:
                    if isinstance(achievements, list):
                        for ach in achievements[:5]:  # Limit to 5 bullets
                            story.append(Paragraph(f"• {ach}", bullet_style))
                    else:
                        story.append(Paragraph(f"• {achievements}", bullet_style))
                
                story.append(Spacer(1, 6))
    
    # Education
    education = resume_data.get("education", [])
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
    projects = resume_data.get("projects", [])
    if projects:
        story.append(Paragraph("KEY PROJECTS", section_style))
        for proj in projects[:4]:  # Limit to 4 projects
            if isinstance(proj, dict):
                name = proj.get("name", proj.get("title", ""))
                description = proj.get("description", "")
                if name:
                    story.append(Paragraph(f"<b>{name}</b>: {description}", bullet_style))
    
    # Certifications
    certifications = resume_data.get("certifications", [])
    if certifications:
        story.append(Paragraph("CERTIFICATIONS", section_style))
        for cert in certifications:
            if isinstance(cert, str):
                story.append(Paragraph(f"• {cert}", bullet_style))
            elif isinstance(cert, dict):
                cert_name = cert.get("name", "")
                story.append(Paragraph(f"• {cert_name}", bullet_style))
    
    # Build PDF
    doc.build(story)
    print(f"✅ Generated: {output_path}")


async def main():
    print("=" * 60)
    print("RESUME ENHANCEMENT & PDF GENERATION TEST")
    print("=" * 60)
    
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 1. Fetch Job Description
        print("\n📋 Fetching Job Description...")
        job = await fetch_job_description(session, JOB_ID)
        if not job:
            print(f"❌ Job not found: {JOB_ID}")
            return
        
        print(f"   Job Title: {job['title']}")
        print(f"   Company: {job['company']}")
        print(f"   Description Length: {len(job['description'] or '')} chars")
        
        # 2. Fetch User Resume
        print("\n👤 Fetching User Resume...")
        user = await fetch_user_resume(session, USER_ID)
        if not user:
            print(f"❌ User not found: {USER_ID}")
            return
        
        print(f"   Name: {user['full_name']}")
        print(f"   Email: {user['email']}")
        
        original_resume = user['resume_data']
        original_summary = original_resume.get("summary", "")
        original_skills = original_resume.get("skills", [])
        
        print(f"   Original Summary: {len(original_summary)} chars")
        print(f"   Original Skills: {type(original_skills).__name__}")
        
        # 3. Enhance Resume with AI
        print("\n🤖 Enhancing Resume with AI...")
        try:
            enhancement = await enhance_resume_with_ai(
                original_resume,
                job['description'],
                job['title'],
                job['company']
            )
            print(f"   Enhanced Summary: {len(enhancement.get('enhanced_summary', ''))} chars")
            print(f"   Enhanced Skills: {len(enhancement.get('enhanced_skills', []))} items")
        except Exception as e:
            print(f"❌ Enhancement failed: {e}")
            return
        
        # 4. Create Enhanced Resume
        import copy
        enhanced_resume = copy.deepcopy(original_resume)
        enhanced_resume["summary"] = enhancement["enhanced_summary"]
        enhanced_resume["skills"] = enhancement["enhanced_skills"]
        
        # 5. Generate PDFs
        print("\n📄 Generating PDF Resumes...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Original Resume PDF
        original_pdf_path = os.path.join(OUTPUT_DIR, f"original_resume_{timestamp}.pdf")
        generate_ats_pdf(original_resume, user['full_name'], user['email'], original_pdf_path, is_enhanced=False)
        
        # Enhanced Resume PDF
        enhanced_pdf_path = os.path.join(OUTPUT_DIR, f"enhanced_resume_ATS_{timestamp}.pdf")
        generate_ats_pdf(enhanced_resume, user['full_name'], user['email'], enhanced_pdf_path, is_enhanced=True)
        
        # 6. Summary
        print("\n" + "=" * 60)
        print("✅ GENERATION COMPLETE!")
        print("=" * 60)
        print(f"\n📁 Output Directory: {OUTPUT_DIR}")
        print(f"\n📄 Original Resume: {os.path.basename(original_pdf_path)}")
        print(f"📄 Enhanced Resume (ATS): {os.path.basename(enhanced_pdf_path)}")
        
        print("\n📊 Enhancement Summary:")
        print(f"   Job: {job['title']} at {job['company']}")
        print(f"   Summary: {len(original_summary)} → {len(enhancement['enhanced_summary'])} chars")
        
        # Flatten original skills for count
        if isinstance(original_skills, dict):
            flat_count = sum(len(v) if isinstance(v, list) else 1 for v in original_skills.values())
        elif isinstance(original_skills, list):
            flat_count = len(original_skills)
        else:
            flat_count = 1
        
        print(f"   Skills: {flat_count} → {len(enhancement['enhanced_skills'])} items")
        
        print("\n🎯 Enhanced Summary Preview:")
        print(f"   {enhancement['enhanced_summary'][:200]}...")
        
        print("\n🛠️ Top Enhanced Skills:")
        for skill in enhancement['enhanced_skills'][:10]:
            print(f"   • {skill}")


if __name__ == "__main__":
    asyncio.run(main())
