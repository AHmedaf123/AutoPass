"""
Clean Job Discovery and Application Endpoints
Simplified job scraping and application matching requirements
"""
from typing import List, Optional, AsyncGenerator
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Form, Query
from fastapi.responses import StreamingResponse
from loguru import logger
from datetime import datetime
import json
import os
import asyncio

from infrastructure.security.baseline_cookie_cipher import (
    BaselineCookieCipher,
    BaselineCookieCipherError,
)

from domain.entities import User
from presentation.api.v1.dependencies import get_current_user
from presentation.api.v1.container import get_user_repository
from application.repositories.interfaces import IUserRepository
from application.services.jobs.job_scraper_service import JobScraperService
from application.services.jobs.async_job_discovery_task import create_async_job_discovery_task
from infrastructure.persistence.repositories.job_listing import JobListingRepository
from infrastructure.persistence.repositories.user_job import UserJobRepository
from infrastructure.services.ai_match_service import AIMatchService
from infrastructure.services.job_stream_manager import get_stream_manager
from core.config import settings
from infrastructure.services.auto_apply_service import AutoApplyService
from domain.entities.job_listing import JobListing
from domain.entities.user_job import UserJob

from domain.enums import ApplicationStatus, WorkType
from core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from application.services.task_queue_service import TaskQueueService
from application.services.jobs.linkedin_url_builder import LinkedInURLBuilder


router = APIRouter()


class JobResponse(BaseModel):
    """Single job response"""
    job_id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    work_type: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    match_score: Optional[float] = None
    application_status: str = "pending"


class JobDiscoveryResponse(BaseModel):
    """Job discovery response"""
    user_id: str
    jobs_discovered: int
    jobs: List[JobResponse]
    message: str


class StreamingJobDiscoveryResponse(BaseModel):
    """Initial streaming job discovery response (cached jobs + stream URL)"""
    user_id: str
    jobs_cached: int
    jobs: List[JobResponse]
    stream_session_id: str
    message: str


class PendingJobsResponse(BaseModel):
    """Pending jobs response without triggering new scraping"""
    user_id: str
    jobs_pending: int
    jobs: List[JobResponse]
    message: str


class ApplicationRequest(BaseModel):
    """Application request"""
    job_id: str


class ApplicationResponse(BaseModel):
    """Application response"""
    user_id: str
    job_id: str
    status: str
    message: str


class TaskEnqueueResponse(BaseModel):
    """Task enqueue response"""
    task_id: str
    user_id: str
    message: str
    status: str


class TaskStatusResponse(BaseModel):
    """Task status response"""
    task_id: str
    user_id: str
    task_type: str
    status: str
    current_step: Optional[str]
    retries: int
    max_retries: int
    error_message: Optional[str]
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]


class TaskAIResponsesResponse(BaseModel):
    """AI-generated form responses for a task"""
    task_id: str
    task_type: str
    status: str
    ai_responses: Optional[dict] = None
    response_count: int = 0
    message: str


class TaskDetailedStatusResponse(BaseModel):
    """Detailed task status with application step tracking"""
    task_id: str
    user_id: str
    task_type: str
    status: str
    current_step: Optional[str] = None
    application_step: Optional[str] = None  # navigation, button_click, form_filling, submission, completed
    progress_data: Optional[dict] = None
    retries: int
    max_retries: int
    error_message: Optional[str]
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    message: str






@router.get("/jobs/pending", response_model=PendingJobsResponse)
async def get_pending_jobs(
    user_id: str = Query(..., description="User ID (UID)"),
    limit: int = Query(100, ge=1, le=500, description="Maximum pending jobs to return"),
    user_repo: IUserRepository = Depends(get_user_repository),
    session: AsyncSession = Depends(get_db)
):
    """
    Return pending jobs for a user without triggering new scraping.
    This endpoint is read-only and only queries existing records.
    """
    try:
        # Validate UUID input
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )

        # Ensure user exists
        user = await user_repo.get_by_id(user_uuid)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        job_repo = JobListingRepository(session)
        user_job_repo = UserJobRepository(session)

        pending_user_jobs = await user_job_repo.get_pending_jobs(user_uuid, limit=limit)

        jobs: List[JobResponse] = []
        for user_job in pending_user_jobs:
            job = await job_repo.get_by_id(user_job.job_id)
            if not job:
                logger.warning(f"Job not found for pending user-job link: {user_job.job_id}")
                continue

            jobs.append(JobResponse(
                job_id=str(job.id),
                title=job.title,
                company=job.company,
                location=job.location,
                description=job.description,
                url=job.url,
                work_type=job.work_type.value if job.work_type else None,
                salary_min=None,
                salary_max=None,
                match_score=user_job.match_score,
                application_status=user_job.status.value
            ))

        return PendingJobsResponse(
            user_id=str(user_uuid),
            jobs_pending=len(jobs),
            jobs=jobs,
            message=f"Retrieved {len(jobs)} pending jobs without starting discovery"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving pending jobs for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch pending jobs"
        )


@router.post("/job_scraping")
async def scrape_jobs(
    user_id: str = Form(..., description="User ID (UID)"),
    session_id: str = Form(..., description="LinkedIn session ID (from /api/v1/auth/linkedin/session)"),
    user_repo: IUserRepository = Depends(get_user_repository),
    session: AsyncSession = Depends(get_db)
):
    """
    Job Scraping - Scrapes jobs and returns all results
    
    **Behavior:**
    1. Scrapes LinkedIn jobs for all configured job titles using provided session
    2. Saves all discovered jobs to database (logic unchanged)
    3. Returns all scraped jobs in the response
    
    **Returns:**
    - user_id: User UUID
    - jobs_discovered: Number of jobs scraped
    - jobs: List of all jobs scraped from LinkedIn
    - message: Summary of scraping operation
    
    **Parameters:**
    - user_id: User ID (UID) from login response
    - session_id: LinkedIn session ID (required) from /api/v1/auth/linkedin/session
    
    **Rate Limited**: Avoid calling too frequently to prevent LinkedIn blocks.
    **Note**: This endpoint will wait for scraping to complete before returning results.
    """
    try:
        # Validate UUID format
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id format"
            )
        
        # Get user with latest data
        user = await user_repo.get_by_id(user_uuid)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Validate and use the provided LinkedIn session
        from application.services.linkedin_session_manager import get_session_manager
        session_manager = get_session_manager()
        
        active_session = session_manager.get_session(session_id)
        if not active_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LinkedIn session {session_id} not found. Please create a new session via /api/v1/auth/linkedin/session"
            )
        
        # Verify session belongs to this user
        if active_session.user_id != str(user_uuid):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This LinkedIn session does not belong to this user"
            )
        
        logger.info(f"✅ Using LinkedIn session: {session_id} for job discovery")
        
        active_session_id = session_id
        cookies = []
        
        # Get user preferences
        job_titles = []
        if user.job_title_priority_1:
            job_titles.append(user.job_title_priority_1)
        if user.job_title_priority_2:
            job_titles.append(user.job_title_priority_2)
        if user.job_title_priority_3:
            job_titles.append(user.job_title_priority_3)
        
        if not job_titles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No job titles set. Please set preferences via /api/v1/preferences"
            )
        
        # Determine work type (from user preferences)
        work_type = None
        if user.pref_remote:
            work_type = "Remote"
        elif user.pref_hybrid:
            work_type = "Hybrid"
        elif user.pref_onsite:
            work_type = "Onsite"

        # Determine experience level (from user experience fields)
        # Priority: Executive > Director > Mid-Senior level > Associate > Entry level > Internship
        experience_level = None
        if user.exp_years_executive:
            experience_level = "Executive"
        elif user.exp_years_director:
            experience_level = "Director"
        elif user.exp_years_mid_senior_level:
            experience_level = "Mid-Senior level"
        elif user.exp_years_associate:
            experience_level = "Associate"
        elif user.exp_years_entry_level:
            experience_level = "Entry level"
        elif user.exp_years_internship is not None:
            experience_level = "Internship"
        
        # Get location
        location = user.industry or "Pakistan"
        
        # Initialize repositories
        job_repo = JobListingRepository(session)
        user_job_repo = UserJobRepository(session)
        
        # ========== STEP 1: Perform synchronous job scraping ==========
        logger.info(f"🔍 Starting job scraping for user {user.id}...")
        
        # Prepare resume text for AI matching
        resume_text = ""
        if user.resume_parsed_data:
            parsed = user.resume_parsed_data
            parts = []
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except:
                    pass
            
            if isinstance(parsed, dict):
                if parsed.get("summary"):
                    parts.append(parsed["summary"])
                if parsed.get("skills"):
                    parts.append(f"Skills: {', '.join(parsed['skills'])}")
            
            resume_text = " ".join(parts)
        
        # Initialize AI match service if resume available
        ai_match_service = None
        if resume_text:
            try:
                ai_match_service = AIMatchService()
            except Exception as e:
                logger.warning(f"Failed to initialize AI Match Service: {e}")
        
        # ⚡ OPTIMIZED SCRAPING: Open tabs sequentially, then scrape efficiently
        logger.info(f"🚀 Starting scraping for {len(job_titles)} job titles...")
        logger.info(f"Using session: {active_session_id}")
        
        # Get the driver
        from application.services.linkedin_session_manager import get_session_manager
        import time
        
        session_manager = get_session_manager()
        linkedin_session = session_manager.get_user_session(active_session_id)
        
        if not linkedin_session or not linkedin_session.driver:
            logger.error("Session not found or driver unavailable")
            return JobDiscoveryResponse(
                user_id=str(user_uuid),
                jobs_discovered=0,
                jobs=[],
                message="Session not found"
            )
        
        driver = linkedin_session.driver
        
        # Scrape all job titles sequentially in same browser tab
        # (Multi-tab approach blocked by browser security - this is faster and more reliable)
        logger.info(f"🔍 Scraping {len(job_titles)} job titles sequentially...")
        
        all_jobs_data = []
        scraper = JobScraperService()
        
        for idx, title in enumerate(job_titles, 1):
            try:
                logger.info(f"📍 [{idx}/{len(job_titles)}] Scraping '{title}'...")
                
                # Build search URL
                from urllib.parse import quote
                filters = "f_AL=true"
                
                if experience_level:
                    level_map = {
                        "internship": "1",
                        "entry level": "2",
                        "entry": "2",
                        "associate": "3",
                        "mid-senior": "4",
                        "mid": "4",
                        "senior": "4",
                        "director": "5",
                        "executive": "6"
                    }
                    exp_code = level_map.get(experience_level.lower())
                    if exp_code:
                        filters += f"&f_E={exp_code}"
                
                if work_type:
                    wt_map = {
                        "on-site": "1",
                        "onsite": "1",
                        "on site": "1",
                        "remote": "2",
                        "hybrid": "3"
                    }
                    wt_code = wt_map.get(work_type.lower())
                    if wt_code:
                        filters += f"&f_WT={wt_code}"
                
                search_url = f"https://www.linkedin.com/jobs/search/?{filters}&geoId=104112529&keywords={quote(title)}&origin=JOB_SEARCH_PAGE_SEARCH_BUTTON&refresh=true"
                
                logger.info(f"  🌐 Navigating to search for '{title}'...")
                driver.get(search_url)
                time.sleep(4)  # Wait for page load
                
                # Extract jobs
                logger.info(f"  📥 Extracting jobs...")
                jobs_data = scraper._extract_all_jobs(driver)
                all_jobs_data.extend(jobs_data)
                
                logger.info(f"✅ [{idx}/{len(job_titles)}] Found {len(jobs_data)} jobs for '{title}' (Total: {len(all_jobs_data)})")
                
            except Exception as e:
                logger.error(f"❌ [{idx}/{len(job_titles)}] Error scraping '{title}': {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        total_scraped = len(all_jobs_data)
        logger.info(f"⚡ Completed scraping {len(job_titles)} titles: {total_scraped} total jobs")
        
        if not all_jobs_data:
            logger.warning("No jobs scraped")
            return JobDiscoveryResponse(
                user_id=str(user_uuid),
                jobs_discovered=0,
                jobs=[],
                message="No jobs found"
            )
        
        # ⚡ BATCH LOOKUP: Get all existing external IDs at once
        external_ids = []
        platform = "linkedin"
        for job_data in all_jobs_data:
            ext_id = str(job_data.get("job_id") or job_data.get("external_id")).strip()
            if ext_id and ext_id != "None":
                external_ids.append(ext_id)
        
        existing_jobs_map = {}
        if external_ids:
            # Get all existing jobs in one query
            from sqlalchemy import select, and_
            from infrastructure.persistence.models.job_listing import JobListingModel
            try:
                existing_result = await session.execute(
                    select(JobListingModel).where(
                        and_(
                            JobListingModel.platform == platform,
                            JobListingModel.external_id.in_(external_ids)
                        )
                    )
                )
                existing_jobs_models = existing_result.scalars().all()
                existing_jobs_map = {m.external_id: job_repo._to_entity(m) for m in existing_jobs_models}
            except Exception as lookup_error:
                logger.warning(f"Error during batch lookup: {lookup_error}")
        
        logger.info(f"⚡ Found {len(existing_jobs_map)} existing jobs in DB")
        
        # ⚡ BATCH PROCESSING: Prepare new jobs and user-job links
        from uuid import uuid4
        new_jobs = []
        new_user_jobs = []
        all_job_entities = []  # For AI batch scoring
        
        for job_data in all_jobs_data:
            try:
                external_id = job_data.get("job_id") or job_data.get("external_id")
                if not external_id:
                    continue
                
                existing_job = existing_jobs_map.get(external_id)
                
                if existing_job:
                    # Check if user already has this job
                    existing_user_job = await user_job_repo.get_by_user_and_job(user.id, existing_job.id)
                    if not existing_user_job:
                        all_job_entities.append(existing_job)
                        new_user_jobs.append({
                            'job': existing_job,
                            'is_new_job': False
                        })
                else:
                    # Create new job entity
                    description = job_data.get("description", "")
                    job_work_type = None
                    if job_data.get("work_type"):
                        try:
                            job_work_type = WorkType(job_data["work_type"])
                        except:
                            pass
                    
                    job = JobListing(
                        external_id=external_id,
                        platform=platform,
                        title=job_data.get("title", ""),
                        company=job_data.get("company", ""),
                        location=job_data.get("location", ""),
                        description=description,
                        url=job_data.get("apply_url", ""),
                        work_type=job_work_type,
                        salary_min=job_data.get("salary_min"),
                        salary_max=job_data.get("salary_max")
                    )
                    new_jobs.append(job)
                    all_job_entities.append(job)
                    new_user_jobs.append({
                        'job': job,
                        'is_new_job': True
                    })
            except Exception as e:
                logger.error(f"Error preparing job {job_data.get('job_id')}: {e}")
        
        # ⚡ BULK INSERT: Add all new jobs at once
        if new_jobs:
            logger.info(f"⚡ Bulk inserting {len(new_jobs)} new jobs...")
            successfully_inserted = []
            skipped_duplicates = []
            
            for job in new_jobs:
                try:
                    # add() returns the entity with populated ID
                    # The repository will check for duplicates by external_id AND title+company+description
                    inserted_job = await job_repo.add(job)
                    successfully_inserted.append(inserted_job)
                    
                    # ⭐ COMMIT IMMEDIATELY after each successful insert
                    # This prevents session corruption when duplicates occur
                    try:
                        await session.commit()
                        logger.debug(f"✓ Committed job {job.external_id}")
                    except Exception as commit_err:
                        logger.error(f"Commit error for {job.external_id}: {commit_err}")
                        raise
                    
                    # Update references to use the inserted job with ID
                    for idx, entity in enumerate(all_job_entities):
                        if entity.external_id == job.external_id:
                            all_job_entities[idx] = inserted_job
                            break
                    for item in new_user_jobs:
                        if item['job'].external_id == job.external_id:
                            item['job'] = inserted_job
                            break
                            
                except Exception as insert_error:
                    # Check if this is a duplicate key error
                    error_str = str(insert_error).lower()
                    if "duplicate key" in error_str or "unique" in error_str:
                        logger.warning(f"Skipping duplicate job {job.external_id}")
                        skipped_duplicates.append(job.external_id)
                        
                        # Rollback to clear the failed session state
                        try:
                            await session.rollback()
                            logger.debug(f"Session rolled back after duplicate")
                        except Exception as rb_err:
                            logger.debug(f"Rollback: {type(rb_err).__name__}")
                        
                        # NOW we can safely query
                        try:
                            existing = await job_repo.get_by_external_id(job.external_id, platform)
                            if existing:
                                # Replace in all_job_entities for AI scoring
                                for idx, entity in enumerate(all_job_entities):
                                    if entity.external_id == job.external_id:
                                        all_job_entities[idx] = existing
                                        break
                                # Update new_user_jobs to use existing job
                                for item in new_user_jobs:
                                    if item['job'].external_id == job.external_id:
                                        item['job'] = existing
                                        item['is_new_job'] = False
                                        break
                                logger.info(f"✓ Using existing job {job.external_id}")
                            else:
                                logger.error(f"Couldn't fetch existing duplicate job {job.external_id}")
                                all_job_entities = [e for e in all_job_entities if e.external_id != job.external_id]
                                new_user_jobs = [item for item in new_user_jobs if item['job'].external_id != job.external_id]
                        except Exception as fetch_error:
                            logger.error(f"Error fetching existing job {job.external_id}: {fetch_error}")
                            # Remove from processing since we can't get the job
                            all_job_entities = [e for e in all_job_entities if e.external_id != job.external_id]
                            new_user_jobs = [item for item in new_user_jobs if item['job'].external_id != job.external_id]
                    else:
                        logger.error(f"Error inserting job {job.external_id}: {insert_error}")
                        raise
            
            # Log results
            logger.info(f"✓ Inserted {len(successfully_inserted)} new jobs")
            if skipped_duplicates:
                logger.info(f"  ({len(skipped_duplicates)} skipped as duplicates)")
        
        # ⚡ COMMIT: Persist all inserted jobs to database BEFORE creating user-job links
        try:
            await session.commit()
            logger.info("✓ Jobs committed to database")
        except Exception as commit_error:
            logger.error(f"Error committing jobs: {commit_error}")
            raise
        
        # ⚡ BATCH AI SCORING: Calculate all match scores at once
        match_scores_map = {}
        if ai_match_service and resume_text and all_job_entities:
            try:
                logger.info(f"⚡ Batch calculating {len(all_job_entities)} match scores...")
                match_scores_map = await ai_match_service.batch_calculate_scores(resume_text, all_job_entities)
                logger.info(f"✓ Calculated {len(match_scores_map)} match scores")
            except Exception as e:
                logger.warning(f"Batch match scoring failed: {e}")
        
        # ⚡ BULK INSERT: Create all user-job links
        logger.info(f"⚡ Creating {len(new_user_jobs)} user-job links...")
        all_scraped_jobs = []
        
        for item in new_user_jobs:
            job = item['job']
            
            # Validate job has an ID before creating user_job link
            if not job.id:
                logger.error(f"Job {job.external_id} has no ID, skipping user_job creation")
                continue
            
            match_score_obj = match_scores_map.get(job.id)
            match_score = int(match_score_obj.value) if match_score_obj else None
            
            # Check if user-job link already exists
            existing_user_job = await user_job_repo.get_by_user_and_job(user.id, job.id)
            
            if existing_user_job:
                logger.debug(f"User-job link already exists for job {job.id}, skipping creation")
                # Still include in response with existing match score
                match_score = existing_user_job.match_score
            else:
                user_job = UserJob(
                    id=uuid4(),
                    user_id=user.id,
                    job_id=job.id,
                    status=ApplicationStatus.PENDING,
                    match_score=match_score
                )
                try:
                    await user_job_repo.add(user_job)
                except IntegrityError as e:
                    if "uq_user_jobs_user_id_job_id" in str(e):
                        logger.debug(f"User-job link already exists for job {job.id} (caught duplicate)")
                        # Get existing match score
                        existing = await user_job_repo.get_by_user_and_job(user.id, job.id)
                        match_score = existing.match_score if existing else match_score
                    else:
                        logger.warning(f"Integrity error creating user-job link for job {job.id}: {e}")
                        raise
                except Exception as e:
                    logger.warning(f"Error creating user-job link for job {job.id}: {e}")
                    raise
            
            # Build response (always include the job)
            all_scraped_jobs.append(JobResponse(
                job_id=str(job.id),
                title=job.title,
                company=job.company,
                location=job.location,
                description=job.description,
                url=job.url,
                work_type=job.work_type.value if job.work_type else None,
                salary_min=job.salary_min if hasattr(job, 'salary_min') else None,
                salary_max=job.salary_max if hasattr(job, 'salary_max') else None,
                match_score=match_score,
                application_status="pending"
            ))
        
        # ⚡ SINGLE COMMIT: Commit everything at once
        await session.commit()
        logger.info(f"✓ Committed {len(new_user_jobs)} user-job links")
        
        logger.info(f"⚡ Job scraping COMPLETE! Total: {total_scraped}, New: {len(new_jobs)}, Saved: {len(all_scraped_jobs)}")
        
        # ========== STEP 2: Return all scraped jobs ==========
        return JobDiscoveryResponse(
            user_id=str(user.id),
            jobs_discovered=len(all_scraped_jobs),
            jobs=all_scraped_jobs,
            message=f"Successfully scraped and saved {len(all_scraped_jobs)} jobs from LinkedIn"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error discovering jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to discover jobs: {str(e)}"
        )






@router.post("/apply-single", response_model=ApplicationResponse)
async def apply_to_single_job(
    user_id: str = Form(..., description="User ID (UID)"),
    job_id: str = Form(..., description="Job ID"),
    session_id: str = Form(..., description="LinkedIn session ID (from /api/v1/auth/linkedin/session)"),
    enhance_resume: bool = Form(False, description="If true, AI-enhance resume summary and skills based on job description"),
    user_repo: IUserRepository = Depends(get_user_repository),
    session: AsyncSession = Depends(get_db)
):
    """
    Apply to a single job using Easy Apply automation.
    
    **This endpoint:**
    - Uses provided LinkedIn session for automation
    - Gets job URL from database
    - Uses AI (OpenRouter GPT-4o-mini) to fill application forms
    - Optionally enhances resume with AI to match job description
    - Returns detailed success/failure response
    
    **Parameters:**
    - user_id: User ID (UID)
    - job_id: Job ID from job discovery
    - session_id: LinkedIn session ID (required) from /api/v1/auth/linkedin/session
    - enhance_resume: If true, dynamically tailor skills and summary using the JD via LLM
    
    **Resume Enhancement (when enhance_resume=true):**
    - Fetches user's structured resume JSON (summary + skills only)
    - Fetches job description from database
    - Uses AI to rewrite summary and skills aligned to JD keywords
    - Generates a temporary resume file for this application only
    - Does NOT persist any enhanced content to database
    
    **Returns:**
    - success: Whether application was submitted
    - message: Detailed status message
    - error_stage: Where it failed (if applicable)
    """
    # Variables for cleanup
    temp_resume_file = None
    
    try:
        from application.services.jobs.single_job_applier import SingleJobApplier
        from core.config import settings
        import os
        
        # Validate UUIDs
        try:
            user_uuid = UUID(user_id)
            job_uuid = UUID(job_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_id or job_id format"
            )
        
        # Get user
        user = await user_repo.get_by_id(user_uuid)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check cooldown (critical: prevents 429 cascades)
        from datetime import datetime, timezone
        if user.cooldown_until:
            if user.cooldown_until > datetime.now(timezone.utc):
                seconds_remaining = int((user.cooldown_until - datetime.now(timezone.utc)).total_seconds())
                hours_remaining = seconds_remaining / 3600
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": f"Account in cooldown after tainted session",
                        "reason": user.last_session_outcome or "unknown",
                        "cooldown_ends": user.cooldown_until.isoformat(),
                        "hours_remaining": round(hours_remaining, 1),
                        "seconds_remaining": seconds_remaining
                    }
                )
        
        # Validate and use the provided LinkedIn session
        from application.services.linkedin_session_manager import get_session_manager
        session_manager = get_session_manager()
        
        active_session = session_manager.get_session(session_id)
        if not active_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LinkedIn session {session_id} not found. Please create a new session via /api/v1/auth/linkedin/session"
            )
        
        # Verify session belongs to this user
        if active_session.user_id != str(user_uuid):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This LinkedIn session does not belong to this user"
            )
        
        logger.info(f"✅ Using LinkedIn session: {session_id} for job application")
        
        # Note: For Selenium-based sessions, we don't extract cookies
        # The session manager handles the browser driver directly
        cookies = []
        
        logger.info(f"Loaded {len(cookies)} cookies for user {user_id}")
        
        # Get job from database
        job_repo = JobListingRepository(session)
        job = await job_repo.get_by_id(job_uuid)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        job_url = job.url or job.linkedin_url
        if not job_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job URL not available"
            )
        
        logger.info(f"Applying to job: {job.title} at {job.company}")
        logger.info(f"Job URL: {job_url}")
        
        # Get OpenRouter API key
        openrouter_key = settings.OPENROUTER_API_KEY
        if not openrouter_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenRouter API key not configured"
            )
        
        # Get resume text - with optional AI enhancement
        resume_text = ""
        resume_data = None
        enhanced_resume_json = None
        
        if user.resume_parsed_data:
            try:
                resume_data = json.loads(user.resume_parsed_data) if isinstance(user.resume_parsed_data, str) else user.resume_parsed_data
                
                # === RESUME ENHANCEMENT FLOW ===
                if enhance_resume and job.description:
                    logger.info("🚀 Resume enhancement enabled - tailoring resume to job description")
                    try:
                        from application.services.resume.resume_enhancement_service import (
                            ResumeEnhancementService,
                            create_enhanced_resume_json
                        )
                        from application.services.resume.temp_resume_generator import (
                            TempResumeGeneratorService,
                            cleanup_temp_resume
                        )
                        
                        # Step 1: Enhance resume summary and skills using AI
                        enhancement_service = ResumeEnhancementService(openrouter_key)
                        enhanced_content = await enhancement_service.enhance_resume(
                            resume_data=resume_data,
                            job_description=job.description,
                            job_title=job.title,
                            company=job.company
                        )
                        
                        logger.info(f"✅ Resume enhanced - Summary: {len(enhanced_content.enhanced_summary)} chars, Skills: {len(enhanced_content.enhanced_skills)} items")
                        
                        # Step 2: Create temporary enhanced resume JSON (in-memory, NOT persisted)
                        # Pass user contact info to ensure it's in the PDF
                        user_phone = getattr(user, 'phone', None) or getattr(user, 'phone_number', None)
                        logger.debug(f"Merging user contact into enhanced resume - Name: {user.full_name}, Email: {user.email}, Phone: {user_phone}")
                        
                        enhanced_resume_json = create_enhanced_resume_json(
                            resume_data, 
                            enhanced_content,
                            user_full_name=user.full_name,
                            user_email=str(user.email),
                            user_phone=user_phone
                        )
                        
                        logger.debug(f"Enhanced resume basic_info after merge: {enhanced_resume_json.get('basic_info', {})}")
                        
                        # Step 3: Generate temporary PDF resume file
                        generator_service = TempResumeGeneratorService()
                        temp_resume_file = generator_service.generate_temp_resume(enhanced_resume_json, format="pdf")
                        
                        logger.info(f"✅ Temporary enhanced resume PDF created: {temp_resume_file.file_path}")
                        
                        # Step 4: Generate resume text from enhanced JSON for AI form filling
                        resume_text = generator_service.generate_resume_text(enhanced_resume_json)
                        
                        # Use the enhanced resume for the rest of this application
                        resume_data = enhanced_resume_json
                        
                    except Exception as enhance_error:
                        logger.warning(f"⚠️ Resume enhancement failed, falling back to original resume: {enhance_error}")
                        # Fall through to use original resume
                
                # === STANDARD RESUME FLOW (or fallback from failed enhancement) ===
                if not resume_text:
                    # Build resume text from original data
                    resume_text = f"Name: {user.full_name}\n"
                    resume_text += f"Email: {user.email}\n\n"
                    
                    if resume_data.get("summary"):
                        resume_text += f"Summary:\n{resume_data['summary']}\n\n"
                    
                    if resume_data.get("experience"):
                        resume_text += "Experience:\n"
                        for exp in resume_data.get("experience", []):
                            resume_text += f"- {exp.get('title', '')} at {exp.get('company', '')}\n"
                            if exp.get('description'):
                                resume_text += f"  {exp['description']}\n"
                        resume_text += "\n"
                    
                    if resume_data.get("education"):
                        resume_text += "Education:\n"
                        for edu in resume_data.get("education", []):
                            resume_text += f"- {edu.get('degree', '')} from {edu.get('institution', '')}\n"
                        resume_text += "\n"
                    
                    if resume_data.get("skills"):
                        skills = resume_data.get("skills", [])
                        if isinstance(skills, list):
                            resume_text += f"Skills: {', '.join(skills)}\n"
                        else:
                            resume_text += f"Skills: {skills}\n"
                
            except Exception as e:
                logger.warning(f"Could not parse resume data: {e}")
        
        if not resume_text:
            resume_text = f"Name: {user.full_name}\nEmail: {user.email}\n"
        
        logger.info(f"Resume text length: {len(resume_text)} characters")
        if enhance_resume:
            if not temp_resume_file or not os.path.exists(temp_resume_file.file_path):
                logger.error("❌ Enhancement requested but enhanced resume PDF was not generated. Aborting application.")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Enhanced resume could not be generated. Application aborted. Please check enhancement logs."
                )
            logger.info(f"📄 Using enhanced resume for application: {temp_resume_file.file_path}")

        # Initialize applier with optional temporary enhanced resume path
        applier = SingleJobApplier(
            openrouter_api_key=openrouter_key,
            resume_text=resume_text,
            resume_json=enhanced_resume_json if enhance_resume and enhanced_resume_json else None,
            temp_resume_path=temp_resume_file.file_path if temp_resume_file else None
        )

        # Apply to job
        logger.info("Starting application process...")
        result = applier.apply_to_job(
            job_url=job_url,
            cookies=cookies,
            headless=settings.PLAYWRIGHT_HEADLESS,  # Use setting from .env
            session_id=session_id,  # Reuse existing Selenium session/driver
            job_description=job.description  # Pass job description to AI
        )
        
        # === CLEANUP: Remove temporary enhanced resume file (ephemeral) ===
        if temp_resume_file:
            try:
                temp_resume_file.cleanup()
                logger.info("🧹 Temporary enhanced resume cleaned up (not persisted)")
            except Exception as cleanup_err:
                logger.warning(f"Failed to cleanup temp resume: {cleanup_err}")
        
        # Persist cooldown ONLY if session has critical taint (prevents production breakage from minor issues)
        session_metadata = result.details.get("session", {}) if result.details else {}
        is_critical_taint = session_metadata.get("critical_taint", False)
        taint_reason = session_metadata.get("taint_reason", "unknown")
        
        if is_critical_taint:
            from datetime import timedelta, timezone
            cooldown_hours = session_metadata.get("cooldown_hours", 0.5)  # 30 minutes max
            cooldown_until = datetime.now(timezone.utc) + timedelta(hours=cooldown_hours)
            
            await user_repo.update_session_outcome(
                user_id=user_uuid,
                cooldown_until=cooldown_until,
                last_session_outcome=taint_reason,
            )
            logger.warning(
                f"🚨 CRITICAL taint (reason: {taint_reason}). "
                f"Cooldown enforced until {cooldown_until.isoformat()} ({cooldown_hours:.2f}h)"
            )
        elif session_metadata.get("session_tainted"):
            # Log minor warnings without cooldown
            logger.info(
                f"⚠️  Minor warning (reason: {taint_reason}). "
                f"No cooldown applied - user can continue applying."
            )
        
        # Update job application status in database
        user_job_repo = UserJobRepository(session)
        
        if result.success:
            # Update to APPLIED status
            await user_job_repo.update_status(
                user_id=user_uuid,
                job_id=job_uuid,
                status=ApplicationStatus.APPLIED,
                applied_at=datetime.utcnow()
            )
            await session.commit()
            
            logger.info(f"✅ Successfully applied to {job.title} at {job.company}")
            
            return ApplicationResponse(
                user_id=str(user_uuid),
                job_id=str(job_uuid),
                status="applied",
                message=result.message
            )
        else:
            # Check if job is expired/unavailable
            error_reason = result.details.get("reason", "") if result.details else ""
            if result.error_stage == "easy_apply_button" and error_reason and "job_expired" in error_reason:
                # Update status to EXPIRED when job is no longer available
                await user_job_repo.update_status(
                    user_id=user_uuid,
                    job_id=job_uuid,
                    status=ApplicationStatus.EXPIRED,
                    applied_at=None
                )
                await session.commit()
                
                logger.warning(f"⏳ Job expired/unavailable: {job.title} at {job.company} - Status updated to EXPIRED")
                
                return ApplicationResponse(
                    user_id=str(user_uuid),
                    job_id=str(job_uuid),
                    status="expired",
                    message=f"Job no longer available: {result.message}"
                )
            
            # Keep as PENDING or mark as FAILED
            await session.commit()
            
            logger.error(f"❌ Failed to apply: {result.message} (Stage: {result.error_stage})")
            
            # Return error details
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": result.message,
                    "error_stage": result.error_stage,
                    "job_title": job.title,
                    "company": job.company
                }
            )
    
    except HTTPException:
        # Cleanup temp resume on error
        if temp_resume_file:
            try:
                temp_resume_file.cleanup()
            except Exception:
                pass
        raise
    except Exception as e:
        # Cleanup temp resume on error
        if temp_resume_file:
            try:
                temp_resume_file.cleanup()
            except Exception:
                pass
        logger.error(f"Error in apply_to_single_job: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Application failed: {str(e)}"
        )
