"""
AutoApplyService Implementation
Manages automated job applications via LinkedIn Easy Apply
"""
import json
import random
import asyncio
from typing import List, Dict, Optional
from uuid import UUID
from datetime import datetime

from application.services.auto_apply import IAutoApplyService
from application.repositories.interfaces import IJobRepository, IUserRepository
from domain.entities import JobListing
from domain.enums import ApplicationStatus
from core.logging_config import logger
from infrastructure.security.baseline_cookie_cipher import (
    BaselineCookieCipher,
    BaselineCookieCipherError,
)


class AutoApplyService(IAutoApplyService):
    """Auto-apply service for LinkedIn Easy Apply automation"""
    
    # Anti-ban configuration
    MIN_DELAY_SECONDS = 30
    MAX_DELAY_SECONDS = 60
    MAX_APPLICATIONS_PER_SESSION = 10
    
    def __init__(
        self,
        job_repository: IJobRepository,
        user_repository: IUserRepository,
        job_listing_repository=None,
        user_job_repository=None,
    ):
        """
        Initialize auto-apply service
        
        Args:
            job_repository: Job repository
            user_repository: User repository
            job_listing_repository: JobListing repository (optional)
            user_job_repository: UserJob repository (optional)
        """
        self.job_repo = job_repository
        self.user_repo = user_repository
        self.job_listing_repo = job_listing_repository
        self.user_job_repo = user_job_repository
    
    async def apply_to_jobs(
        self,
        user_id: UUID,
        job_ids: List[UUID]
    ) -> Dict[UUID, ApplicationStatus]:
        """
        Apply to multiple jobs sequentially via LinkedIn Easy Apply
        
        Args:
            user_id: User ID
            job_ids: List of job IDs to apply to
            
        Returns:
            Dict mapping job_id to application status
        """
        results: Dict[UUID, ApplicationStatus] = {}
        
        logger.info(f"Starting auto-apply for user {user_id}, {len(job_ids)} jobs")
        
        # Fetch user
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            logger.error(f"User {user_id} not found")
            return {job_id: ApplicationStatus.PENDING for job_id in job_ids}
        
        # Check for stored cookies (prefers scraper cookies over auth cookies)
        cookies, saved_user_agent = self._parse_cookies(user.persistent_browser_profile)
        if not cookies:
            logger.error(f"No LinkedIn cookies found for user {user_id}")
            return {job_id: ApplicationStatus.PENDING for job_id in job_ids}
        
        # Prepare user data for form filling
        user_data = self._prepare_user_data(user)
        
        # Initialize automation
        try:
            from application.services.jobs.easy_apply_automation import EasyApplyAutomation
            from application.services.jobs.form_answer_generator import FormAnswerGenerator
            
            form_generator = FormAnswerGenerator()
            automation = EasyApplyAutomation(form_answer_generator=form_generator)
            
            # Setup browser
            # Use non-headless to allow visual debugging of the flow
            driver = automation.setup_driver(headless=False)
            if not driver:
                logger.error("Failed to setup browser driver")
                return {job_id: ApplicationStatus.PENDING for job_id in job_ids}
            
            # Verify login (credentials-based session)
            if not automation.verify_login():
                logger.error("LinkedIn login verification failed")
                automation.cleanup()
                return {job_id: ApplicationStatus.PENDING for job_id in job_ids}
            
            logger.info("LinkedIn login verified, starting applications")
            
            # Create temp resume file
            if user.resume_base64:
                automation.create_temp_resume(user.resume_base64)
            
            # Process jobs with anti-ban measures
            processed = 0
            for job_id in job_ids:
                if processed >= self.MAX_APPLICATIONS_PER_SESSION:
                    logger.warning(f"Reached max applications per session ({self.MAX_APPLICATIONS_PER_SESSION})")
                    results[job_id] = ApplicationStatus.PENDING
                    continue
                
                try:
                    # Fetch job details
                    job = await self._get_job_details(job_id)
                    if not job:
                        logger.warning(f"Job {job_id} not found")
                        results[job_id] = ApplicationStatus.PENDING
                        continue
                    
                    job_data = {
                        "external_id": getattr(job, "external_id", str(job_id)),
                        "title": job.title,
                        "company": job.company,
                        "url": job.url if hasattr(job, "url") else job.linkedin_url,
                        "description": job.description,
                    }
                    
                    # Apply to job
                    logger.info(f"Applying to: {job.title} at {job.company}")
                    result = await automation.apply_to_job(
                        job_url=job_data["url"],
                        user_data=user_data,
                        job_data=job_data
                    )
                    
                    if result.success:
                        results[job_id] = ApplicationStatus.APPLIED
                        logger.info(f"SUCCESS: Applied to {job.title} at {job.company}")
                        
                        # Update database
                        if self.user_job_repo:
                            await self.user_job_repo.update_status(
                                user_id=user_id,
                                job_id=job_id,
                                status=ApplicationStatus.APPLIED,
                                applied_at=datetime.utcnow()
                            )
                    else:
                        results[job_id] = ApplicationStatus.PENDING
                        logger.warning(f"FAILED: {job.title} - {result.message}")
                    
                    processed += 1
                    
                    # Anti-ban delay between applications
                    if processed < len(job_ids):
                        delay = random.uniform(self.MIN_DELAY_SECONDS, self.MAX_DELAY_SECONDS)
                        logger.info(f"Waiting {delay:.1f}s before next application...")
                        await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"Error applying to job {job_id}: {e}")
                    results[job_id] = ApplicationStatus.PENDING
            
            # Cleanup
            automation.cleanup()
            
        except ImportError as e:
            logger.error(f"Required modules not available: {e}")
            return {job_id: ApplicationStatus.PENDING for job_id in job_ids}
        except Exception as e:
            logger.error(f"Auto-apply error: {e}")
            # Return pending for any jobs not yet processed
            for job_id in job_ids:
                if job_id not in results:
                    results[job_id] = ApplicationStatus.PENDING
        
        # Summary
        applied = sum(1 for s in results.values() if s == ApplicationStatus.APPLIED)
        logger.info(f"Auto-apply complete: {applied}/{len(job_ids)} successful")
        
        return results
    
    def _parse_cookies(self, cookies_json: Optional[str]) -> tuple:
        """
        Parse cookies from JSON string.
        
        Handles two formats:
        1. Direct array: [{"name": "li_at", ...}]
        2. Scraper format: {"cookies": [...], "user_agent": "..."}
        
        Returns:
            Tuple of (cookies_list, user_agent)
        """
        if not cookies_json:
            return [], None
        
        try:
            cipher = BaselineCookieCipher()
            data = cipher.decrypt_profile(cookies_json)
        except BaselineCookieCipherError:
            try:
                data = json.loads(cookies_json)
            except json.JSONDecodeError:
                return [], None
        
        # Format 2: Scraper format with cookies key (preferred - more recent)
        if isinstance(data, dict) and "cookies" in data:
            cookies = data.get("cookies", [])
            user_agent = data.get("user_agent")
            logger.info(f"Loaded {len(cookies)} cookies from encrypted profile format")
            return cookies, user_agent
        
        # Format 1: Direct array (legacy plaintext)
        if isinstance(data, list):
            logger.info(f"Loaded {len(data)} cookies from legacy direct array format")
            return data, None
        
        return [], None
    
    def _prepare_user_data(self, user) -> Dict:
        """Prepare user data dictionary for form filling"""
        resume_parsed = user.resume_parsed_data or {}
        
        return {
            "full_name": user.full_name,
            "email": str(user.email) if user.email else "",
            "phone": resume_parsed.get("contact", {}).get("phone", ""),
            "linkedin_url": "",
            "resume_base64": user.resume_base64,
            "resume_parsed_data": resume_parsed,
            "resume_summary": resume_parsed.get("summary", ""),
            "skills": resume_parsed.get("skills", []),
            "experience": resume_parsed.get("experience", []),
            "education": resume_parsed.get("education", []),
            "target_job_title": user.target_job_title or user.job_title_priority_1 or "",
            "exp_years_internship": user.exp_years_internship,
            "exp_years_entry_level": user.exp_years_entry_level,
            "exp_years_associate": user.exp_years_associate,
            "exp_years_mid_senior_level": user.exp_years_mid_senior_level,
            "exp_years_director": user.exp_years_director,
            "exp_years_executive": user.exp_years_executive,
            "pref_remote": user.pref_remote,
            "pref_hybrid": user.pref_hybrid,
            "pref_onsite": user.pref_onsite,
        }
    
    async def _get_job_details(self, job_id: UUID):
        """Get job details from repository"""
        # Try job_listing_repo first
        if self.job_listing_repo:
            try:
                return await self.job_listing_repo.get_by_id(job_id)
            except:
                pass
        
        # Fall back to job_repo
        if self.job_repo:
            try:
                return await self.job_repo.get_by_id(job_id)
            except:
                pass
        
        return None

