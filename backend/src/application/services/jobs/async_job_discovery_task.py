"""
Async Job Scraping Task
Handles background job discovery without blocking the HTTP request
"""
import asyncio
import json
import random
from uuid import uuid4, UUID
from datetime import datetime
from typing import Optional, Set, List
from sqlalchemy.exc import IntegrityError

from infrastructure.persistence.repositories.job_listing import JobListingRepository
from infrastructure.persistence.repositories.user_job import UserJobRepository
from infrastructure.persistence.repositories.job_filter import JobFilterRepository
from infrastructure.services.ai_match_service import AIMatchService
from infrastructure.services.job_stream_manager import (
    get_stream_manager,
    JobDiscoveryEvent,
    StreamStatusEvent
)
from application.services.jobs.job_scraper_service import JobScraperService
from domain.entities.job_listing import JobListing
from domain.entities.user_job import UserJob
from domain.enums import ApplicationStatus, WorkType
from core.database import AsyncSessionLocal


class AsyncJobDiscoveryTask:
    """
    Background task for discovering jobs asynchronously.
    Scrapes LinkedIn without blocking the initial HTTP request.
    Publishes newly discovered jobs via SSE stream manager.
    """
    
    def __init__(
        self,
        user_id,
        session_id: str,
        user_data: dict,
        job_repo: JobListingRepository,
        user_job_repo: UserJobRepository,
        session,
        task_id: Optional[UUID] = None,
    ):
        """
        Initialize async job discovery task.
        
        Args:
            user_id: User UUID
            session_id: Stream session ID for SSE
            user_data: User preferences and cookies dict
            job_repo: Job repository for database operations
            user_job_repo: User-job repository for link creation
            session: SQLAlchemy async session
            task_id: Optional task ID for filter auditing
        """
        self.user_id = user_id
        self.session_id = session_id
        self.user_data = user_data
        self.job_repo = job_repo
        self.user_job_repo = user_job_repo
        self.session = session
        self.task_id = task_id
        self.stream_manager = get_stream_manager()
        self.scraper = JobScraperService()
        self.filter_repo = JobFilterRepository(session)
        
        # Stats tracking
        self.scraped_count = 0
        self.published_count = 0
        self.skipped_count = 0
    
    async def run(self):
        """
        Execute background job discovery.
        Scrapes jobs, saves to DB, streams new ones to client.
        
        Uses pre-generated LinkedIn URLs from task data (built from user preferences).
        ANTI-429: Staggered job title scraping with 90s gaps minimum.
        """
        try:
            logger.info(f"🚀 Starting async job discovery for user {self.user_id}, session {self.session_id}")
            
            job_titles = self.user_data.get("job_titles", [])
            location = self.user_data.get("location", "Pakistan")
            cookies = self.user_data.get("cookies", [])
            session_id = self.user_data.get("session_id")  # Active Selenium session (if available)
            experience_level = self.user_data.get("experience_level")
            work_type = self.user_data.get("work_type")
            resume_text = self.user_data.get("resume_text", "")
            search_urls = self.user_data.get("search_urls", [])  # Pre-generated URLs
            
            # Log which authentication method is being used
            if session_id:
                logger.info(f"✅ Using active Selenium session: {session_id}")
            elif cookies:
                logger.info(f"✅ Using stored LinkedIn cookies")
            else:
                logger.error("❌ No session or cookies available for scraping")
                return
            
            # Log if pre-generated URLs are available
            if search_urls:
                logger.info(f"✅ Using {len(search_urls)} pre-generated LinkedIn URLs")
            else:
                logger.warning("⚠ No pre-generated URLs found, will build URLs dynamically")
            
            # Initialize AI match service if resume available
            ai_match_service = None
            if resume_text:
                try:
                    ai_match_service = AIMatchService()
                except Exception as e:
                    logger.warning(f"Failed to initialize AI Match Service: {e}")
            
            # OPTIMIZATION: Pre-load ALL existing external IDs from database
            # This prevents duplicate scraping and expensive DB queries later
            existing_external_ids = await self._get_existing_external_ids()
            logger.info(f"📋 Pre-loaded {len(existing_external_ids)} existing job IDs from database")
            
            processed_external_ids: Set[str] = set()
            
            # Anti-429: Track consecutive rate limits
            consecutive_rate_limits = 0
            rate_limit_threshold = 3
            
            # Scrape for each job title
            for idx, title in enumerate(job_titles, 1):
                logger.info(f"[{idx}/{len(job_titles)}] Scraping '{title}'...")
                
                # Get pre-generated URL for this job title (if available)
                search_url = None
                if search_urls:
                    for url_data in search_urls:
                        if url_data.get("job_title") == title:
                            search_url = url_data.get("url")
                            logger.info(f"✅ Using pre-generated URL: {search_url}")
                            break
                
                try:
                    # Scrape jobs with pre-generated URL (or fallback to parameters)
                    if search_url:
                        # Use pre-generated URL
                        jobs_data, fresh_cookies, filter_verification = self.scraper.scrape_jobs_by_url(
                            search_url=search_url,
                            cookies=cookies
                        )
                    else:
                        # Fallback: Build URL dynamically in scraper using session_id
                        jobs_data = self.scraper.scrape_jobs(
                            job_title=title,
                            location=location,
                            # Use the Selenium session_id from user_data, not the SSE stream session_id
                            session_id=self.user_data.get("session_id"),
                            experience_level=experience_level,
                            work_type=work_type,
                            easy_apply=True,
                            current_job_id=None
                        )
                        fresh_cookies = cookies  # Keep for backward compat
                        filter_verification = {}  # No filter verification from direct scrape
                    
                    # Store applied filters in audit trail
                    await self._store_filter_audit(
                        job_title=title,
                        search_url=search_url,
                        filter_verification=filter_verification
                    )
                    
                    self.scraped_count += len(jobs_data)
                    
                    # Check if no jobs were found (empty list returned)
                    if len(jobs_data) == 0:
                        logger.warning(f"⚠ No matching jobs found for '{title}' in '{location}'")
                        
                        # Send notification to user via SSE stream
                        await self.stream_manager.send_event(
                            self.session_id,
                            StreamStatusEvent(
                                type="no_jobs",
                                message=f"No matching jobs found for role: {title}",
                                data={
                                    "job_title": title,
                                    "location": location,
                                    "reason": "no_matching_jobs"
                                }
                            )
                        )
                        
                        # Update cookies if available
                        if fresh_cookies:
                            self.user_data["cookies"] = fresh_cookies
                        
                        # Continue to next title
                        continue
                    
                    logger.info(f"Scraped {len(jobs_data)} jobs for '{title}'")
                    
                    # Update cookies if fresh ones received
                    if fresh_cookies:
                        self.user_data["cookies"] = fresh_cookies
                    
                    # Reset rate limit counter on successful scrape
                    consecutive_rate_limits = 0
                    
                    # Process each job (with existing_external_ids for fast duplicate check)
                    for job_data in jobs_data:
                        # Extract page number from job data (set by scraper)
                        page_number = job_data.get("page_number", 1)
                        await self._process_and_publish_job(
                            job_data,
                            processed_external_ids,
                            existing_external_ids,
                            ai_match_service,
                            page_number=page_number  # Pass page number from scraper
                        )
                
                except Exception as e:
                    error_str = str(e).lower()
                    
                    # Detect rate limit errors (429, rate limit, too many requests)
                    if "429" in error_str or "rate" in error_str or "too many" in error_str:
                        consecutive_rate_limits += 1
                        logger.error(
                            f"❌ Rate limit detected for '{title}' "
                            f"(consecutive: {consecutive_rate_limits}/{rate_limit_threshold})"
                        )
                        
                        if consecutive_rate_limits >= rate_limit_threshold:
                            logger.critical(
                                f"🚫 CIRCUIT BREAKER: {consecutive_rate_limits} consecutive rate limits! "
                                f"Stopping job discovery. Please try again in 1+ hours."
                            )
                            await self.stream_manager.send_event(
                                self.session_id,
                                StreamStatusEvent(
                                    type="error",
                                    message=f"Rate limited after {consecutive_rate_limits} attempts. Stopping.",
                                    data={"error_type": "rate_limit"}
                                )
                            )
                            break
                        
                        # Wait exponentially before next title
                        backoff_time = 2 ** consecutive_rate_limits  # 2s, 4s, 8s
                        backoff_time = min(backoff_time, 300)  # Cap at 5 minutes
                        logger.warning(
                            f"Waiting {backoff_time:.0f}s before next title due to rate limit..."
                        )
                        await asyncio.sleep(backoff_time)
                    else:
                        # Non-rate-limit error
                        consecutive_rate_limits = 0
                        logger.error(f"Error scraping jobs for '{title}': {e}")
                    
                    # Continue with next title
                    continue
            
            # Complete the stream
            await self.stream_manager.complete_stream(self.session_id)
            
            logger.info(
                f"✅ Job discovery complete for session {self.session_id}\n"
                f"  Scraped: {self.scraped_count}\n"
                f"  Published: {self.published_count}\n"
                f"  Skipped: {self.skipped_count}"
            )
            
        except Exception as e:
            logger.error(f"💥 Fatal error in async job discovery: {e}")
            await self.stream_manager.complete_stream(self.session_id)
    
    async def _get_existing_external_ids(self) -> Set[str]:
        """
        Pre-load all existing LinkedIn job external IDs from database.
        This allows fast in-memory duplicate checking without DB queries.
        Uses a fresh session to avoid interfering with the main transaction.
        
        Returns:
            Set of external IDs already in database
        """
        fresh_session = None
        try:
            # Create a fresh session for this read operation
            fresh_session = AsyncSessionLocal()
            fresh_repo = JobListingRepository(fresh_session)
            existing_ids = await fresh_repo.get_all_external_ids_by_platform("linkedin")
            return existing_ids
        except Exception as e:
            logger.warning(f"Failed to pre-load existing job IDs: {e}")
            return set()
        finally:
            # Always close the fresh session
            if fresh_session:
                try:
                    await fresh_session.close()
                except:
                    pass
    
    async def _store_filter_audit(
        self,
        job_title: str,
        search_url: Optional[str],
        filter_verification: dict
    ) -> None:
        """
        Store filter verification results in job_filters table for auditing
        
        Args:
            job_title: Job title that was searched
            search_url: LinkedIn search URL used
            filter_verification: Dictionary with verification results from _verify_filters_applied
        """
        try:
            if not filter_verification:
                logger.debug("No filter verification results to store")
                return
            
            # Create filter records for each verified filter
            filters_to_store = []
            
            for filter_name, verification_result in filter_verification.items():
                expected = verification_result.get("expected")
                verified = verification_result.get("verified")
                found = verification_result.get("found")
                
                # Determine verification status
                status = "verified" if verified else "failed"
                
                filters_to_store.append({
                    "filter_name": filter_name,
                    "filter_value": str(expected) if expected else "unknown",
                    "verified": status
                })
                
                logger.debug(f"Filter audit: {filter_name}={expected} -> {status} (found: {found})")
            
            # Store all filters in bulk
            if filters_to_store:
                await self.filter_repo.create_bulk(
                    user_id=self.user_id,
                    filters=filters_to_store,
                    task_id=self.task_id,
                    search_url=search_url,
                    job_title=job_title
                )
                
                verified_count = sum(1 for f in filters_to_store if f.get("verified") == "verified")
                logger.info(f"✅ Stored {len(filters_to_store)} filter audit records ({verified_count} verified)")
                
                # Commit filter audit records
                await self.session.commit()
            
        except Exception as e:
            logger.error(f"Error storing filter audit: {e}")
            # Don't fail the whole task if filter audit fails
            try:
                await self.session.rollback()
            except:
                pass
    
    async def _process_and_publish_job(
        self,
        job_data: dict,
        processed_ids: Set[str],
        existing_ids: Set[str],
        ai_match_service: Optional[AIMatchService],
        page_number: int = 1
    ):
        """
        Process a single job and publish it if new.
        
        Job data expected fields (from structured parsing):
        - title: Job title
        - company: Company name
        - location: Job location
        - description: Job description
        - apply_url: Direct apply link with currentJobId
        - job_id: LinkedIn external job ID
        - easy_apply: Whether job has easy apply
        
        Duplicate Detection Strategy:
        1. Session check: processed_ids (fast memory check)
        2. DB check via index: exists_by_external_id() (O(1) via external_id index)
        3. Skip if either check passes
        
        Args:
            job_data: Raw job data from scraper
            processed_ids: Set of already processed external IDs in this session
            existing_ids: Set of IDs pre-loaded from database (optional fallback)
            ai_match_service: AI service for match scoring
            page_number: Which page this job was found on (for audit trail)
        """
        try:
            # Use job_id from structured parsing (data-job-id attribute)
            external_id = job_data.get("job_id") or job_data.get("external_id")
            if not external_id:
                self.skipped_count += 1
                logger.debug("Job has no external_id, skipping")
                return
            
            # Check 1: Skip if already processed in this session
            if external_id in processed_ids:
                self.skipped_count += 1
                logger.debug(f"Skipping duplicate job {external_id} (already processed this session)")
                return
            
            processed_ids.add(external_id)
            
            # Check 2: Check database for duplicate via indexed external_id (O(1) lookup)
            # This is the authoritative check - database is source of truth
            if await self.job_repo.exists_by_external_id(external_id, platform="linkedin"):
                self.skipped_count += 1
                logger.debug(f"Skipping duplicate job {external_id} (already exists in database)")
                return
            
            # Check 2.5: Check database for duplicate via URL
            apply_url = job_data.get("apply_url", "").strip()
            if apply_url and await self.job_repo.exists_by_url(apply_url, platform="linkedin"):
                self.skipped_count += 1
                logger.debug(f"Skipping duplicate job {external_id} (URL already exists in database)")
                return
            
            # Check 3: Check for content duplicate (same title, company, description)
            # This catches jobs that may have different external_ids but are the same job
            title = job_data.get("title", "").strip()
            company = job_data.get("company", "").strip()
            description = job_data.get("description", "").strip()
            
            existing_duplicate = await self.job_repo.find_duplicate_by_content(
                title=title,
                company=company, 
                description=description,
                platform="linkedin"
            )
            if existing_duplicate:
                self.skipped_count += 1
                logger.debug(f"Skipping content duplicate job {external_id} (matches existing job {existing_duplicate.id})")
                return
            
            # Apply filters: Easy Apply required
            if not job_data.get("easy_apply", False):
                self.skipped_count += 1
                logger.debug(f"Skipping non-Easy Apply job {external_id}")
                return
            
            # Skip already applied jobs
            if job_data.get("already_applied", False):
                self.skipped_count += 1
                logger.debug(f"Skipping already applied job {external_id}")
                return
            
            # Skip jobs no longer accepting applications
            if job_data.get("no_longer_accepting", False):
                self.skipped_count += 1
                logger.debug(f"Skipping job no longer accepting applications {external_id}")
                return
            
            # Validate description completeness
            if not description or description.lower() == "about the job":
                self.skipped_count += 1
                logger.debug(f"Skipping job with incomplete description {external_id}")
                return
            
            # At this point, it's a NEW job - create it
            wt = None
            if job_data.get("work_type"):
                try:
                    wt = WorkType(job_data.get("work_type"))
                except:
                    pass
            
            # Normalize URL by removing query parameters
            from urllib.parse import urlparse
            apply_url = job_data.get("apply_url", "")
            parsed = urlparse(apply_url)
            normalized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            
            new_job = JobListing(
                id=uuid4(),
                external_id=external_id,
                platform="linkedin",
                title=job_data.get("title", ""),
                company=job_data.get("company", ""),
                location=job_data.get("location", ""),
                description=description,
                url=normalized_url,  # Use normalized URL
                apply_link=apply_url,  # Keep original apply link
                easy_apply=True,
                salary_range=None,
                work_type=wt,
                posted_date=None,
                page_number=job_data.get("page_number", page_number),  # Prefer data from scraper
                scraped_at=job_data.get("scraped_at") or datetime.utcnow(),  # Prefer scraper timestamp
                last_seen_at=datetime.utcnow()
            )
            
            created_job = await self.job_repo.create(new_job)
            job_id = created_job.id
            
            # Update in-memory set if using fallback strategy
            if external_id in existing_ids:
                existing_ids.add(external_id)
            
            logger.info(f"Created new job {external_id}: {job_data.get('title')}")
            
            # Calculate match score
            match_score = None
            if ai_match_service and self.user_data.get("resume_text"):
                try:
                    # Need to fetch the job for AI scoring
                    job = await self.job_repo.get_by_id(job_id)
                    match_score_result = await ai_match_service.calculate_match_score(
                        self.user_data["resume_text"],
                        job
                    )
                    match_score = match_score_result.value
                except Exception as e:
                    logger.warning(f"Failed to calculate match score: {e}")
            
            # Create user-job link if doesn't exist with status=PENDING
            try:
                existing_user_job = await self.user_job_repo.get_by_user_and_job(self.user_id, job_id)
                
                if not existing_user_job:
                    user_job = UserJob(
                        id=uuid4(),
                        user_id=self.user_id,
                        job_id=job_id,
                        match_score=match_score or 0,
                        status=ApplicationStatus.PENDING  # Status is PENDING for newly discovered jobs
                    )
                    await self.user_job_repo.create(user_job)
                    logger.debug(f"Created user-job link for {job_id} with status=PENDING")
                else:
                    logger.debug(f"User-job link already exists for {job_id}")
            except IntegrityError as e:
                if "uq_user_jobs_user_id_job_id" in str(e):
                    logger.debug(f"User-job link already exists for {job_id} (caught duplicate)")
                else:
                    logger.warning(f"Integrity error creating user-job link for {job_id}: {e}")
                    raise
            except Exception as e:
                logger.warning(f"Error creating user-job link for {job_id}: {e}")
                raise
            
            # Publish to stream
            event = JobDiscoveryEvent(
                job_id=str(job_id),
                title=job_data.get("title", ""),
                company=job_data.get("company", ""),
                location=job_data.get("location", ""),
                description=description,
                url=job_data.get("apply_url", ""),
                work_type=job_data.get("work_type"),
                salary_min=job_data.get("salary_min"),
                salary_max=job_data.get("salary_max"),
                match_score=match_score
            )
            
            await self.stream_manager.publish_job(self.session_id, event)
            self.published_count += 1
            logger.info(f"Published job to stream: {job_data.get('title')}")
            
            # Commit after each job
            await self.session.commit()
        
        except Exception as e:
            logger.error(f"Error processing job {job_data.get('job_id')}: {e}")
            self.skipped_count += 1


def create_async_job_discovery_task(
    user_id,
    session_id: str,
    user_data: dict,
    job_repo: JobListingRepository,
    user_job_repo: UserJobRepository,
    session,
    task_id: Optional[UUID] = None
) -> AsyncJobDiscoveryTask:
    """Factory function to create async job discovery task"""
    return AsyncJobDiscoveryTask(
        user_id=user_id,
        session_id=session_id,
        user_data=user_data,
        job_repo=job_repo,
        user_job_repo=user_job_repo,
        session=session,
        task_id=task_id
    )
