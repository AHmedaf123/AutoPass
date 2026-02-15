"""Resume Endpoints (OpenRouter-based parsing)

Two endpoints:

1. POST /resume/upload-parse
	- Accepts a PDF resume and UID (user id).
	- Extracts text from the PDF and sends it to an OpenRouter LLM.
	- Saves the structured JSON returned by the model on the user record.
	- Returns the UID and the JSON structure.

2. POST /resume/json
	- Accepts a UID and a JSON resume structure directly in the body.
	- Saves the JSON on the user record in the database.
	- Returns the UID and the stored JSON structure.
"""

from dataclasses import replace
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import base64
import copy
import io
import json
import re

import pdfplumber
import httpx
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from loguru import logger
from pydantic import BaseModel

from application.repositories.interfaces import IUserRepository
from core.config import settings
from infrastructure.external.file_storage_service import LocalFileStorageService
from presentation.api.v1.container import get_user_repository


router = APIRouter()


class ResumeJsonResponse(BaseModel):
	"""Response containing the stored resume JSON and user id."""

	user_id: str
	resume_data: Dict[str, Any]


class ResumeJsonRequest(BaseModel):
	"""Request model for directly providing resume JSON for a user."""

	uid: str
	resume_data: Dict[str, Any]


class EnhanceResumeRequest(BaseModel):
	"""Request model for enhancing resume based on job description."""

	uid: str
	job_description: str
	job_title: Optional[str] = None
	company: Optional[str] = None


class EnhancedResumeResponse(BaseModel):
	"""Response containing both original and enhanced resumes."""

	user_id: str
	original_resume: Dict[str, Any]
	enhanced_resume: Dict[str, Any]
	original_resume_text: str
	enhanced_resume_text: str
	enhancement_summary: Dict[str, Any]



def _extract_json_from_text(text: str) -> Dict[str, Any]:
	"""Best-effort extraction of a JSON object from model output.

	Handles cases where the model wraps JSON in markdown code fences
	or adds brief explanations around the JSON.
	"""
	text = text.strip()
	if not text:
		raise ValueError("Empty response content from OpenRouter")

	# Strip markdown code fences if present
	if text.startswith("```"):
		lines = text.splitlines()
		if lines and lines[0].startswith("```"):
			lines = lines[1:]
		if lines and lines[-1].startswith("```"):
			lines = lines[:-1]
		text = "\n".join(lines).strip()

	def _parse_with_repairs(raw: str) -> Dict[str, Any]:
		"""Try to parse JSON, repairing common issues like trailing commas and truncation."""
		def attempt_parse(s: str) -> Dict[str, Any]:
			try:
				return json.loads(s)
			except json.JSONDecodeError:
				# Remove trailing commas before closing } or ]
				cleaned = re.sub(r",\s*([}\]])", r"\1", s)
				if cleaned != s:
					return json.loads(cleaned)
				raise

		try:
			return attempt_parse(raw)
		except json.JSONDecodeError as e:
			# Handle truncated responses: close open strings and brackets
			if "Unterminated string" in str(e):
				# Find last complete line and close JSON
				lines = raw.rstrip().rsplit("\n", 1)
				if len(lines) == 2:
					truncated = lines[0]
				else:
					truncated = raw.rstrip()
				# Count unclosed brackets
				open_braces = truncated.count("{") - truncated.count("}")
				open_brackets = truncated.count("[") - truncated.count("]")
				# Close any open string (remove trailing incomplete value)
				if truncated.rstrip().endswith('"'):
					truncated = truncated.rstrip()[:-1].rstrip().rstrip(",")
				else:
					# Remove incomplete key-value
					truncated = re.sub(r',\s*"[^"]*"?\s*:\s*"?[^"]*$', '', truncated)
					truncated = truncated.rstrip().rstrip(",")
				# Close brackets
				truncated += "]" * max(0, open_brackets) + "}" * max(0, open_braces)
				return attempt_parse(truncated)
			raise

	# First, try direct JSON parsing (with repairs)
	try:
		return _parse_with_repairs(text)
	except Exception:
		# Fallback: try to extract between the first '{' and last '}'
		start = text.find("{")
		end = text.rfind("}")
		if start != -1 and end != -1 and end > start:
			candidate = text[start : end + 1]
			try:
				return _parse_with_repairs(candidate)
			except Exception:
				pass
		raise


@router.post("/resume/upload-parse", response_model=ResumeJsonResponse, status_code=status.HTTP_201_CREATED)
async def upload_and_parse_resume(
	uid: str = Form(..., description="User ID (UID)"),
	file: UploadFile = File(..., description="Resume PDF"),
	user_repo: IUserRepository = Depends(get_user_repository),
) -> ResumeJsonResponse:
	"""Upload a resume PDF, parse it via OpenRouter into JSON, and store it.

	- Validates the UID.
	- Saves the PDF using LocalFileStorageService.
	- Extracts text from the PDF and sends it to an OpenRouter LLM with a strict JSON schema prompt.
	- Stores the parsed JSON in ``resume_parsed_data`` for the user.
	- Returns the user id and the parsed JSON to the client.
	"""

	# Validate UID
	try:
		user_uuid = UUID(uid)
	except ValueError:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid uid format")

	# Ensure OpenRouter API key is configured
	openrouter_key = settings.OPENROUTER_API_KEY
	if not openrouter_key:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="OpenRouter API key not configured",
		)

	# Save file locally and get base64 + text
	storage = LocalFileStorageService()
	try:
		file_path = await storage.save_file(user_uuid, file, "resume")
		await file.seek(0)
		content = await file.read()
		resume_base64 = base64.b64encode(content).decode("utf-8")

		pdf_file = io.BytesIO(content)
		text = ""
		with pdfplumber.open(pdf_file) as pdf:
			for page in pdf.pages:
				text += page.extract_text() or ""
	except Exception as exc:
		logger.error(f"Failed to save/read resume file for user {uid}: {exc}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to read resume file",
		)

	# Call OpenRouter to parse resume text into structured JSON
	prompt = (
		"Convert the given resume into a well-structured JSON format.\n\n"
		"Instructions:\n\n"
		"Extract all information from the resume accurately.\n\n"
		"Create separate JSON objects for the following sections if they exist in the resume:\n\n"
		"basic_info\n\n"
		"summary\n\n"
		"skills\n\n"
		"education\n\n"
		"experience\n\n"
		"projects\n\n"
		"languages\n\n"
		"If the resume contains additional sections (e.g., certifications, awards, interests, publications, etc.), "
		"create separate JSON sections for them as well.\n\n"
		"Do not omit any section that appears in the resume.\n\n"
		"Maintain clean, readable, and properly nested JSON.\n\n"
		"Use arrays where multiple entries exist (e.g., multiple jobs, degrees, or projects).\n\n"
		"Do not add any information that is not present in the resume.\n\n"
		"Output Requirement:\n\n"
		"Return only valid JSON\n\n"
		"No explanations, no extra text, no comments\n\n"
		"Input:\n" + text
	)

	try:
		async with httpx.AsyncClient(timeout=60.0) as client:
			response = await client.post(
				"https://openrouter.ai/api/v1/chat/completions",
				headers={
					"Authorization": f"Bearer {openrouter_key}",
					"Content-Type": "application/json",
				},
				json={
					"model": "openai/gpt-4o-mini",
					"messages": [
						{"role": "user", "content": prompt},
					],
					"temperature": 0.1,
					"max_tokens": 4000,
					"response_format": {"type": "json_object"},
				},
			)
			response.raise_for_status()
			data = response.json()
			content_text = data["choices"][0]["message"]["content"]
			parsed_json: Dict[str, Any] = _extract_json_from_text(content_text)
	except Exception as exc:
		logger.error(
			f"Failed to parse resume with OpenRouter for user {uid}: {exc}"
		)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to parse resume via OpenRouter",
		)

	# Persist parsed JSON and metadata on user
	user = await user_repo.get_by_id(user_uuid)
	if not user:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

	updated_user = replace(
		user,
		resume_url=file_path,
		resume_base64=resume_base64,
		resume_parsed_data=parsed_json,
		updated_at=datetime.utcnow(),
	)
	await user_repo.update(updated_user)

	logger.info(f"Resume uploaded and parsed via OpenRouter for user {uid}")

	return ResumeJsonResponse(user_id=uid, resume_data=parsed_json)


@router.post("/resume/json", response_model=ResumeJsonResponse, status_code=status.HTTP_200_OK)
async def save_resume_json(
	payload: ResumeJsonRequest = Body(..., description="UID and resume JSON structure"),
	user_repo: IUserRepository = Depends(get_user_repository),
) -> ResumeJsonResponse:
	"""Accept a resume JSON structure directly and store it for the given UID.

	This endpoint does **not** call OpenRouter; instead it trusts the client-provided
	JSON structure and saves it as ``resume_parsed_data`` for the specified user.
	"""

	try:
		user_uuid = UUID(payload.uid)
	except ValueError:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid uid format")

	user = await user_repo.get_by_id(user_uuid)
	if not user:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

	# Store provided JSON as-is
	parsed_json: Dict[str, Any] = payload.resume_data

	updated_user = replace(
		user,
		resume_parsed_data=parsed_json,
		updated_at=datetime.utcnow(),
	)
	await user_repo.update(updated_user)

	logger.info(f"Resume JSON stored for user {user.id}")

	return ResumeJsonResponse(user_id=str(updated_user.id), resume_data=parsed_json)


@router.post("/resume/enhance", response_model=EnhancedResumeResponse, status_code=status.HTTP_200_OK)
async def enhance_resume_for_job(
	payload: EnhanceResumeRequest = Body(..., description="UID, Job Description, and optional job details"),
	user_repo: IUserRepository = Depends(get_user_repository),
) -> EnhancedResumeResponse:
	"""
	Enhance resume summary and skills based on job description.
	
	**This endpoint:**
	- Fetches user's stored resume structure from DB
	- Extracts summary and skills sections
	- Uses AI (OpenRouter GPT-4o-mini) to enhance them for the specific JD
	- Returns BOTH original and enhanced resumes in JSON and text format
	- Does NOT persist enhanced resume to database (ephemeral)
	
	**Parameters:**
	- uid: User ID (UID)
	- job_description: The full job description text
	- job_title: Optional job title for better context
	- company: Optional company name for better context
	
	**Returns:**
	- original_resume: The user's original resume JSON
	- enhanced_resume: Resume JSON with enhanced summary and skills
	- original_resume_text: Original resume in ATS-friendly text format
	- enhanced_resume_text: Enhanced resume in ATS-friendly text format
	- enhancement_summary: Summary of what was enhanced
	"""
	
	# Validate UID
	try:
		user_uuid = UUID(payload.uid)
	except ValueError:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid uid format")
	
	# Get user and their resume
	user = await user_repo.get_by_id(user_uuid)
	if not user:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
	
	# Get resume data
	if not user.resume_parsed_data:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="No resume found for this user. Please upload a resume first."
		)
	
	original_resume = user.resume_parsed_data if isinstance(user.resume_parsed_data, dict) else json.loads(user.resume_parsed_data)
	
	# Use the ResumeEnhancementService for consistent enhancement
	from application.services.resume.resume_enhancement_service import (
		ResumeEnhancementService,
		create_enhanced_resume_json
	)
	
	# Ensure OpenRouter API key is configured
	openrouter_key = settings.OPENROUTER_API_KEY
	if not openrouter_key:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="OpenRouter API key not configured",
		)
	
	try:
		# Use the service for enhancement (now includes full resume context)
		enhancement_service = ResumeEnhancementService(openrouter_key)
		enhanced_content = await enhancement_service.enhance_resume(
			resume_data=original_resume,
			job_description=payload.job_description,
			job_title=payload.job_title,
			company=payload.company
		)
		
		# Create the enhanced resume JSON
		user_phone = getattr(user, 'phone', None) or getattr(user, 'phone_number', None)
		logger.debug(f"Merging user contact into enhanced resume - Name: {user.full_name}, Email: {user.email}, Phone: {user_phone}")
		
		enhanced_resume = create_enhanced_resume_json(
			original_resume, 
			enhanced_content,
			user_full_name=user.full_name,
			user_email=str(user.email),
			user_phone=user_phone
		)
		
		logger.debug(f"Enhanced resume basic_info after merge: {enhanced_resume.get('basic_info', {})}")
		
		# Extract for compatibility
		original_summary = enhanced_content.original_summary
		enhanced_summary = enhanced_content.enhanced_summary
		original_skills = enhanced_content.original_skills
		enhanced_skills = enhanced_content.enhanced_skills
		
	except Exception as exc:
		logger.error(f"Failed to enhance resume for user {payload.uid}: {exc}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to enhance resume",
		)
	
	# Generate ATS-friendly text format for both resumes
	original_resume_text = _generate_ats_resume_text(original_resume, user.full_name, str(user.email))
	enhanced_resume_text = _generate_ats_resume_text(enhanced_resume, user.full_name, str(user.email))
	
	# Build enhancement summary
	enhancement_summary = {
		"original_summary_length": len(original_summary),
		"enhanced_summary_length": len(enhanced_summary),
		"original_skills_count": len(original_skills) if isinstance(original_skills, list) else 1,
		"enhanced_skills_count": len(enhanced_skills) if isinstance(enhanced_skills, list) else 1,
		"job_title": payload.job_title,
		"company": payload.company,
	}
	
	logger.info(f"Resume enhanced for user {payload.uid} - Summary: {len(original_summary)} → {len(enhanced_summary)} chars, Skills: {len(original_skills)} → {len(enhanced_skills)} items")
	
	return EnhancedResumeResponse(
		user_id=payload.uid,
		original_resume=original_resume,
		enhanced_resume=enhanced_resume,
		original_resume_text=original_resume_text,
		enhanced_resume_text=enhanced_resume_text,
		enhancement_summary=enhancement_summary
	)


def _generate_ats_resume_text(resume_json: Dict[str, Any], full_name: str, email: str) -> str:
	"""
	Generate ATS-friendly plain text resume from JSON structure.
	
	Args:
		resume_json: Structured resume JSON data
		full_name: User's full name
		email: User's email
		
	Returns:
		ATS-optimized plain text resume
	"""
	lines = []
	
	# Header
	basic_info = resume_json.get("basic_info", {})
	name = basic_info.get("name", full_name) or full_name
	user_email = basic_info.get("email", email) or email
	phone = basic_info.get("phone", "")
	location = basic_info.get("location", "")
	linkedin = basic_info.get("linkedin", "")
	
	lines.append("=" * 60)
	lines.append(name.upper())
	lines.append("=" * 60)
	
	contact_parts = [p for p in [user_email, phone, location, linkedin] if p]
	if contact_parts:
		lines.append(" | ".join(contact_parts))
	lines.append("")
	
	# Professional Summary
	summary = resume_json.get("summary", "")
	if summary:
		lines.append("-" * 40)
		lines.append("PROFESSIONAL SUMMARY")
		lines.append("-" * 40)
		lines.append(summary)
		lines.append("")
	
	# Skills
	skills = resume_json.get("skills", [])
	if skills:
		lines.append("-" * 40)
		lines.append("SKILLS")
		lines.append("-" * 40)
		if isinstance(skills, list):
			# Group skills in rows of 5 for better readability
			for i in range(0, len(skills), 5):
				lines.append(" • ".join(skills[i:i+5]))
		else:
			lines.append(str(skills))
		lines.append("")
	
	# Experience
	experience = resume_json.get("experience", [])
	if experience:
		lines.append("-" * 40)
		lines.append("PROFESSIONAL EXPERIENCE")
		lines.append("-" * 40)
		for exp in experience:
			if isinstance(exp, dict):
				title = exp.get("title", exp.get("position", ""))
				company = exp.get("company", exp.get("organization", ""))
				dates = exp.get("dates", exp.get("duration", exp.get("date", "")))
				location = exp.get("location", "")
				description = exp.get("description", exp.get("responsibilities", ""))
				
				# Job header
				header = f"{title}"
				if company:
					header += f" | {company}"
				if location:
					header += f" | {location}"
				lines.append(header)
				
				if dates:
					lines.append(f"({dates})")
				
				# Description/Responsibilities
				if description:
					if isinstance(description, list):
						for item in description:
							lines.append(f"  • {item}")
					else:
						# Split by sentences or bullet points
						desc_lines = description.replace("•", "\n•").split("\n")
						for dl in desc_lines:
							dl = dl.strip()
							if dl:
								if not dl.startswith("•"):
									lines.append(f"  • {dl}")
								else:
									lines.append(f"  {dl}")
				lines.append("")
	
	# Education
	education = resume_json.get("education", [])
	if education:
		lines.append("-" * 40)
		lines.append("EDUCATION")
		lines.append("-" * 40)
		for edu in education:
			if isinstance(edu, dict):
				degree = edu.get("degree", "")
				institution = edu.get("institution", edu.get("school", edu.get("university", "")))
				dates = edu.get("dates", edu.get("year", edu.get("graduation_date", "")))
				gpa = edu.get("gpa", "")
				
				edu_line = f"{degree}"
				if institution:
					edu_line += f" - {institution}"
				if dates:
					edu_line += f" ({dates})"
				lines.append(edu_line)
				
				if gpa:
					lines.append(f"  GPA: {gpa}")
		lines.append("")
	
	# Projects
	projects = resume_json.get("projects", [])
	if projects:
		lines.append("-" * 40)
		lines.append("PROJECTS")
		lines.append("-" * 40)
		for proj in projects:
			if isinstance(proj, dict):
				name = proj.get("name", proj.get("title", ""))
				description = proj.get("description", "")
				link = proj.get("link", proj.get("url", proj.get("github", "")))
				technologies = proj.get("technologies", proj.get("tech_stack", []))
				
				if name:
					lines.append(f"► {name}")
				if description:
					lines.append(f"  {description}")
				if link:
					lines.append(f"  🔗 Link: {link}")
				if technologies:
					if isinstance(technologies, list):
						lines.append(f"  Technologies: {', '.join(technologies)}")
					else:
						lines.append(f"  Technologies: {technologies}")
				lines.append("")
	
	# Certifications
	certifications = resume_json.get("certifications", [])
	if certifications:
		lines.append("-" * 40)
		lines.append("CERTIFICATIONS")
		lines.append("-" * 40)
		for cert in certifications:
			if isinstance(cert, str):
				lines.append(f"  • {cert}")
			elif isinstance(cert, dict):
				cert_name = cert.get("name", cert.get("title", ""))
				cert_org = cert.get("organization", cert.get("issuer", ""))
				cert_date = cert.get("date", "")
				cert_line = cert_name
				if cert_org:
					cert_line += f" - {cert_org}"
				if cert_date:
					cert_line += f" ({cert_date})"
				lines.append(f"  • {cert_line}")
		lines.append("")
	
	# Languages
	languages = resume_json.get("languages", [])
	if languages:
		lines.append("-" * 40)
		lines.append("LANGUAGES")
		lines.append("-" * 40)
		lang_items = []
		for lang in languages:
			if isinstance(lang, str):
				lang_items.append(lang)
			elif isinstance(lang, dict):
				name = lang.get("name", lang.get("language", ""))
				level = lang.get("level", lang.get("proficiency", ""))
				if name:
					lang_items.append(f"{name}" + (f" ({level})" if level else ""))
		if lang_items:
			lines.append(" • ".join(lang_items))
		lines.append("")
	
	# Footer
	lines.append("=" * 60)
	
	return "\n".join(lines)
