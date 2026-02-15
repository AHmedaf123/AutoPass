"""
Form Answer Generator
AI-powered answer generation for LinkedIn Easy Apply forms
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass
import httpx
from loguru import logger

from core.config import settings


@dataclass
class FormAnswerContext:
    """Context for generating form answers"""
    job_title: str
    company: str
    job_description: str
    user_name: str
    user_email: str
    resume_summary: str
    skills: list
    experience: list
    education: list
    

class FormAnswerGenerator:
    """
    AI-powered form answer generator using OpenRouter LLM.
    
    Generates contextual answers for LinkedIn Easy Apply forms including:
    - Cover letters
    - Headlines
    - Custom question responses
    """
    
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    MODEL = "gpt-4o-mini"
    
    def __init__(self):
        """Initialize form answer generator"""
        self.api_key = getattr(settings, 'OPENROUTER_API_KEY', None)
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not set - AI form generation will fail")
    
    async def _call_llm(self, prompt: str, max_tokens: int = 500) -> str:
        """
        Call OpenRouter LLM API
        
        Args:
            prompt: The prompt to send
            max_tokens: Maximum tokens in response
            
        Returns:
            Generated text response
        """
        if not self.api_key:
            logger.error("Cannot call LLM - API key not configured")
            return ""
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.OPENROUTER_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a professional career assistant helping with job applications. Be concise, professional, and positive."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.7,
                        "max_tokens": max_tokens
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
        
        except Exception as e:
            logger.error(f"Error calling OpenRouter LLM: {e}")
            return ""
    
    async def generate_cover_letter(
        self,
        context: FormAnswerContext
    ) -> str:
        """
        Generate a tailored cover letter for a specific job.
        
        Args:
            context: Form answer context with job and user details
            
        Returns:
            Generated cover letter (150-250 words)
        """
        prompt = f"""Write a professional cover letter for this job application:

Job: {context.job_title} at {context.company}
Job Description: {context.job_description[:800]}

Candidate:
- Name: {context.user_name}
- Skills: {', '.join(context.skills[:10])}
- Summary: {context.resume_summary}
- Recent Experience: {context.experience[0] if context.experience else 'Not specified'}

Requirements:
- 150-250 words maximum
- Professional but personable tone
- Highlight 2-3 relevant skills/experiences
- Show enthusiasm for the role
- Do NOT include [brackets] or placeholders
- Start with "Dear Hiring Manager," and end with the candidate's name
"""
        result = await self._call_llm(prompt, max_tokens=400)
        return result if result else self._default_cover_letter(context)
    
    async def generate_headline(
        self,
        context: FormAnswerContext
    ) -> str:
        """
        Generate a professional headline from resume.
        
        Args:
            context: Form answer context
            
        Returns:
            Professional headline (e.g., "Senior Python Developer | 5+ Years | FastAPI & AWS")
        """
        prompt = f"""Create a professional LinkedIn-style headline for a job applicant:

Skills: {', '.join(context.skills[:8])}
Summary: {context.resume_summary}
Experience: {context.experience[0] if context.experience else 'Entry-level professional'}

Requirements:
- Maximum 120 characters
- Format: "[Title] | [Years] Experience | [Top 2-3 Skills]"
- Professional and impactful
- No quotes or special formatting
"""
        result = await self._call_llm(prompt, max_tokens=50)
        return result if result else f"{context.skills[0]} Professional" if context.skills else "Experienced Professional"
    
    async def generate_summary(
        self,
        context: FormAnswerContext
    ) -> str:
        """
        Generate a professional summary (2-3 sentences) in first person.
        
        Args:
            context: Form answer context
            
        Returns:
            Professional summary written by the applicant
        """
        prompt = f"""Write a brief professional summary FOR the job applicant (in first person, as if they are writing it).

Skills: {', '.join(context.skills[:10])}
Summary: {context.resume_summary}
Experience: {', '.join(str(e) for e in context.experience[:2])}

Requirements:
- 2-3 sentences only
- MUST be written in first person (use "I", "my", "me")
- Highlight key strengths
- Professional and personable tone
- Sound like the actual applicant wrote this, not a third party
- Be authentic and direct
"""
        result = await self._call_llm(prompt, max_tokens=150)
        return result if result else context.resume_summary
    
    async def answer_custom_question(
        self,
        question: str,
        context: FormAnswerContext
    ) -> str:
        """
        Answer any custom application question using context.
        
        Args:
            question: The question to answer
            context: Form answer context
            
        Returns:
            Contextual answer
        """
        prompt = f"""Answer this job application question:

Question: "{question}"

Context:
- Applying for: {context.job_title} at {context.company}
- Candidate skills: {', '.join(context.skills[:8])}
- Experience summary: {context.resume_summary}

Requirements:
- Concise answer (1-3 sentences unless essay is implied)
- Professional tone
- Be specific and positive
- If question is about salary, say "Open to discussion based on total compensation"
- If question is about availability, say "Available to start within 2 weeks"
- If question asks Yes/No about qualifications, answer "Yes" unless clearly unqualified
"""
        result = await self._call_llm(prompt, max_tokens=200)
        return result if result else self._default_question_answer(question)
    
    async def answer_experience_years(
        self,
        skill_or_role: str,
        resume_experience: list
    ) -> str:
        """
        Calculate years of experience for a skill/role from resume.
        
        Args:
            skill_or_role: The skill or role being asked about
            resume_experience: List of experience entries
            
        Returns:
            Years as string (e.g., "5")
        """
        # Simple heuristic - count total years from experience entries
        total_years = 0
        for exp in resume_experience:
            years = exp.get("duration_years", 0)
            if isinstance(years, (int, float)):
                total_years += years
        
        # Default to 2 if no data
        return str(max(int(total_years), 2))
    
    def _default_cover_letter(self, context: FormAnswerContext) -> str:
        """Fallback cover letter template"""
        return f"""Dear Hiring Manager,

I am excited to apply for the {context.job_title} position at {context.company}. With my background in {', '.join(context.skills[:3]) if context.skills else 'relevant technologies'}, I am confident in my ability to contribute to your team.

{context.resume_summary}

I look forward to the opportunity to discuss how my skills and experience align with your needs.

Best regards,
{context.user_name}
"""
    
    def _default_question_answer(self, question: str) -> str:
        """Fallback answer for custom questions"""
        question_lower = question.lower()
        
        if "salary" in question_lower or "compensation" in question_lower:
            return "Open to discussion based on total compensation package"
        elif "start" in question_lower or "available" in question_lower:
            return "Available to start within 2 weeks"
        elif "sponsorship" in question_lower or "visa" in question_lower:
            return "I am authorized to work in this location"
        elif "relocate" in question_lower:
            return "Open to relocation for the right opportunity"
        else:
            return "Yes, I am qualified for this opportunity"
    
    async def batch_answer_questions(
        self,
        questions: list,
        resume_context: str,
        job_title: str,
        job_company: str,
        user_preferences: Optional[Dict[str, Any]] = None
    ) -> dict:
        """
        Answer ALL questions in ONE LLM call - 80% cost reduction.
        
        Args:
            questions: List of question strings
            resume_context: Compressed resume context (from ResumeContextManager)
            job_title: Job title being applied for
            job_company: Company name
            user_preferences: User preferences dict with current_salary, desired_salary, etc.
            
        Returns:
            Dict mapping question index to answer
        """
        if not questions:
            return {}
        
        user_preferences = user_preferences or {}
        
        # Format questions with numbers
        questions_text = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        
        # Build salary context from preferences
        salary_context = ""
        if user_preferences.get("current_salary"):
            salary_context += f"\n- Current Salary: ${user_preferences['current_salary']:,}"
        if user_preferences.get("desired_salary"):
            salary_context += f"\n- Desired Salary: ${user_preferences['desired_salary']:,}"
        if user_preferences.get("gender"):
            salary_context += f"\n- Gender: {user_preferences['gender']}"
        if user_preferences.get("location"):
            salary_context += f"\n- Location: {user_preferences['location']}"
        
        prompt = f"""You are filling out a job application form.

JOB: {job_title} at {job_company}

QUESTIONS TO ANSWER:
{questions_text}

RESUME CONTEXT:
{resume_context}{salary_context}

INSTRUCTIONS:
- Answer each question based on the resume context and user preferences
- Keep answers SHORT (1-2 sentences max)
- For salary questions: Use the provided salary values if available
  * If current salary asked: Use "Current Salary: $X" or "$X"
  * If desired/expected salary asked: Use "Desired Salary: $X" or "$X"
  * If no salary preference provided: "Open to discussion based on total compensation"
- For gender questions: Use the gender preference if available (Male/Female/Other)
- For location questions: Use the location preference if available
- For availability: "Available within 2 weeks"
- For yes/no questions about qualifications: "Yes" unless clearly unqualified
- For experience years: give a number only

Return JSON only: {{"1": "answer1", "2": "answer2", ...}}
No explanations, just the JSON object."""

        result = await self._call_llm(prompt, max_tokens=len(questions) * 60)
        
        if not result:
            # Fallback to individual default answers
            return {str(i+1): self._default_question_answer(q) for i, q in enumerate(questions)}
        
        try:
            import json
            import re
            
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                answers = json.loads(json_match.group())
                logger.info(f"Batch answered {len(answers)}/{len(questions)} questions")
                return answers
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse batch answers: {e}")
        
        # Fallback
        return {str(i+1): self._default_question_answer(q) for i, q in enumerate(questions)}


# Field pattern detection for form filling
FIELD_PATTERNS = {
    # Contact
    "name": ["name", "full name", "your name", "candidate name"],
    "email": ["email", "e-mail", "email address", "your email"],
    "phone": ["phone", "mobile", "contact number", "telephone"],
    "linkedin": ["linkedin", "profile url", "linkedin url"],
    
    # Experience
    "years_experience": ["years of experience", "how many years", "experience in", "years experience"],
    "current_title": ["current title", "job title", "current role", "current position"],
    "current_company": ["current company", "employer", "current employer", "organization"],
    
    # Education
    "degree": ["degree", "education level", "highest education", "qualification"],
    "school": ["school", "university", "college", "institution"],
    "gpa": ["gpa", "grade point", "academic score"],
    
    # Work preferences
    "salary": ["salary", "compensation", "pay", "expected salary", "salary expectation"],
    "start_date": ["start date", "availability", "when can you start", "earliest start"],
    "relocation": ["relocate", "relocation", "willing to move", "open to relocation"],
    "remote": ["remote", "work from home", "hybrid", "remote work"],
    "sponsorship": ["visa", "sponsorship", "work authorization", "legally authorized", "authorized to work"],
    
    # Long-form
    "cover_letter": ["cover letter", "letter of interest", "introduction letter"],
    "headline": ["headline", "professional headline", "tagline"],
    "summary": ["summary", "about yourself", "tell us about", "describe yourself", "professional summary"],
    "why_interested": ["why are you interested", "why this role", "why apply", "interest in this position"],
    "strengths": ["strengths", "what makes you", "why should we hire", "unique qualifications"],
}


def detect_field_type(label: str) -> Optional[str]:
    """
    Detect the field type from a form label.
    
    Args:
        label: The form field label text
        
    Returns:
        Field type key if detected, None otherwise
    """
    label_lower = label.lower().strip()
    
    for field_type, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            if pattern in label_lower:
                return field_type
    
    return None
