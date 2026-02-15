"""
Task Worker - Background worker for processing queued tasks
Processes job scraping and application tasks from the ApplyQueue
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from core.config import settings
from core.database import AsyncSessionLocal
from infrastructure.persistence.repositories.apply_queue import ApplyQueueRepository
from infrastructure.persistence.repositories.job_listing import JobListingRepository
from infrastructure.persistence.repositories.user_job import UserJobRepository
from infrastructure.persistence.repositories.session import SessionRepository
from infrastructure.persistence.models.apply_queue import TaskType, TaskStatus
from infrastructure.persistence.models.session import SessionStatus
from application.repositories.interfaces import IUserRepository
from infrastructure.persistence.repositories.user import UserRepository
from application.services.jobs.job_scraper_service import JobScraperService
from application.services.jobs.single_job_applier import SingleJobApplier
from application.services.linkedin_session_manager import get_session_manager
from application.services.session_health_checker import get_session_health_checker
from infrastructure.services.ai_match_service import AIMatchService
from domain.entities.job_listing import JobListing
from domain.entities.user_job import UserJob
from domain.enums import ApplicationStatus, WorkType


class TaskWorker:
    """Background worker for processing async tasks"""
    
    def __init__(self, poll_interval: int = 5, max_concurrent_tasks: int = 3):
        """
        Initialize task worker
        
        Args:
            poll_interval: Seconds between checking for new tasks
            max_concurrent_tasks: Maximum number of tasks to process concurrently
        """
        self.poll_interval = poll_interval
        self.max_concurrent_tasks = max_concurrent_tasks
        self.running = False
        self.active_tasks = set()

    async def start(self):
        """Start the background worker"""
        self.running = True
        logger.info(f"🚀 Task worker started (poll_interval={self.poll_interval}s, max_concurrent={self.max_concurrent_tasks})")
        
        try:
            while self.running:
                await self._process_tasks()
                await asyncio.sleep(self.poll_interval)
        except Exception as e:
            logger.error(f"❌ Task worker crashed: {e}")
            raise
        finally:
            logger.info("🛑 Task worker stopped")

    async def stop(self):
        """Stop the background worker"""
        logger.info("Stopping task worker...")
        self.running = False
        
        # Wait for active tasks to complete
        if self.active_tasks:
            logger.info(f"Waiting for {len(self.active_tasks)} active tasks to complete...")
            await asyncio.gather(*self.active_tasks, return_exceptions=True)

    async def _process_tasks(self):
        """Check for and process pending tasks"""
        async with AsyncSessionLocal() as session:
            try:
                queue_repo = ApplyQueueRepository(session)
                
                # Get pending tasks (limited by max concurrent)
                available_slots = self.max_concurrent_tasks - len(self.active_tasks)
                if available_slots <= 0:
                    return
                
                pending_tasks = await queue_repo.get_pending_tasks(limit=available_slots)
                
                if not pending_tasks:
                    return
                
                logger.info(f"📋 Found {len(pending_tasks)} pending task(s)")
                
                # Process each task
                for task in pending_tasks:
                    # Mark as processing
                    await queue_repo.mark_processing(task.id)
                    await session.commit()
                    
                    # Create async task for processing
                    task_coro = self._process_single_task(
                        task.id,
                        task.task_type,
                        task.user_id,
                        task.progress_data,
                        task.job_url,
                        task.job_id,
                        task.session_id,
                    )
                    asyncio_task = asyncio.create_task(task_coro)
                    self.active_tasks.add(asyncio_task)
                    
                    # Remove from active set when done
                    asyncio_task.add_done_callback(lambda t: self.active_tasks.discard(t))
                    
            except Exception as e:
                logger.error(f"Error in _process_tasks: {e}")

    async def _process_single_task(self, task_id: UUID, task_type: TaskType, user_id: UUID, progress_data: Optional[str], job_url: Optional[str], job_id: Optional[UUID], session_id: Optional[str]):
        """Process a single task with session tracking and cleanup"""
        logger.info(f"🔄 Starting task {task_id}")
        logger.info(f"   Type: {task_type.value}")
        logger.info(f"   User: {user_id}")
        logger.info(f"   Job ID: {job_id or 'N/A'}")
        logger.info(f"   Session: {session_id or 'N/A'}")
        logger.info(f"   Job URL: {job_url or 'N/A'}")
        
        db_session_id: Optional[str] = None
        session_manager = get_session_manager()
        task_success = False
        
        async with AsyncSessionLocal() as session:
            try:
                queue_repo = ApplyQueueRepository(session)
                session_repo = SessionRepository(session)
                
                # Create or get a tracking record for this session
                if not session_id:
                    # Generate new session_id for tracking
                    session_id = f"task_{task_id}_{datetime.now(timezone.utc).isoformat()}"
                
                # Create database session record
                db_session = await session_repo.create_session(
                    session_id=session_id,
                    user_id=user_id,
                    browser_type="chrome",
                    headless=True
                )
                db_session_id = session_id
                await session.commit()
                logger.info(f"📝 Created session record: {db_session_id}")
                
                # Mark session as in use for this task
                await session_repo.mark_session_in_use(session_id, task_id)
                await session.commit()
                
                if task_type == TaskType.JOB_SCRAPING:
                    await self._process_job_scraping(task_id, user_id, progress_data, session, queue_repo)
                elif task_type == TaskType.JOB_APPLICATION:
                    await self._process_job_application(task_id, user_id, job_url, job_id, session_id, session, queue_repo)
                else:
                    logger.warning(f"Unknown task type: {task_type}")
                    await queue_repo.mark_failed(task_id, f"Unknown task type: {task_type}")
                    await session.commit()
                
                # Mark task as successful for cleanup phase
                task_success = True
                
                # Mark session as idle on success and prepare for disposal
                if db_session_id:
                    async with AsyncSessionLocal() as cleanup_session:
                        cleanup_repo = SessionRepository(cleanup_session)
                        await cleanup_repo.mark_session_idle(db_session_id)
                        await cleanup_repo.increment_task_count(db_session_id)
                        await cleanup_session.commit()
                    logger.info(f"✅ Session {db_session_id} marked idle, task count incremented")
                    
            except Exception as e:
                logger.error(f"❌ Task {task_id} failed: {e}")
                logger.error(f"   Task Type: {task_type.value}")
                logger.error(f"   User: {user_id}")
                
                error_message = str(e)
                error_type = type(e).__name__
                health_checker = get_session_health_checker()
                health_issue = None
                cooldown_seconds = None
                
                # Check session health
                if settings.SESSION_HEALTH_CHECK_ENABLED and settings.SESSION_HEALTH_CHECK_ON_ERROR:
                    health_issue = health_checker.check_health(error_message, error_type)
                    if health_issue:
                        cooldown_seconds = health_checker.get_cooldown_duration_seconds(health_issue)
                        issue_description = health_checker.get_issue_description(health_issue)
                        logger.warning(f"⚠️  Session health issue detected: {issue_description}")
                
                # Update session with error info
                if db_session_id:
                    async with AsyncSessionLocal() as error_session:
                        error_repo = SessionRepository(error_session)
                        
                        # Record health check event
                        if health_issue:
                            await error_repo.record_health_check(
                                db_session_id,
                                issue_type=health_issue.value,
                                description=health_checker.get_issue_description(health_issue)
                            )
                        
                        # Mark session as tainted if health issue detected
                        if health_issue and settings.SESSION_MARK_TAINTED_ON_HEALTH_ISSUE:
                            await error_repo.mark_session_tainted(
                                db_session_id,
                                issue_type=health_issue.value,
                                reason="health_check_failed"
                            )
                            logger.error(f"🏴 Session {db_session_id} marked as TAINTED (issue: {health_issue.value})")
                        else:
                            await error_repo.update_session_status(
                                db_session_id,
                                SessionStatus.FAILED,
                                error_message=error_message,
                                error_type=error_type
                            )
                        
                        await error_session.commit()
                    logger.error(f"⚠️ Session {db_session_id} updated with error info")
                
                # Retry with cooldown if health issue detected, otherwise exponential backoff
                async with AsyncSessionLocal() as retry_session:
                    retry_repo = ApplyQueueRepository(retry_session)
                    
                    if health_issue and cooldown_seconds:
                        # Health check triggered retry with longer cooldown
                        updated_task = await retry_repo.enqueue_health_check_retry(
                            task_id,
                            issue_type=health_issue.value,
                            cooldown_seconds=cooldown_seconds,
                            error_message=health_checker.get_issue_description(health_issue)
                        )
                    else:
                        # Standard exponential backoff retry
                        updated_task = await retry_repo.increment_retry(task_id, error_message)
                    
                    await retry_session.commit()
                    
                    # Log retry info
                    if updated_task and updated_task.status == TaskStatus.PENDING:
                        delay = 2 ** updated_task.retries if not health_issue else cooldown_seconds
                        retry_reason = f"health issue ({health_issue.value})" if health_issue else "error"
                        logger.info(f"🔄 Task {task_id} will retry in {delay}s (attempt {updated_task.retries}/{updated_task.max_retries}) [{retry_reason}]")
                        if updated_task.session_id:
                            logger.info(f"   Session: {updated_task.session_id}")
                    elif updated_task and updated_task.status == TaskStatus.FAILED:
                        logger.error(f"💀 Task {task_id} failed permanently after {updated_task.retries} retries")
                        if updated_task.error_log:
                            logger.error(f"   Error history: {updated_task.error_log}")
            finally:
                # Always dispose Selenium session and mark as DISPOSED in database
                if db_session_id:
                    try:
                        # Dispose Selenium browser in LinkedInSessionManager
                        reason = "task_completed" if task_success else "task_failed"
                        disposed = session_manager.dispose_session(db_session_id, reason)
                        if disposed:
                            logger.info(f"🧹 Selenium session {db_session_id} disposed ({reason})")
                        
                        # Mark session as DISPOSED in database
                        async with AsyncSessionLocal() as dispose_session:
                            dispose_repo = SessionRepository(dispose_session)
                            await dispose_repo.dispose_session(db_session_id, reason)
                            await dispose_session.commit()
                        logger.info(f"✅ Session {db_session_id} marked DISPOSED in database")
                    except Exception as cleanup_error:
                        logger.error(f"❌ Error during session cleanup: {cleanup_error}")

    async def _process_job_scraping(self, task_id: UUID, user_id: UUID, progress_data: Optional[str], session: AsyncSession, queue_repo: ApplyQueueRepository):
        """
        Process a job scraping task using Selenium
        
        Steps:
        1. Load user session and LinkedIn cookies
        2. Initialize Selenium WebDriver with cookies
        3. Navigate to LinkedIn job search with filters
        4. Parse job cards from search results
        5. Save jobs to job_listings table
        6. Update user session with fresh cookies
        7. Create user-job links with match scores
        """
        try:
            # Parse progress data
            if not progress_data:
                raise ValueError("No progress data found for job scraping task")
            
            params = json.loads(progress_data)
            job_titles = params.get("job_titles", [])
            location = params.get("location", "")
            experience_level = params.get("experience_level")
            work_type = params.get("work_type")
            
            if not job_titles:
                raise ValueError("No job titles found in task parameters")
            
            logger.info(f"📝 Starting job scraping task for user {user_id}")
            logger.info(f"   Job titles: {job_titles}")
            logger.info(f"   Location: {location}")
            logger.info(f"   Experience: {experience_level}")
            logger.info(f"   Work type: {work_type}")
            
            # Update progress
            await queue_repo.update_progress(task_id, "Loading user session")
            await session.commit()
            
            # Get user and LinkedIn session
            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(user_id)
            
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            # Require active Selenium session (no cookie fallback)
            session_manager = get_session_manager()
            active_sessions = session_manager.get_user_active_sessions(user_id)
            
            if not active_sessions:
                raise ValueError(f"No active Selenium sessions for user {user_id}. User must login with live session first.")
            
            # Use first available active session
            selenium_session = active_sessions[0]
            session_id = selenium_session.session_id
            
            # Verify session is IN_USE or IDLE (not TAINTED, FAILED, DISPOSED)
            if not session_id:
                raise ValueError("Invalid session: missing session_id")
            
            # Update task with session_id
            await queue_repo.update_session_id(task_id, session_id)
            await session.commit()
            logger.info(f"🔑 Using Selenium session: {session_id}")
            logger.info(f"   Session status: {selenium_session.status}")
            logger.info(f"   Session tasks completed: {selenium_session.tasks_completed}")
            
            # Initialize repositories
            job_repo = JobListingRepository(session)
            user_job_repo = UserJobRepository(session)
            
            # Get existing job IDs to avoid duplicates
            await queue_repo.update_progress(task_id, "Checking for existing jobs")
            await session.commit()
            
            existing_ids = await job_repo.get_all_external_ids_by_platform("linkedin")
            logger.info(f"📊 Found {len(existing_ids)} existing jobs in database")
            
            # Prepare AI match service
            await queue_repo.update_progress(task_id, "Preparing AI match service")
            await session.commit()
            
            resume_text = ""
            if user.resume_parsed_data:
                parsed = user.resume_parsed_data
                if isinstance(parsed, str):
                    try:
                        parsed = json.loads(parsed)
                    except:
                        pass
                
                if isinstance(parsed, dict):
                    parts = []
                    if parsed.get("summary"):
                        parts.append(parsed["summary"])
                    if parsed.get("skills"):
                        parts.append(f"Skills: {', '.join(parsed['skills'])}")
                    if parsed.get("experience"):
                        exp_text = " ".join([f"{exp.get('title', '')} at {exp.get('company', '')}" for exp in parsed.get("experience", [])])
                        parts.append(exp_text)
                    resume_text = " ".join(parts)
            
            ai_match_service = None
            if resume_text:
                ai_match_service = AIMatchService()
                logger.info("✅ AI match service initialized")
            else:
                logger.warning("⚠️  No resume data found, match scores will be unavailable")
            
            # Process each job title with Selenium scraper
            total_jobs_discovered = 0
            total_jobs_saved = 0
            
            for idx, job_title in enumerate(job_titles, 1):
                await queue_repo.update_progress(task_id, f"Scraping [{idx}/{len(job_titles)}]: {job_title}")
                await session.commit()
                
                logger.info(f"🔍 [{idx}/{len(job_titles)}] Scraping LinkedIn for: {job_title}")
                
                try:
                    # Initialize Selenium scraper
                    scraper = JobScraperService()
                    
                    # Scrape jobs using Selenium with session cookies
                    jobs_data = scraper.scrape_jobs(
                        job_title=job_title,
                        location=location,
                        session_id=session_id,  # Use Selenium session instead of cookies
                        experience_level=experience_level,
                        work_type=work_type,
                        easy_apply=True,
                        max_pages=1,  # Process one page at a time to avoid timeouts
                        page_load_timeout=60,
                        script_timeout=120
                    )
                    
                    logger.info(f"✅ Scraped {len(jobs_data)} jobs for '{job_title}'")
                    total_jobs_discovered += len(jobs_data)
                    
                    # Process and save each job to database
                    await queue_repo.update_progress(task_id, f"Processing {len(jobs_data)} jobs from '{job_title}'")
                    await session.commit()
                    
                    for job_idx, job_data in enumerate(jobs_data, 1):
                        try:
                            external_id = job_data.get("external_id")
                            
                            if not external_id:
                                logger.warning(f"Skipping job without external_id")
                                continue
                            
                            # Skip duplicates
                            if external_id in existing_ids:
                                logger.debug(f"Job {external_id} already exists, skipping")
                                continue
                            
                            # Create job listing entity
                            job_entity = JobListing(
                                id=None,
                                external_id=external_id,
                                platform="linkedin",
                                title=job_data.get("title", "").strip(),
                                company=job_data.get("company", "").strip(),
                                location=job_data.get("location", location).strip(),
                                description=job_data.get("description", "").strip(),
                                url=job_data.get("url", ""),
                                salary_range=None,
                                work_type=WorkType(job_data.get("work_type")) if job_data.get("work_type") else None,
                                posted_date=None,
                                first_seen_at=None,
                                last_seen_at=None
                            )
                            
                            # Validate job data
                            if not job_entity.title or not job_entity.company:
                                logger.warning(f"Skipping job {external_id}: missing title or company")
                                continue
                            
                            # Save job listing to database
                            saved_job = await job_repo.create(job_entity)
                            existing_ids.add(external_id)
                            total_jobs_saved += 1
                            
                            # Calculate AI match score
                            match_score = None
                            if ai_match_service and resume_text:
                                try:
                                    match_score = await ai_match_service.calculate_match_score(
                                        job_description=job_data.get("description", ""),
                                        resume_text=resume_text
                                    )
                                    logger.debug(f"Match score for {job_entity.title}: {match_score}")
                                except Exception as e:
                                    logger.warning(f"Failed to calculate match score: {e}")
                            
                            # Create user-job link
                            try:
                                # Check if user-job link already exists
                                existing_user_job = await user_job_repo.get_by_user_and_job(user_id, saved_job.id)
                                
                                if not existing_user_job:
                                    user_job = UserJob(
                                        id=None,
                                        user_id=user_id,
                                        job_id=saved_job.id,
                                        status=ApplicationStatus.PENDING,
                                        match_score=match_score,
                                        applied_at=None,
                                        responded_at=None,
                                        interview_scheduled_at=None,
                                        rejected_at=None,
                                        offer_received_at=None
                                    )
                                    
                                    await user_job_repo.create(user_job)
                                    logger.debug(f"✅ [{job_idx}/{len(jobs_data)}] Saved: {job_entity.title} @ {job_entity.company} (match: {match_score})")
                                else:
                                    logger.debug(f"User-job link already exists for {saved_job.id}")
                            except IntegrityError as e:
                                if "uq_user_jobs_user_id_job_id" in str(e):
                                    logger.debug(f"User-job link already exists for {saved_job.id} (caught duplicate)")
                                else:
                                    logger.warning(f"Integrity error creating user-job link for {saved_job.id}: {e}")
                                    raise
                            except Exception as e:
                                logger.warning(f"Error creating user-job link for {saved_job.id}: {e}")
                                raise
                            
                            # Batch commit every 10 jobs for performance
                            if job_idx % 10 == 0:
                                await session.commit()
                            
                        except Exception as e:
                            logger.warning(f"Failed to process job {job_data.get('external_id', 'unknown')}: {e}")
                            continue
                    
                    # Commit remaining jobs
                    await session.commit()
                    logger.info(f"💾 Saved {total_jobs_saved} new jobs from '{job_title}'")
                    
                except Exception as e:
                    logger.error(f"Failed to scrape '{job_title}': {e}")
                    # Continue with next job title instead of failing entire task
                    continue
            
            # Update user session with fresh cookies
            if fresh_cookies and fresh_cookies != cookies:
                await queue_repo.update_progress(task_id, "Updating LinkedIn session")
                await session.commit()
                
                try:
                    cipher = BaselineCookieCipher()
                    fresh_profile = {"cookies": fresh_cookies}
                    encrypted_profile = cipher.encrypt_profile(fresh_profile)
                    await user_repo.update_persistent_browser_profile(user_id, encrypted_profile)
                    await session.commit()
                    logger.info("✅ Updated user session with fresh LinkedIn cookies")
                except Exception as e:
                    logger.warning(f"Failed to update session cookies: {e}")
            
            # Mark task as completed (logs duration automatically)
            await queue_repo.mark_completed(task_id)
            await session.commit()
            
            logger.info(f"✅ Task {task_id} completed successfully")
            logger.info(f"   👤 User: {user_id}")
            logger.info(f"   🔑 Session: {session_id}")
            logger.info(f"   📊 Total jobs discovered: {total_jobs_discovered}")
            logger.info(f"   💾 New jobs saved: {total_jobs_saved}")
            logger.info(f"   🔁 Duplicate jobs skipped: {total_jobs_discovered - total_jobs_saved}")
            
        except Exception as e:
            logger.error(f"❌ Job scraping task {task_id} failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    async def _process_job_application(
        self,
        task_id: UUID,
        user_id: UUID,
        job_url: Optional[str],
        job_id: Optional[UUID],
        session_id: Optional[str],
        session: AsyncSession,
        queue_repo: ApplyQueueRepository,
    ):
        """
        Process a job application task using session-based Easy Apply
        
        Steps:
        1. Retrieve LinkedIn session from manager
        2. Get user and job details
        3. Apply to job using SingleJobApplier with session
        4. Update job application status in database
        5. Dispose of session
        6. Handle errors and retries
        """
        session_manager = None
        driver = None
        
        try:
            if not job_url:
                raise ValueError("No job URL provided for application task")
            
            if not job_id:
                raise ValueError("No job ID provided for application task")
            
            if not session_id:
                raise ValueError("No session ID provided for application task")
            
            logger.info(f"📝 Processing job application task")
            logger.info(f"   Job ID: {job_id}")
            logger.info(f"   Job URL: {job_url}")
            logger.info(f"   Session: {session_id}")
            
            # Update progress
            await queue_repo.update_progress(task_id, "Retrieving LinkedIn session")
            await session.commit()
            
            # Get session from manager
            from application.services.linkedin_session_manager import get_session_manager
            session_manager = get_session_manager()
            
            linkedin_session = session_manager.get_session(session_id)
            if not linkedin_session:
                raise ValueError(f"LinkedIn session not found or expired: {session_id}")
            
            logger.info(f"✅ Retrieved LinkedIn session {session_id}")
            
            # Mark session as in use
            linkedin_session.start_task("job_application")
            driver = linkedin_session.driver
            
            # Get user and job details
            await queue_repo.update_progress(task_id, "Loading user and job details")
            await session.commit()
            
            user_repo = UserRepository(session)
            job_repo = JobListingRepository(session)
            user_job_repo = UserJobRepository(session)
            
            user = await user_repo.get_by_id(user_id)
            if not user:
                raise ValueError(f"User not found: {user_id}")
            
            job = await job_repo.get_by_id(job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")
            
            # Get resume text for AI form filling
            resume_text = ""
            if user.resume_parsed_data:
                try:
                    import json as json_lib
                    resume_data = (
                        json_lib.loads(user.resume_parsed_data)
                        if isinstance(user.resume_parsed_data, str)
                        else user.resume_parsed_data
                    )
                    
                    # Combine resume sections
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
                        resume_text += f"Skills: {', '.join(resume_data.get('skills', []))}\n"
                    
                except Exception as e:
                    logger.warning(f"Could not parse resume data: {e}")
            
            if not resume_text:
                resume_text = f"Name: {user.full_name}\nEmail: {user.email}\n"
            
            logger.info(f"Resume text length: {len(resume_text)} characters")
            
            # Generate AI form responses for Easy Apply questions
            await queue_repo.update_progress(task_id, "Generating AI form responses")
            await session.commit()
            
            ai_responses = {}
            try:
                from application.services.jobs.ai_form_filling_service import get_ai_form_filling_service
                
                ai_service = get_ai_form_filling_service()
                
                # Prepare resume context
                ai_service.prepare_resume_context(user)
                
                # Generate responses for common Easy Apply questions
                common_questions = [
                    ("1", "Why are you interested in this role?"),
                    ("2", "Describe your experience with the key technologies/skills for this role."),
                    ("3", "What interests you about our company?"),
                ]
                
                # Generate batch answers using AI (80% more efficient than per-question)
                ai_responses = await ai_service.generate_answers_batch(
                    fields=[],  # We'll use question text directly
                    user=user,
                    job_title=job.title,
                    job_description=job.description or "",
                    job_company=job.company,
                )
                
                # For now, generate individual answers for common questions
                # (SingleJobApplier will use these when filling forms)
                context_data = ai_service._build_form_context(
                    user=user,
                    job_title=job.title,
                    job_description=job.description or "",
                    job_company=job.company,
                )
                
                for field_id, question in common_questions:
                    try:
                        answer = await ai_service.form_generator.answer_custom_question(
                            question,
                            context_data
                        )
                        ai_responses[field_id] = answer
                        logger.debug(f"Generated answer for question {field_id}: {len(answer)} chars")
                    except Exception as e:
                        logger.warning(f"Failed to generate answer for question {field_id}: {e}")
                        ai_responses[field_id] = ""
                
                # Store AI responses in task
                if ai_responses:
                    serialized_responses = ai_service.serialize_responses(ai_responses)
                    logger.info(f"✅ Generated {len(ai_responses)} AI form responses")
                    
                    # Update task with responses
                    task = await queue_repo.get_by_id(task_id)
                    if task:
                        task.ai_response = serialized_responses
                        await session.flush()
                        logger.info(f"💾 Stored AI responses ({len(serialized_responses)} bytes)")
                
            except Exception as e:
                logger.warning(f"Could not generate AI form responses: {e}")
                logger.debug(f"Will proceed with manual form filling")
            
            # Update progress
            await queue_repo.update_progress(task_id, "Applying to job using Easy Apply")
            await session.commit()
            
            # Apply to job using SingleJobApplier
            from application.services.jobs.single_job_applier import SingleJobApplier
            from core.config import settings
            from datetime import datetime
            
            openrouter_key = settings.OPENROUTER_API_KEY
            if not openrouter_key:
                raise ValueError("OpenRouter API key not configured")
            
            # Create activity logger callback to log to session activity_log
            def activity_logger(event_type: str, description: str, metadata: dict = None):
                """Log behavior activity to session activity_log for auditing"""
                try:
                    if not linkedin_session or not linkedin_session.session_log:
                        return
                    
                    # Initialize activity_log if it doesn't exist
                    if linkedin_session.session_log.activity_log is None:
                        linkedin_session.session_log.activity_log = []
                    
                    # Create activity event
                    event = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "event_type": event_type,
                        "description": description,
                        "task_id": task_id,
                        "job_id": job_id,
                    }
                    
                    # Add metadata if provided
                    if metadata:
                        event["metadata"] = metadata
                    
                    # Append to activity log
                    linkedin_session.session_log.activity_log.append(event)
                    
                    logger.debug(f"🎬 Behavior activity: {event_type} - {description}")
                    
                except Exception as e:
                    logger.warning(f"Failed to log activity: {e}")
            
            # Create status update callback for application steps
            def status_callback(step: str, additional_data: dict = None):
                """Update ApplyQueue status for current application step"""
                try:
                    # Use asyncio to run async function from sync context
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(
                            queue_repo.update_application_step(task_id, step, additional_data)
                        )
                        loop.run_until_complete(session.commit())
                    finally:
                        loop.close()
                    logger.info(f"📊 Application step updated: {step}")
                except Exception as e:
                    logger.warning(f"Failed to update application step: {e}")
            
            applier = SingleJobApplier(
                openrouter_api_key=openrouter_key,
                resume_text=resume_text,
                activity_logger=activity_logger,  # Pass activity logger
                enable_human_behavior=True,  # Enable human-like behavior
                status_callback=status_callback,  # Pass status callback
            )
            
            # Use existing driver from session instead of creating new one
            applier.driver = driver
            
            # Pass AI-generated responses to the applier for form filling
            if ai_responses:
                applier.ai_responses = ai_responses
                logger.info(f"📋 Using {len(ai_responses)} AI-generated form responses")
            
            # Directly apply to job (driver is already logged in)
            logger.info("Starting job application...")
            result = applier.apply_to_job(
                job_url=job_url,
                cookies=[],  # Driver already has cookies/session
                headless=False,  # We're using existing session
            )
            
            # Update job application status in database
            if result.success:
                await queue_repo.update_progress(task_id, "Updating job status to APPLIED")
                await session.commit()
                
                await user_job_repo.update_status(
                    user_id=user_id,
                    job_id=job_id,
                    status=ApplicationStatus.APPLIED,
                    applied_at=None,  # Will default to now
                )
                await session.commit()
                
                # Save behavior activity log to session log
                try:
                    behavior_log = applier.get_behavior_activity_log()
                    if behavior_log and linkedin_session and linkedin_session.session_log:
                        # Ensure activity_log exists
                        if linkedin_session.session_log.activity_log is None:
                            linkedin_session.session_log.activity_log = []
                        
                        # Append all behavior events
                        linkedin_session.session_log.activity_log.extend(behavior_log)
                        await session.commit()
                        
                        logger.info(f"📋 Saved {len(behavior_log)} behavior activity events to session log")
                        
                        # Log summary statistics
                        summary = applier.get_behavior_summary()
                        if summary:
                            logger.info(f"🎬 Behavior summary: {summary.get('total_events', 0)} events, "
                                      f"{summary.get('total_duration_seconds', 0):.1f}s total duration")
                except Exception as e:
                    logger.warning(f"Failed to save behavior activity log: {e}")
                
                linkedin_session.complete_task()
                
                logger.info(f"✅ Successfully applied to {job.title} at {job.company}")
                logger.info(f"   Task: {task_id}")
                
                # Mark task as completed
                await queue_repo.mark_completed(task_id)
                await session.commit()
                
            else:
                error_msg = f"Application failed: {result.message} (stage: {result.error_stage})"
                logger.error(f"❌ {error_msg}")
                
                linkedin_session.complete_task(error=error_msg)
                
                # Mark session as tainted if critical
                if result.details and result.details.get("session", {}).get("critical_taint"):
                    logger.warning(f"Session marked as tainted: {result.details.get('session', {}).get('taint_reason')}")
                
                # Don't retry on application errors - just fail
                await queue_repo.mark_failed(task_id, error_msg)
                await session.commit()
            
        except Exception as e:
            logger.error(f"❌ Job application task {task_id} failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Mark session task as failed
            if session_manager and session_id:
                try:
                    linkedin_session = session_manager.get_session(session_id)
                    if linkedin_session:
                        linkedin_session.complete_task(error=str(e))
                except:
                    pass
            
            raise


# Global worker instance
_worker_instance: Optional[TaskWorker] = None


async def start_worker(poll_interval: int = 5, max_concurrent_tasks: int = 3):
    """Start the global task worker"""
    global _worker_instance
    
    if _worker_instance and _worker_instance.running:
        logger.warning("Task worker is already running")
        return
    
    _worker_instance = TaskWorker(poll_interval, max_concurrent_tasks)
    await _worker_instance.start()


async def stop_worker():
    """Stop the global task worker"""
    global _worker_instance
    
    if _worker_instance:
        await _worker_instance.stop()
        _worker_instance = None


def get_worker() -> Optional[TaskWorker]:
    """Get the global worker instance"""
    return _worker_instance
