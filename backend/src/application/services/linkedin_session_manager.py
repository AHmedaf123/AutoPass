"""
LinkedIn Session Manager
Manages dynamic Selenium sessions with username/password login
Integrates session logging and activity tracking
"""
import time
import uuid
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

from domain.entities.session_log import SessionLog

try:
    import undetected_chromedriver as uc
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium/undetected-chromedriver not available")


class SessionStatus(str, Enum):
    """Session status enumeration"""
    CREATING = "creating"
    ACTIVE = "active"
    IN_USE = "in_use"
    COMPLETED = "completed"
    EXPIRED = "expired"
    ERROR = "error"


@dataclass
class LinkedInSession:
    """Represents an active LinkedIn session"""
    session_id: str
    driver: Any
    user_id: str
    created_at: datetime
    last_used: datetime
    linkedin_username: str
    status: SessionStatus = SessionStatus.ACTIVE
    task_name: Optional[str] = None
    task_started_at: Optional[datetime] = None
    task_completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    session_log: Optional[SessionLog] = None  # Associated session log for tracking
    
    def is_expired(self, max_age_minutes: int = 30) -> bool:
        """Check if session has expired"""
        age = datetime.utcnow() - self.last_used
        return age.total_seconds() > (max_age_minutes * 60)
    
    def is_idle(self, idle_minutes: int = 5) -> bool:
        """Check if session has been idle"""
        idle_time = datetime.utcnow() - self.last_used
        return idle_time.total_seconds() > (idle_minutes * 60)
    
    def mark_used(self):
        """Update last used timestamp"""
        self.last_used = datetime.utcnow()
    
    def start_task(self, task_name: str):
        """Mark task as started"""
        self.task_name = task_name
        self.task_started_at = datetime.utcnow()
        self.status = SessionStatus.IN_USE
        logger.info(f"Session {self.session_id}: Task '{task_name}' started")
    
    def complete_task(self, error: Optional[str] = None):
        """Mark task as completed"""
        self.task_completed_at = datetime.utcnow()
        self.status = SessionStatus.COMPLETED if not error else SessionStatus.ERROR
        self.error_message = error
        if error:
            logger.error(f"Session {self.session_id}: Task '{self.task_name}' failed: {error}")
        else:
            logger.info(f"Session {self.session_id}: Task '{self.task_name}' completed successfully")
    
    def get_uptime_seconds(self) -> float:
        """Get how long session has been active"""
        return (datetime.utcnow() - self.created_at).total_seconds()
    
    def get_idle_seconds(self) -> float:
        """Get how long session has been idle"""
        return (datetime.utcnow() - self.last_used).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for API response"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "uptime_seconds": self.get_uptime_seconds(),
            "idle_seconds": self.get_idle_seconds(),
            "task_name": self.task_name,
            "task_started_at": self.task_started_at.isoformat() if self.task_started_at else None,
            "task_completed_at": self.task_completed_at.isoformat() if self.task_completed_at else None,
            "error_message": self.error_message,
        }


class LinkedInSessionManager:
    """
    Manages dynamic LinkedIn Selenium sessions
    
    - Creates sessions with username/password login
    - Supports multiple concurrent sessions per user for parallel task processing
    - Tracks session lifecycle (creation, usage, task completion)
    - Auto-terminates completed sessions
    - Cleans up expired/idle sessions
    """
    
    def __init__(self):
        self.sessions: Dict[str, LinkedInSession] = {}
        self.user_sessions: Dict[str, List[str]] = {}  # Maps user_id to list of active session_ids (multiple concurrent)
        self.session_logs: Dict[str, SessionLog] = {}  # Maps session_id to session log
        self.user_cooldowns: Dict[str, datetime] = {}  # Maps user_id to cooldown_until time
        self.MAX_SESSION_AGE_MINUTES = 48 * 60  # 48 hours (instead of 30 minutes)
        self.MAX_IDLE_MINUTES = 5
        self.MAX_CONCURRENT_SESSIONS_PER_USER = 3  # Allow up to 3 concurrent sessions
        # Cooldown durations by failure type
        self.COOLDOWN_MINUTES_LOGIN_ERROR = 30  # Login failed
        self.COOLDOWN_MINUTES_CHECKPOINT = 60   # LinkedIn checkpoint/2FA
        self.COOLDOWN_MINUTES_SECURITY_ERROR = 120  # Security challenge
        self.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    def get_user_active_sessions(self, user_id: str) -> List[LinkedInSession]:
        """Get all active sessions for user (supports multiple concurrent sessions)"""
        session_ids = self.user_sessions.get(user_id, [])
        active_sessions = []
        for session_id in session_ids:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                if session.status in [SessionStatus.ACTIVE, SessionStatus.IN_USE]:
                    active_sessions.append(session)
        return active_sessions
    
    def get_user_active_session(self, user_id: str) -> Optional[LinkedInSession]:
        """Get first active session for user (backward compatibility)"""
        active_sessions = self.get_user_active_sessions(user_id)
        return active_sessions[0] if active_sessions else None
    
    def user_has_active_session(self, user_id: str) -> bool:
        """Check if user has any active sessions"""
        return len(self.get_user_active_sessions(user_id)) > 0
    
    def can_create_new_session(self, user_id: str) -> bool:
        """Check if user can create another concurrent session"""
        active_sessions = self.get_user_active_sessions(user_id)
        return len(active_sessions) < self.MAX_CONCURRENT_SESSIONS_PER_USER
    
    def is_user_on_cooldown(self, user_id: str) -> tuple[bool, Optional[datetime]]:
        """
        Check if user is on cooldown
        
        Returns:
            (is_on_cooldown, cooldown_until_datetime)
        """
        cooldown_time = self.user_cooldowns.get(user_id)
        if cooldown_time:
            if datetime.utcnow() < cooldown_time:
                logger.warning(f"User {user_id} is on cooldown until {cooldown_time}")
                return True, cooldown_time
            else:
                # Cooldown expired
                del self.user_cooldowns[user_id]
                logger.info(f"Cooldown expired for user {user_id}")
                return False, None
        return False, None
    
    def set_user_cooldown(self, user_id: str, cooldown_minutes: int, reason: str) -> datetime:
        """
        Set cooldown for user
        
        Args:
            user_id: User identifier
            cooldown_minutes: Duration in minutes
            reason: Reason for cooldown (login_error, checkpoint, security_challenge, etc.)
            
        Returns:
            Cooldown until datetime
        """
        cooldown_until = datetime.utcnow() + timedelta(minutes=cooldown_minutes)
        self.user_cooldowns[user_id] = cooldown_until
        logger.warning(f"Set {cooldown_minutes}min cooldown for user {user_id} ({reason}), until {cooldown_until}")
        return cooldown_until
    
    def clear_user_cooldown(self, user_id: str) -> bool:
        """
        Clear cooldown for user (manual reset)
        
        Returns:
            True if cooldown was cleared, False if no cooldown existed
        """
        if user_id in self.user_cooldowns:
            del self.user_cooldowns[user_id]
            logger.info(f"Cooldown cleared for user {user_id}")
            return True
        return False
    
    def terminate_user_session(self, user_id: str, reason: str = "Manual termination") -> bool:
        """Terminate user's active session"""
        session = self.get_user_active_session(user_id)
        if session:
            logger.info(f"Terminating session for user {user_id}: {reason}")
            return self.dispose_session(session.session_id)
        return False
    
    async def create_session(
        self,
        user_id: str,
        linkedin_username: str,
        linkedin_password: str,
        headless: bool = True
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Create a new LinkedIn session with dynamic login
        
        Now supports multiple concurrent sessions per user (up to MAX_CONCURRENT_SESSIONS_PER_USER).
        
        Returns:
            (session_id, error_message)
        """
        if not SELENIUM_AVAILABLE:
            return None, "Selenium not available"
        
        try:
            logger.info(f"Creating LinkedIn session for user {user_id}")
            
            # Check if user is on cooldown
            on_cooldown, cooldown_until = self.is_user_on_cooldown(user_id)
            if on_cooldown:
                error_msg = f"User is on cooldown until {cooldown_until.isoformat()}"
                logger.error(error_msg)
                return None, error_msg
            
            # Check if user can create more concurrent sessions
            if not self.can_create_new_session(user_id):
                error_msg = f"User has reached maximum concurrent sessions ({self.MAX_CONCURRENT_SESSIONS_PER_USER})"
                logger.warning(error_msg)
                return None, error_msg
            
            # Create session log
            session_log = SessionLog(
                user_id=user_id,
                session_id=str(uuid.uuid4()),  # Temporary ID
                created_at=datetime.utcnow(),
                status="CREATING"
            )
            session_log.record_login_started()
            
            # Setup Chrome driver
            driver = self._setup_driver(headless)
            if not driver:
                session_log.record_login_failed("Failed to initialize browser")
                session_log.status = "ERROR"
                self.session_logs[session_log.session_id] = session_log
                return None, "Failed to initialize browser"
            
            # Perform LinkedIn login
            login_start = time.time()
            login_success, login_error = self._login_to_linkedin(
                driver, linkedin_username, linkedin_password
            )
            login_time = int(time.time() - login_start)
            
            if not login_success:
                driver.quit()
                
                # Determine cooldown duration based on error type
                cooldown_minutes = self.COOLDOWN_MINUTES_LOGIN_ERROR
                if "checkpoint" in login_error.lower():
                    cooldown_minutes = self.COOLDOWN_MINUTES_CHECKPOINT
                    error_type = "checkpoint_required"
                elif "security" in login_error.lower() or "challenge" in login_error.lower():
                    cooldown_minutes = self.COOLDOWN_MINUTES_SECURITY_ERROR
                    error_type = "security_challenge"
                else:
                    error_type = "login_error"
                
                # Set cooldown
                cooldown_until = self.set_user_cooldown(user_id, cooldown_minutes, error_type)
                
                session_log.record_login_failed(login_error)
                session_log.status = "ERROR"
                session_log.add_activity(
                    "cooldown_set",
                    f"User on cooldown for {cooldown_minutes} minutes",
                    {"cooldown_minutes": cooldown_minutes, "reason": error_type, "until": cooldown_until.isoformat()}
                )
                self.session_logs[session_log.session_id] = session_log
                return None, f"{login_error} (cooldown {cooldown_minutes}min)"
            
            # Record successful login (clear cooldown on success)
            self.clear_user_cooldown(user_id)
            
            # Record successful login
            session_log.record_login_success(login_time)
            
            # Verify login
            if not self._verify_login(driver):
                driver.quit()
                session_log.record_login_failed("Login verification failed")
                session_log.status = "ERROR"
                self.session_logs[session_log.session_id] = session_log
                return None, "Login verification failed"
            
            # Create session
            session_id = session_log.session_id
            session = LinkedInSession(
                session_id=session_id,
                driver=driver,
                user_id=user_id,
                created_at=datetime.utcnow(),
                last_used=datetime.utcnow(),
                linkedin_username=linkedin_username,
                status=SessionStatus.ACTIVE,
                session_log=session_log
            )
            
            # Update session log status
            session_log.status = "ACTIVE"
            session_log.started_at = datetime.utcnow()
            
            self.sessions[session_id] = session
            self.session_logs[session_id] = session_log
            
            # Register session in user's session list (now supports multiple)
            if user_id not in self.user_sessions:
                self.user_sessions[user_id] = []
            self.user_sessions[user_id].append(session_id)
            
            active_count = len(self.get_user_active_sessions(user_id))
            logger.info(f"✅ LinkedIn session created: {session_id} for user {user_id}")
            logger.info(f"   Active sessions for user: {active_count}/{self.MAX_CONCURRENT_SESSIONS_PER_USER}")
            logger.info(f"   Session log tracking: tasks=0, errors=0, retries=0")
            
            # Keep browser open for 30 minutes (don't close immediately)
            expires_at = session.created_at + timedelta(minutes=30)
            logger.info(f"🌐 Browser will remain open for 30 minutes")
            logger.info(f"   Session will auto-expire at: {expires_at.isoformat()}")
            
            # Optional: Save to DB (commented out as per requirement)
            # try:
            #     await self._save_session_to_db(session_id, user_id)
            #     logger.info(f"✅ Session saved to database: {session_id}")
            # except Exception as e:
            #     logger.warning(f"⚠️ Failed to save session to DB: {e}")
            
            # Don't close browser - keep it alive for job discovery and applications
            logger.info(f"✅ Browser session ready for use: {session_id}")
            
            # Cleanup old sessions
            self._cleanup_expired_sessions()
            
            return session_id, None
            
        except Exception as e:
            logger.error(f"Failed to create LinkedIn session: {e}")
            return None, str(e)
    
    def get_user_cooldown_info(self, user_id: str) -> Dict[str, Any]:
        """
        Get cooldown information for user
        
        Returns:
            Dict with cooldown info
        """
        on_cooldown, cooldown_until = self.is_user_on_cooldown(user_id)
        if on_cooldown:
            remaining_seconds = int((cooldown_until - datetime.utcnow()).total_seconds())
            return {
                "is_on_cooldown": True,
                "cooldown_until": cooldown_until.isoformat(),
                "remaining_seconds": remaining_seconds,
                "remaining_minutes": remaining_seconds // 60,
            }
        return {
            "is_on_cooldown": False,
            "cooldown_until": None,
            "remaining_seconds": 0,
            "remaining_minutes": 0,
        }
    
    def get_session_log(self, session_id: str) -> Optional[SessionLog]:
        """Get session log by session ID"""
        return self.session_logs.get(session_id)
    
    def get_user_session(self, session_id: str) -> Optional[LinkedInSession]:
        """Get an active session by ID"""
        logger.info(f"🔍 Looking for session: {session_id}")
        logger.info(f"   Available sessions: {list(self.sessions.keys())}")
        
        session = self.sessions.get(session_id)
        
        if not session:
            logger.warning(f"❌ Session not found: {session_id}")
            logger.warning(f"   Total sessions in memory: {len(self.sessions)}")
            return None
        
        if session.is_expired(self.MAX_SESSION_AGE_MINUTES):
            logger.info(f"⏰ Session expired: {session_id}")
            self.dispose_session(session_id)
            return None
        
        session.mark_used()
        logger.info(f"✅ Session found and active: {session_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[LinkedInSession]:
        """Alias for get_user_session for backward compatibility"""
        return self.get_user_session(session_id)
    
    def dispose_session(self, session_id: str, reason: str = "session_complete") -> bool:
        """Dispose of a session and close the browser"""
        session = self.sessions.get(session_id)
        
        if not session:
            return False
        
        try:
            if session.driver:
                session.driver.quit()
                logger.info(f"🔌 Browser closed for session {session_id}")
        except Exception as e:
            logger.warning(f"⚠️ Error closing browser for session {session_id}: {e}")
        
        # Update session log
        session_log = self.session_logs.get(session_id)
        if session_log:
            duration = int((datetime.utcnow() - session_log.created_at).total_seconds())
            session_log.record_session_disposed(reason, duration)
            session_log.completed_at = datetime.utcnow()
            logger.info(f"📊 Session log summary: tasks={session_log.tasks_completed}, errors={session_log.errors_count}, retries={session_log.retries}, duration={duration}s")
        
        # Clean up user session mapping (now handles list of sessions)
        user_id = session.user_id
        if user_id in self.user_sessions:
            try:
                self.user_sessions[user_id].remove(session_id)
                remaining = len(self.user_sessions[user_id])
                logger.info(f"   Removed from user session list: {remaining}/{self.MAX_CONCURRENT_SESSIONS_PER_USER} sessions remaining")
                
                # Clean up empty user session list
                if not self.user_sessions[user_id]:
                    del self.user_sessions[user_id]
                    logger.info(f"   User {user_id} no longer has active sessions")
            except ValueError:
                logger.warning(f"   Session {session_id} not found in user {user_id} session list")
        
        # Clean up session objects
        del self.sessions[session_id]
        if session_id in self.session_logs:
            del self.session_logs[session_id]
        
        logger.info(f"✅ Session disposed: {session_id} ({reason})")
        return True
    
    def dispose_all_sessions(self):
        """Dispose all active sessions"""
        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            self.dispose_session(session_id)
        logger.info(f"Disposed {len(session_ids)} sessions")
    
    def get_user_session_status(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get status of user's active session"""
        session = self.get_user_active_session(user_id)
        if session:
            return session.to_dict()
        return None
    
    def get_all_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions across all users"""
        active_sessions = [
            session.to_dict() for session in self.sessions.values()
            if session.status in [SessionStatus.ACTIVE, SessionStatus.IN_USE]
        ]
        return active_sessions
    
    def get_sessions_by_status(self, status: SessionStatus) -> List[LinkedInSession]:
        """Get all sessions with specific status"""
        return [
            session for session in self.sessions.values()
            if session.status == status
        ]
    
    def get_user_session_logs(self, user_id: str) -> List[SessionLog]:
        """Get all session logs for a user"""
        return [
            log for log in self.session_logs.values()
            if log.user_id == user_id
        ]
    
    def get_user_session_statistics(self, user_id: str) -> Dict[str, Any]:
        """Get aggregated session statistics for a user"""
        logs = self.get_user_session_logs(user_id)
        
        if not logs:
            return {
                "total_sessions": 0,
                "total_tasks": 0,
                "total_retries": 0,
                "total_errors": 0,
                "avg_session_duration": 0,
                "avg_login_time": 0,
                "avg_task_duration": 0,
            }
        
        total_tasks = sum(log.tasks_completed for log in logs)
        total_retries = sum(log.retries for log in logs)
        total_errors = sum(log.errors_count for log in logs)
        
        durations = [log.session_duration_seconds for log in logs if log.session_duration_seconds]
        login_times = [log.login_time_seconds for log in logs if log.login_time_seconds]
        task_durations = [log.task_duration_seconds for log in logs if log.task_duration_seconds]
        
        return {
            "total_sessions": len(logs),
            "total_tasks": total_tasks,
            "total_retries": total_retries,
            "total_errors": total_errors,
            "avg_session_duration": sum(durations) / len(durations) if durations else 0,
            "avg_login_time": sum(login_times) / len(login_times) if login_times else 0,
            "avg_task_duration": sum(task_durations) / len(task_durations) if task_durations else 0,
        }
    
    def get_session_statistics(self) -> Dict[str, Any]:
        """Get global session statistics"""
        total_sessions = len(self.sessions)
        active_sessions = len([s for s in self.sessions.values() if s.status in [SessionStatus.ACTIVE, SessionStatus.IN_USE]])
        completed_sessions = len([s for s in self.sessions.values() if s.status == SessionStatus.COMPLETED])
        expired_sessions = len([s for s in self.sessions.values() if s.status == SessionStatus.EXPIRED])
        error_sessions = len([s for s in self.sessions.values() if s.status == SessionStatus.ERROR])
        
        # Check for idle sessions
        idle_sessions = []
        for session in self.sessions.values():
            if session.is_idle(self.MAX_IDLE_MINUTES) and session.status in [SessionStatus.ACTIVE, SessionStatus.IN_USE]:
                idle_sessions.append(session.session_id)
        
        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "completed_sessions": completed_sessions,
            "expired_sessions": expired_sessions,
            "error_sessions": error_sessions,
            "idle_sessions": idle_sessions,
            "total_users": len(self.user_sessions),
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def mark_session_task_complete(self, session_id: str, error: Optional[str] = None) -> bool:
        """Mark session task as completed and auto-dispose"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.complete_task(error)
        
        # Log task completion
        session_log = self.session_logs.get(session_id)
        if session_log and session.task_name:
            duration = int((datetime.utcnow() - session.task_started_at).total_seconds())
            session_log.record_task_completed(session.task_name, duration, error)
            logger.info(f"Task '{session.task_name}' completed: errors={session_log.errors_count}, retries={session_log.retries}")
        
        # Auto-dispose completed sessions
        logger.info(f"Auto-disposing completed session: {session_id}")
        reason = "error" if error else "auto_disposal"
        return self.dispose_session(session_id, reason)
    
    def record_task_retry(self, session_id: str, reason: str) -> bool:
        """Record a task retry attempt"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session_log = self.session_logs.get(session_id)
        if session_log:
            session_log.record_retry(reason, session_log.retries + 1)
            logger.warning(f"Task retry #{session_log.retries}: {reason}")
        
        return True
    
    def mark_session_task_started(self, session_id: str, task_name: str) -> bool:
        """Mark session task as started"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.start_task(task_name)
        
        # Log task start
        session_log = self.session_logs.get(session_id)
        if session_log:
            session_log.record_task_started(task_name)
            logger.info(f"Task '{task_name}' started in session {session_id}")
        
        return True
    
    def _cleanup_expired_sessions(self):
        """Remove expired and idle sessions"""
        expired = [
            sid for sid, session in self.sessions.items()
            if session.is_expired(self.MAX_SESSION_AGE_MINUTES) or 
               (session.is_idle(self.MAX_IDLE_MINUTES) and session.status == SessionStatus.COMPLETED)
        ]
        
        for session_id in expired:
            logger.info(f"Cleaning up expired/idle session: {session_id}")
            self.dispose_session(session_id)
    
    def _setup_driver(self, headless: bool = True) -> Optional[Any]:
        """Initialize undetected Chrome driver"""
        try:
            options = uc.ChromeOptions()
            options.add_argument(f"--user-agent={self.USER_AGENT}")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            if headless:
                options.add_argument("--headless=new")
            
            # Specify Chrome version to match installed browser
            driver = uc.Chrome(options=options, use_subprocess=True, version_main=144)
            driver.set_page_load_timeout(60)
            driver.implicitly_wait(10)
            
            logger.info("Chrome driver initialized")
            return driver
            
        except Exception as e:
            logger.error(f"Failed to setup driver: {e}")
            return None
    
    def _login_to_linkedin(
        self,
        driver: Any,
        username: str,
        password: str
    ) -> tuple[bool, Optional[str]]:
        """
        Perform LinkedIn login with username and password
        
        Returns:
            (success, error_message)
        """
        try:
            logger.info("Navigating to LinkedIn login page...")
            driver.get("https://www.linkedin.com/login")
            time.sleep(2)
            
            # Check if already logged in (redirected to feed)
            current_url = driver.current_url
            logger.info(f"After navigation, current URL: {current_url}")
            
            if "feed" in current_url or ("linkedin.com" in current_url and "login" not in current_url):
                logger.info("✅ Already logged in - redirected to feed")
                return True, None
            
            # Find and fill username
            logger.info("Entering username...")
            try:
                username_field = WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.ID, "username"))
                )
                username_field.clear()
                username_field.send_keys(username)
                time.sleep(0.5)
            except TimeoutException:
                logger.error("Timeout finding username field - checking if already logged in")
                current_url = driver.current_url
                if "login" not in current_url and "linkedin.com" in current_url:
                    logger.info("✅ Not on login page - likely already authenticated")
                    return True, None
                raise
            
            # Find and fill password
            logger.info("Entering password...")
            try:
                password_field = driver.find_element(By.ID, "password")
                password_field.clear()
                password_field.send_keys(password)
                time.sleep(0.5)
            except NoSuchElementException:
                logger.error("Password field not found")
                return False, "Password field not found on login page"
            
            # Click login button
            logger.info("Clicking login button...")
            try:
                login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                login_button.click()
                logger.info("Waiting for LinkedIn to process login...")
                time.sleep(5)  # Wait 5 seconds for login to process
            except NoSuchElementException:
                logger.error("Login button not found")
                return False, "Login button not found on login page"
            
            # Check for login errors
            current_url = driver.current_url
            logger.info(f"After login button click, current URL: {current_url}")
            
            if "login" in current_url or "checkpoint" in current_url:
                # Check for error messages
                try:
                    error_element = driver.find_element(By.ID, "error-for-username")
                    error_message = error_element.text
                    logger.error(f"Login failed: {error_message}")
                    return False, f"Login failed: {error_message}"
                except NoSuchElementException:
                    pass
                
                # Check if 2FA is required
                if "checkpoint" in current_url:
                    logger.error("2FA/verification required")
                    return False, "2FA verification required. Please disable 2FA or use app-specific password"
                
                return False, "Login failed - incorrect credentials or security challenge"
            
            logger.info("✅ Login form submitted successfully")
            return True, None
            
        except TimeoutException as e:
            logger.error(f"Timeout during login process: {e}")
            # Give it one more chance - maybe it redirected
            try:
                current_url = driver.current_url
                if "feed" in current_url or ("linkedin.com" in current_url and "login" not in current_url):
                    logger.info("✅ Despite timeout, browser reached authenticated page")
                    return True, None
            except:
                pass
            return False, "Login page timeout"
        except NoSuchElementException as e:
            logger.error(f"Login element not found: {e}")
            return False, "Login page structure changed"
        except Exception as e:
            logger.error(f"Error during login: {e}")
            return False, str(e)
    
    def _verify_login(self, driver: Any) -> bool:
        """Verify successful LinkedIn login"""
        try:
            time.sleep(2)
            current_url = driver.current_url
            
            logger.info(f"Verifying login - current URL: {current_url}")
            
            # Check if redirected to login/checkpoint
            if "login" in current_url or "checkpoint" in current_url:
                logger.error("Still on login/checkpoint page")
                return False
            
            # Check for feed page (best case)
            if "linkedin.com/feed" in current_url:
                logger.info("✅ On feed page - login successful")
                return True
            
            # Check for navigation bar (indicates logged in)
            try:
                driver.find_element(By.ID, "global-nav")
                logger.info("✅ Found global-nav - login successful")
                return True
            except NoSuchElementException:
                pass
            
            # If on any authenticated LinkedIn page
            if "linkedin.com" in current_url:
                logger.info("✅ On LinkedIn authenticated page")
                return True
            
            logger.error("Login verification failed - unknown state")
            return False
        except Exception as e:
            logger.error(f"Error verifying login: {e}")
            return False
    
    
    async def _save_session_to_db(self, session_id: str, user_id: str) -> None:
        """Save session to database for persistence across server restarts"""
        try:
            from core.database import AsyncSessionLocal
            from infrastructure.persistence.models.session import SessionModel, SessionStatus as DBSessionStatus
            
            db_session = AsyncSessionLocal()
            try:
                # Create session record in database
                session_record = SessionModel(
                    session_id=session_id,
                    user_id=user_id,
                    status=DBSessionStatus.ACTIVE,
                    browser_type="chrome",
                    headless=0  # Browser was shown during login
                )
                
                db_session.add(session_record)
                await db_session.commit()
                logger.info(f"✅ Session {session_id} persisted to database")
            except Exception as db_error:
                logger.error(f"Failed to commit session to database: {db_error}")
                await db_session.rollback()
            finally:
                await db_session.close()
        except Exception as e:
            logger.error(f"Failed to persist session to database: {e}")


# Global session manager instance
_session_manager = None


def get_session_manager() -> LinkedInSessionManager:
    """Get or create the global session manager instance"""
    global _session_manager
    if _session_manager is None:
        _session_manager = LinkedInSessionManager()
    return _session_manager
