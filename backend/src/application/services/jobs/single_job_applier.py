"""
Single Job Application Service
Applies to a single LinkedIn job using Easy Apply automation
Based on the linkedin-easyapply-using-AI script but refactored for API use
"""
# Always import os at the top
import os
import time
import random
import re
import json
import requests
import demjson3
from typing import Optional, Dict, Any, List, Tuple, Callable
from dataclasses import dataclass
from loguru import logger
from core.config import settings
from application.services.jobs.session_lifecycle import (
    SessionContext,
    SessionLifecycleManager,
)
from application.services.jobs.human_behavior_simulator import (
    HumanBehaviorSimulator,
    BehaviorAction,
)

# Selenium imports
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException,
        NoSuchElementException,
        ElementClickInterceptedException
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium/undetected-chromedriver not available")


@dataclass
class ApplicationResult:
    """Result of job application attempt"""
    success: bool
    job_url: str
    message: str
    error_stage: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class SingleJobApplier:
    """
    Applies to a single LinkedIn job with Easy Apply automation.
    Uses AI (OpenRouter) to answer form questions intelligently.
    
    FAIL-FAST 429 / ANTI-BOT FEATURES (NO RETRIES):
    - Disposable runtime session derived from baseline cookies (baseline untouched)
    - SessionLifecycleManager caps applies per session (default 5) and taints on anti-bot signals
    - No LinkedIn retries/backoff; any 429/shadow-throttle marks session tainted immediately
    - Fixed SessionContext per session (UA, locale, viewport, proxy) for hygiene
    - Human-like cadence (bounded scroll + dwell) without refresh loops
    """
    
    def __init__(
        self,
        openrouter_api_key: str,
        resume_text: str,
        session_context: SessionContext | None = None,
        lifecycle_manager: SessionLifecycleManager | None = None,
        activity_logger: Optional[Callable] = None,
        enable_human_behavior: bool = True,
        status_callback: Optional[Callable] = None,
        temp_resume_path: Optional[str] = None,
        resume_json: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize job applier
        
        Args:
            openrouter_api_key: OpenRouter API key for GPT
            resume_text: User's resume text for AI answers
            session_context: Optional session context
            lifecycle_manager: Optional lifecycle manager
            activity_logger: Optional callback for logging activities (receives event_type, description, metadata)
            enable_human_behavior: Whether to enable human-like behavior simulation (default: True)
            temp_resume_path: Optional path to temporary enhanced resume PDF for upload (ephemeral, not persisted)
            resume_json: Optional full resume JSON structure for enhanced AI context (same as used in enhancement)
        """
        self.driver = None
        self.openrouter_api_key = openrouter_api_key
        self.resume = resume_text
        self.resume_json = resume_json  # Full JSON structure for enhanced AI context
        self.job_description = None  # Will be set in apply_to_job
        self.max_gpt_retries = 5  # Increased to handle more retries
        self.span_messages = {}  # Store span messages for field context
        self.lifecycle = lifecycle_manager or SessionLifecycleManager(max_applies=5)
        
        # Temporary enhanced resume path (for job-specific AI-enhanced resumes)
        # This is ephemeral and NOT persisted to database
        self.temp_resume_path = temp_resume_path
        
        default_user_agent = (
            settings.USER_AGENTS[0]
            if hasattr(settings, "USER_AGENTS") and settings.USER_AGENTS
            else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self.session_context = session_context or SessionContext(
            user_agent=default_user_agent,
            viewport=(1366, 768),
            accept_language="en-US,en;q=0.9",
            proxy=None,
            max_applies=self.lifecycle.max_applies,
        )
        self.consecutive_rate_limits = 0  # Used only for GPT/OpenRouter
        self.last_rate_limit_time = 0
        # Track ownership to avoid quitting a shared session-managed driver
        self.owns_driver = True
        # Optional hook for status updates
        self.status_callback = status_callback
        
        # Human behavior simulation
        self.enable_human_behavior = enable_human_behavior
        self.behavior_simulator: Optional[HumanBehaviorSimulator] = None
        self.activity_logger = activity_logger
    
    def _initialize_behavior_simulator(self):
        """Initialize human behavior simulator if enabled"""
        if self.enable_human_behavior and self.driver:
            self.behavior_simulator = HumanBehaviorSimulator(
                driver=self.driver,
                activity_logger=self.activity_logger
            )
            logger.info("Human behavior simulator initialized")
    
    def _type_with_human_behavior(
        self,
        element,
        text: str,
        clear_first: bool = True,
        field_label: Optional[str] = None
    ) -> float:
        """
        Type text with human-like behavior if enabled, otherwise use normal typing
        OPTIMIZED: Minimal delays for speed while maintaining basic human-like patterns
        
        Args:
            element: Form element to type in
            text: Text to type
            clear_first: Whether to clear field first
            field_label: Optional label for logging
            
        Returns:
            Time taken in seconds
        """
        # SPEED OPTIMIZED: Use fast typing with minimal delays
        start_time = time.time()
        try:
            element.click()
            time.sleep(0.05)  # Minimal pause
            if clear_first:
                element.clear()
                time.sleep(0.02)
            element.send_keys(text)
            time.sleep(0.05)  # Brief pause after typing
        except Exception as e:
            logger.warning(f"Fast typing failed: {e}")
            # Retry once
            element.send_keys(text)
        return time.time() - start_time
    
    def _click_with_human_behavior(
        self,
        element,
        pause_after: bool = True
    ) -> float:
        """
        Click element with human-like behavior if enabled
        OPTIMIZED: Minimal delays for speed
        
        Args:
            element: Element to click
            pause_after: Whether to pause after clicking
            
        Returns:
            Time taken in seconds
        """
        # SPEED OPTIMIZED: Fast click with minimal delay
        start_time = time.time()
        element.click()
        if pause_after:
            time.sleep(0.05)  # Minimal pause
        return time.time() - start_time
    
    def _scroll_with_human_behavior(
        self,
        direction: str = "down",
        distance: Optional[float] = None
    ) -> float:
        """
        Scroll with human-like behavior if enabled
        
        Args:
            direction: "up" or "down"
            distance: Distance to scroll in pixels
            
        Returns:
            Time taken in seconds
        """
        if self.behavior_simulator and self.enable_human_behavior:
            try:
                return self.behavior_simulator.scroll_like_human(
                    direction=direction,
                    distance=distance,
                    pause_after=True
                )
            except Exception as e:
                logger.warning(f"Human scroll failed, falling back to normal: {e}")
        
        # Fallback to normal scroll
        start_time = time.time()
        self._human_scroll()
        return time.time() - start_time
    
    def _pause_with_human_behavior(self, label: str = "processing") -> float:
        """
        Add thinking pause with human-like behavior
        
        Args:
            label: Description of what "thinking" about
            
        Returns:
            Pause duration in seconds
        """
        if self.behavior_simulator and self.enable_human_behavior:
            try:
                return self.behavior_simulator.think_like_human(label=label)
            except Exception as e:
                logger.warning(f"Human pause failed, falling back to normal: {e}")
        
        # Fallback to normal pause
        pause_duration = random.uniform(0.5, 2.0)
        time.sleep(pause_duration)
        return pause_duration
    
    def get_behavior_activity_log(self) -> List[Dict[str, Any]]:
        """
        Get the activity log of all human-like behaviors performed
        
        Returns:
            List of behavior events with timestamps and metadata
        """
        if self.behavior_simulator:
            return self.behavior_simulator.export_activity_log()
        return []
    
    def get_behavior_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics of human-like behaviors
        
        Returns:
            Summary including total events, durations, and breakdown by type
        """
        if self.behavior_simulator:
            return self.behavior_simulator.get_behavior_summary()
        return {}
    
    def _human_delay(self, min_seconds: float | None = None, max_seconds: float | None = None):
        """Add bounded human-like delay derived from session context."""
        ctx_min, ctx_max = self.session_context.dwell_seconds_range
        low = min_seconds if min_seconds is not None else ctx_min
        high = max_seconds if max_seconds is not None else ctx_max
        delay = random.uniform(low, high)
        logger.debug(f"Human delay: {delay:.2f}s")
        time.sleep(delay)

    def _human_scroll(self):
        """Perform a single human-like scroll to a randomized depth."""
        if not self.driver:
            return
        
        # Use new human behavior simulator if available
        if self.behavior_simulator and self.enable_human_behavior:
            try:
                # Randomly choose scroll direction and distance
                direction = "down" if random.random() > 0.3 else "up"
                self._scroll_with_human_behavior(direction=direction)
                return
            except Exception as e:
                logger.warning(f"Human scroll behavior failed, using fallback: {e}")
        
        # Fallback to original scroll behavior
        min_depth, max_depth = self.session_context.human_scroll_depth_range
        depth = random.uniform(min_depth, max_depth)
        try:
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight * arguments[0]);",
                depth,
            )
            logger.debug(f"Scrolled to {depth:.2f} of page height")
        except Exception as exc:
            logger.debug(f"Scroll skipped: {exc}")

    def _mark_session_tainted(self, reason: str, critical: bool = False):
        """Mark session as tainted with optional severity level.
        
        Args:
            reason: The reason for tainting
            critical: If True, enforce cooldown. If False, log warning but allow continuation.
        """
        severity = "CRITICAL" if critical else "WARNING"

        try:
            self.lifecycle.mark_tainted(reason, critical=critical)
        except TypeError as exc:
            # Legacy safety: older SessionLifecycleManager may not accept `critical`
            if "critical" not in str(exc):
                raise
            logger.warning("SessionLifecycleManager.mark_tainted missing critical flag; applying legacy fallback")
            self.lifecycle.mark_tainted(reason)
            if critical and hasattr(self.lifecycle, "critical_taint"):
                try:
                    self.lifecycle.critical_taint = True
                except Exception:
                    logger.debug("Could not set critical_taint on legacy lifecycle")

        logger.warning(f"Session {severity}: {reason}")
    
    def _handle_rate_limit_response(self, response_headers: Dict[str, str]) -> float:
        """
        Handle 429 rate limit response from server.
        Uses exponential backoff and respects Retry-After header.
        
        Args:
            response_headers: Response headers from failed request
            
        Returns:
            Wait time in seconds before retry
        """
        self.consecutive_rate_limits += 1
        logger.error(
            f"❌ HTTP 429 Rate Limit detected! "
            f"(consecutive: {self.consecutive_rate_limits}/5)"
        )
        
        # Circuit breaker: stop after 5 consecutive rate limits
        if self.consecutive_rate_limits >= 5:
            logger.critical(
                f"🚫 RATE LIMIT CIRCUIT BREAKER TRIGGERED! "
                f"({self.consecutive_rate_limits} consecutive 429 errors)"
            )
            raise Exception(
                f"Rate limit circuit breaker triggered after "
                f"{self.consecutive_rate_limits} consecutive 429 errors. "
                "LinkedIn is blocking this account. Please wait 1+ hours before retrying."
            )
        
        # Check for Retry-After header (most authoritative)
        retry_after_str = response_headers.get('Retry-After', '')
        wait_seconds = None
        
        if retry_after_str:
            try:
                # Could be seconds (integer) or HTTP date
                wait_seconds = float(retry_after_str)
                logger.info(f"📋 Retry-After header: {wait_seconds}s")
            except ValueError:
                logger.debug(f"Could not parse Retry-After header: {retry_after_str}")
        
        # Use exponential backoff if no Retry-After header
        if wait_seconds is None:
            # Exponential backoff: 2s, 4s, 8s, 16s, 32s
            wait_seconds = 2 ** self.consecutive_rate_limits
            wait_seconds = min(wait_seconds, 300)  # Cap at 5 minutes
            logger.info(f"Using exponential backoff: {wait_seconds}s (attempt {self.consecutive_rate_limits})")
        
        logger.warning(
            f"⏳ Rate limited! Backing off for {wait_seconds:.0f}s "
            f"before retry {self.consecutive_rate_limits}/5..."
        )
        
        self.last_rate_limit_time = time.time()
        return wait_seconds
    
    def setup_driver(
        self,
        headless: bool = True,
        retry_count: int = 3,
        session_context: Optional[SessionContext] = None,
    ) -> Optional[Any]:
        """Initialize undetected Chrome driver with stealth mode and session hygiene"""
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not available")
            return None
        
        # Clean up any existing driver first
        if self.driver:
            try:
                logger.info("Cleaning up existing driver...")
                self.driver.quit()
                time.sleep(2)  # Wait for cleanup
            except:
                pass
            self.driver = None
        
        # Retry loop for initialization
        for attempt in range(retry_count):
            try:
                logger.info(f"Initializing Chrome driver (attempt {attempt + 1}/{retry_count})...")
                
                ctx = session_context or self.session_context
                options = uc.ChromeOptions()
                
                # Stealth mode - appear more human-like
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-notifications")
                options.add_argument("--disable-popup-blocking")
                
                # Fixed per-session hygiene
                options.add_argument(f"user-agent={ctx.user_agent}")
                options.add_argument(f"--accept-language={ctx.accept_language}")
                if ctx.proxy:
                    options.add_argument(f"--proxy-server={ctx.proxy}")
                if headless:
                    options.add_argument("--headless=new")
                if ctx.viewport:
                    width, height = ctx.viewport
                    options.add_argument(f"--window-size={width},{height}")
                
                # Increase timeout to handle slow connections
                self.driver = uc.Chrome(options=options, timeout=120)
                
                # Wait for window to be fully ready before proceeding
                time.sleep(3)
                
                # Verify driver is responsive before executing commands
                try:
                    _ = self.driver.current_url
                    logger.debug("✓ Driver window is responsive")
                except Exception as e:
                    logger.warning(f"Driver not responsive after initialization: {e}")
                    self.driver.quit()
                    self.driver = None
                    if attempt < retry_count - 1:
                        logger.info(f"Retrying in 3 seconds...")
                        time.sleep(3)
                        continue
                    raise
                
                # Maximize window
                try:
                    self.driver.maximize_window()
                except:
                    logger.debug("Could not maximize window (may be headless)")
                
                # Additional stealth: remove webdriver property
                try:
                    self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                        "source": """
                            Object.defineProperty(navigator, 'webdriver', {
                                get: () => undefined
                            })
                        """
                    })
                    logger.debug("✓ Webdriver property masked")
                except Exception as e:
                    logger.warning(f"Could not mask webdriver property: {e}")
                    # Non-fatal, continue
                
                # Final verification that driver is still alive after all modifications
                try:
                    _ = self.driver.current_url
                    _ = self.driver.window_handles
                    logger.info("✓ Driver initialized with stealth mode")
                    
                    # Initialize human behavior simulator
                    self._initialize_behavior_simulator()
                    
                    return self.driver
                except Exception as e:
                    logger.error(f"Driver became unresponsive after stealth setup: {e}")
                    self.driver.quit()
                    self.driver = None
                    if attempt < retry_count - 1:
                        logger.info(f"Retrying in 3 seconds...")
                        time.sleep(3)
                        continue
                    raise
                
            except Exception as e:
                logger.warning(f"Chrome driver initialization failed (attempt {attempt + 1}/{retry_count}): {e}")
                
                # Clean up on failure
                if self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass
                    self.driver = None
                
                # If this was the last attempt, log error and return None
                if attempt == retry_count - 1:
                    logger.error(f"Failed to initialize Chrome driver after {retry_count} attempts")
                    return None
                
                # Wait before retrying
                wait_time = 3 * (attempt + 1)  # Progressive backoff: 3s, 6s, 9s
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
    
    def verify_login(self) -> bool:
        """Verify successful LinkedIn login by checking for authenticated elements"""
        if not self.driver:
            return False
        
        try:
            current_url = self.driver.current_url
            
            # If redirected to login/checkpoint, cookies failed
            if "login" in current_url or "checkpoint" in current_url:
                logger.warning("Redirected to login page - cookies invalid")
                return False
            
            # Check for authenticated navigation elements
            try:
                self.driver.find_element(By.ID, "global-nav")
                logger.info("✓ LinkedIn login verified (global-nav found)")
                return True
            except NoSuchElementException:
                pass
            
            # If we're on any linkedin.com page (not login), assume success
            if "linkedin.com" in current_url and "login" not in current_url:
                logger.info("✓ LinkedIn login verified (on authenticated page)")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error verifying login: {e}")
            return False
    
    def ask_gpt(self, prompt: str, max_tokens: int = 2048) -> Optional[str]:
        """
        Ask GPT via OpenRouter API with 429 rate limit handling.
        Uses exponential backoff for rate limit errors.
        """
        for attempt in range(self.max_gpt_retries):
            try:
                headers = {
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "HTTP-Referer": "https://linkedin-easy-apply.com",
                    "X-Title": "LinkedIn Easy Apply Bot"
                }
                
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": "openai/gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": max_tokens
                    },
                    timeout=30
                )
                
                # Check for rate limit (429) response
                if response.status_code == 429:
                    wait_seconds = self._handle_rate_limit_response(dict(response.headers))
                    if attempt < self.max_gpt_retries - 1:
                        logger.warning(
                            f"OpenRouter rate limited (attempt {attempt+1}/{self.max_gpt_retries}). "
                            f"Waiting {wait_seconds}s before retry..."
                        )
                        time.sleep(wait_seconds)
                        continue
                    else:
                        logger.error("Max retries exhausted for OpenRouter 429 error")
                        return None
                
                # Check for other HTTP errors
                response.raise_for_status()
                
                # Reset rate limit counter on success
                self.consecutive_rate_limits = 0
                
                return response.json()['choices'][0]['message']['content']
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"OpenRouter attempt {attempt+1}/{self.max_gpt_retries} failed: {e}")
                
                # Exponential backoff for connection errors too
                if attempt < self.max_gpt_retries - 1:
                    backoff_time = 2 ** (attempt + 1)  # 2s, 4s, 8s, 16s
                    logger.info(f"Retrying in {backoff_time}s...")
                    time.sleep(backoff_time)
                else:
                    logger.error("All OpenRouter attempts exhausted")
                    return None
            
            except Exception as e:
                logger.error(f"Unexpected error in ask_gpt: {e}")
                if attempt < self.max_gpt_retries - 1:
                    time.sleep(2)
                else:
                    return None
        
        return None
    
    def _is_shadow_throttled(self) -> bool:
        if not self.driver:
            return False
        try:
            html = self.driver.page_source.lower()
        except Exception:
            return False
        if not html or len(html) < 500:
            # Avoid false positives when the page is still streaming content
            logger.debug("Shadow throttle check skipped: HTML incomplete")
            return False

        shadow_signals = [
            "too many requests",
            "429",
            "temporarily limited",
            "unusual activity"
        ]
        throttled = any(sig in html for sig in shadow_signals)
        if throttled:
            logger.warning("Shadow throttle signals detected in page HTML")
        return throttled

    def _job_content_missing(self) -> bool:
        if not self.driver:
            return True
        try:
            desc = self.driver.find_elements(By.CSS_SELECTOR, "section.show-more-less-html__markup")
            if not desc:
                return True
            joined = " ".join([d.text for d in desc])
            return len(joined.strip()) < 50
        except Exception:
            return True

    @staticmethod
    def _normalize_job_url(job_url: str) -> str:
        """Normalize LinkedIn URLs to keep only currentJobId param."""
        try:
            match = re.search(r"currentJobId=(\d+)", job_url)
            if match:
                job_id = match.group(1)
                return f"https://www.linkedin.com/jobs/search/?currentJobId={job_id}"
        except Exception as exc:
            logger.debug(f"Job URL normalization failed: {exc}")
        return job_url

    def navigate_to_job(self, job_url: str) -> tuple[bool, Optional[str]]:
        """Navigate to job listing page."""
        if not self.driver:
            return False, "driver_missing"
        
        try:
            normalized_url = self._normalize_job_url(job_url)
            logger.info(f"Navigating to job URL: {normalized_url}")
            
            self.driver.get(normalized_url)
            time.sleep(2)  # Brief wait for page load
            
            return True, None
        except Exception as e:
            logger.error(f"Failed to navigate to job: {e}")
            return False, "navigation_error"
    
    def click_easy_apply(self) -> tuple[bool, Optional[str]]:
        """Click the Easy Apply button with human-like behavior and fail-fast on shadow throttle."""
        try:
            self._pause_with_human_behavior("reviewing job description")
            
            # Check for job expired/unavailable errors before attempting to click Easy Apply
            error_selectors = [
                "#ember54 > span",  # Common error message container
                ".artdeco-inline-feedback--error",
                ".jobs-details__main-content .artdeco-inline-feedback",
                "//div[contains(@class, 'artdeco-inline-feedback') and contains(@class, 'error')]",
                "//span[contains(text(), 'no longer accepting applications')]",
                "//span[contains(text(), 'This job is no longer available')]",
                "//span[contains(text(), 'expired')]"
            ]
            
            for error_selector in error_selectors:
                try:
                    if error_selector.startswith("//"):
                        error_element = self.driver.find_element(By.XPATH, error_selector)
                    else:
                        error_element = self.driver.find_element(By.CSS_SELECTOR, error_selector)
                    
                    if error_element and error_element.is_displayed():
                        error_text = error_element.text.strip()
                        logger.error(f"Job expired/unavailable error detected: {error_text}")
                        return False, f"job_expired: {error_text}"
                except Exception:
                    continue
            
            selectors = [
                ".jobs-s-apply.jobs-s-apply--fadein.inline-flex.mr2",
                "button.jobs-apply-button",
                "button[aria-label*='Easy Apply']",
                "//button[contains(text(), 'Easy Apply')]"
            ]
            
            for selector in selectors:
                try:
                    if selector.startswith("//"):
                        button = self.driver.find_element(By.XPATH, selector)
                    else:
                        button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    # Smooth scroll to button
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                    self._pause_with_human_behavior("preparing to click Easy Apply")
                    
                    # Use human-like click
                    self._click_with_human_behavior(button, pause_after=True)
                    time.sleep(0.2)  # Quick wait for form to appear
                    
                    logger.info("Easy Apply button clicked")
                    return True, None
                except Exception:
                    continue
            
            logger.error("Easy Apply button not found")
            self._mark_session_tainted("missing_easy_apply", critical=False)
            return False, "missing_easy_apply"
            
        except Exception as e:
            logger.error(f"Error clicking Easy Apply button: {e}")
            self._mark_session_tainted("easy_apply_error", critical=False)
            return False, "easy_apply_error"
    
    def handle_easy_apply_popup(self) -> bool:
        """Handle popup that may appear after clicking Easy Apply button
        Sometimes LinkedIn shows a confirmation popup that needs to be clicked before showing the form"""
        try:
            self._pause_with_human_behavior("checking for popup")
            
            # Try to find the popup button with various ember IDs
            popup_selectors = [
                "div[id^='ember'][id$='6'] > div",  # Matches ember296, ember306, etc.
                "div[id^='ember'][id$='0'] > div",  # Matches ember300, ember310, etc.
                ".artdeco-modal__actionbar button.artdeco-button--primary",
                "button[aria-label*='Continue']",
                "button[aria-label*='Submit']",
                "//button[contains(text(), 'Continue')]",
                "//button[contains(text(), 'Submit application')]"
            ]
            
            for selector in popup_selectors:
                try:
                    if selector.startswith("//"):
                        popup_button = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    else:
                        popup_button = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    
                    # Found the popup, click it with human-like behavior
                    self._pause_with_human_behavior("reading popup")
                    self._click_with_human_behavior(popup_button, pause_after=True)
                    
                    logger.info(f"Popup handled successfully using selector: {selector}")
                    time.sleep(0.5)
                    return True
                except:
                    continue
            
            # No popup found - this is normal, proceed to form
            logger.debug("No Easy Apply popup detected (this is normal)")
            return True
            
        except Exception as e:
            logger.warning(f"Error handling Easy Apply popup: {e}")
            # Non-fatal, continue anyway
            return True

    def _wait_for_overlay_to_clear(self, timeout: float = 8.0) -> None:
        """Wait for transient modal overlays to stop intercepting clicks"""
        if not self.driver:
            return

        overlay_selectors = [
            "div.artdeco-modal-overlay--is-top-layer",
            "div[data-test-modal-id='easy-apply-modal'][aria-hidden='false']",
            "div[data-test-modal-container][aria-hidden='false']"
        ]

        for selector in overlay_selectors:
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, selector))
                )
            except TimeoutException:
                continue

    def _safe_click_element(self, element, description: str = "element") -> bool:
        """Click an element with overlay handling and JS retry"""
        try:
            self._wait_for_overlay_to_clear()
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.3)
            element.click()
            return True
        except ElementClickInterceptedException as e:
            logger.warning(f"{description} click intercepted: {e}. Waiting and retrying with JS click.")
            try:
                self._wait_for_overlay_to_clear(timeout=10)
                time.sleep(0.2)
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception as retry_error:
                logger.error(f"Retry click failed for {description}: {retry_error}")
                return False
        except Exception as e:
            logger.error(f"Error clicking {description}: {e}")
            return False
    
    def _extract_span_messages(self, container=None) -> Dict[str, str]:
        """Extract all span messages from the form - these contain labels, hints, and requirements
        Returns a dict of span_id -> span_text for context"""
        try:
            if container is None:
                container = self.driver
            
            span_messages = {}
            
            # Find all span elements with text content
            try:
                spans = container.find_elements(By.XPATH, ".//span[normalize-space(text())]")
                for span in spans:
                    try:
                        span_id = span.get_attribute("id") or ""
                        span_text = span.text.strip()
                        
                        if span_text and len(span_text) > 0:
                            # Skip very short or common words
                            if len(span_text) > 2:
                                if span_id:
                                    span_messages[span_id] = span_text
                                else:
                                    # Even without ID, store by class or partial content
                                    classes = span.get_attribute("class") or ""
                                    key = f"span_{classes.split()[0] if classes else 'unknown'}_{hash(span_text) % 10000}"
                                    span_messages[key] = span_text
                    except:
                        continue
            except:
                pass
            
            if span_messages:
                logger.info(f"Extracted {len(span_messages)} span messages:")
                for span_id, text in list(span_messages.items())[:5]:  # Log first 5
                    logger.debug(f"  {span_id}: {text[:80]}")
            
            return span_messages
            
        except Exception as e:
            logger.warning(f"Error extracting span messages: {e}")
            return {}
    
    def _get_field_context(self, field_elem, span_messages: Dict[str, str] = None) -> str:
        """Get all available context for a field including span messages
        Returns a comprehensive context string for GPT"""
        try:
            context_parts = []
            
            # Get direct field info
            field_id = field_elem.get_attribute("id") or ""
            field_name = field_elem.get_attribute("name") or ""
            placeholder = field_elem.get_attribute("placeholder") or ""
            aria_label = field_elem.get_attribute("aria-label") or ""
            field_type = field_elem.get_attribute("type") or ""
            
            if field_id:
                context_parts.append(f"Field ID: {field_id}")
            if field_name:
                context_parts.append(f"Field Name: {field_name}")
            if placeholder:
                context_parts.append(f"Placeholder: {placeholder}")
            if aria_label:
                context_parts.append(f"Aria Label: {aria_label}")
            if field_type:
                context_parts.append(f"Type: {field_type}")
            
            # Look for nearby span messages that might be hints or labels
            if span_messages:
                # Try to find spans near this field
                try:
                    parent = field_elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'form-element') or contains(@class, 'form-field')][1]")
                    # Look for spans in parent
                    for span_id, span_text in span_messages.items():
                        try:
                            # Try to find this span in parent
                            parent.find_element(By.ID, span_id)
                            context_parts.append(f"Label/Hint: {span_text}")
                        except:
                            pass
                except:
                    pass
            
            return " | ".join(context_parts) if context_parts else ""
            
        except Exception as e:
            logger.warning(f"Error getting field context: {e}")
            return ""
    
    def _read_error_messages(self) -> List[str]:
        """Read all error messages from the current page for intelligent retry"""
        errors = []
        try:
            # Common LinkedIn error message selectors
            error_selectors = [
                "span.artdeco-inline-feedback__message",
                "div.artdeco-inline-feedback--error",
                "span[role='alert']",
                "div.fb-form-element-error",
                ".artdeco-inline-feedback__message",
                "span[data-test-form-builder-error]",
                "div[class*='error']",
            ]
            
            for selector in error_selectors:
                try:
                    error_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in error_elements:
                        if elem.is_displayed():
                            error_text = elem.text.strip()
                            if error_text and len(error_text) > 2:
                                errors.append(error_text)
                                logger.warning(f"🔴 Form error detected: {error_text}")
                except:
                    continue
            
            # Also check XPath-based errors
            try:
                xpath_errors = self.driver.find_elements(By.XPATH, "//*[contains(@class, 'error') or contains(@class, 'invalid')]//*[contains(text(), '')]")
                for elem in xpath_errors:
                    if elem.is_displayed():
                        error_text = elem.text.strip()
                        if error_text and len(error_text) > 2 and error_text not in errors:
                            errors.append(error_text)
                            logger.warning(f"🔴 Form error detected: {error_text}")
            except:
                pass
        except Exception as e:
            logger.debug(f"Error reading error messages: {e}")
        
        return errors

    def fill_form_with_ai(self) -> Tuple[bool, str]:
        """
        Fill form dynamically - discovers all fields in one pass.
        OPTIMIZED VERSION: Fast filling with intelligent error detection and retry.
        """
        try:
            # Verify driver is still alive
            if not self.driver:
                return False, "Driver is not initialized"
            
            try:
                _ = self.driver.current_url
            except:
                return False, "Driver has crashed or disconnected"
            
            wait = WebDriverWait(self.driver, 10)
            time.sleep(0.2)  # OPTIMIZED: Let form load quickly
            
            # Extract ALL span messages from the page for context
            span_messages = self._extract_span_messages()
            if span_messages:
                self.span_messages = span_messages  # Store for use in field handlers
            
            results = []
            
            # Try multiline text fields (textareas, summaries, cover letters)
            try:
                success, msg = self._fill_multiline_text()
                results.append(("multiline", success, msg))
            except Exception as e:
                logger.error(f"Multiline text exception: {e}")
                results.append(("multiline", False, str(e)))
            
            # Try location/typeahead fields
            try:
                success, msg = self._fill_location_fields()
                results.append(("location", success, msg))
            except Exception as e:
                logger.error(f"Location field exception: {e}")
                results.append(("location", False, str(e)))
            
            # Try text inputs (single line)
            try:
                success, msg = self._fill_text_inputs()
                results.append(("text", success, msg))
            except Exception as e:
                logger.error(f"Text input exception: {e}")
                results.append(("text", False, str(e)))
            
            # Try radio buttons
            try:
                success, msg = self._fill_radio_buttons()
                results.append(("radio", success, msg))
            except Exception as e:
                logger.error(f"Radio button exception: {e}")
                results.append(("radio", False, str(e)))
            
            # Try dropdowns/selects
            try:
                success, msg = self._fill_dropdowns()
                results.append(("dropdown", success, msg))
            except Exception as e:
                logger.error(f"Dropdown exception: {e}")
                results.append(("dropdown", False, str(e)))
            
            # Try file inputs (resume upload) - only if temp_resume_path is set
            if self.temp_resume_path:
                try:
                    success, msg = self._fill_file_inputs()
                    results.append(("file_upload", success, msg))
                except Exception as e:
                    logger.error(f"File upload exception: {e}")
                    results.append(("file_upload", False, str(e)))
            
            # Check if ANY fields were filled
            any_success = any(success for _, success, _ in results)
            
            if not any_success:
                logger.error("Failed to fill any form fields")
                return False, "Failed to fill any fields"
            
            # Report what was filled
            filled = [ftype for ftype, success, _ in results if success]
            logger.info(f"Successfully filled: {', '.join(filled)}")
            
            # INTELLIGENT ERROR CHECK: Read errors and retry if needed
            errors = self._read_error_messages()
            if errors:
                logger.warning(f"🔄 Detected {len(errors)} errors after filling, attempting intelligent retry...")
                
                # Retry with error context for failed fields
                retry_success = self._retry_with_error_context(errors, results)
                if retry_success:
                    logger.info("✅ Successfully fixed errors on retry")
                    return True, f"Form filled with error correction: {', '.join(filled)}"
                else:
                    logger.warning("⚠️ Some errors remain after retry, but continuing...")
            
            return True, f"Form filled: {', '.join(filled)}"
            
        except Exception as e:
            logger.error(f"Error in fill_form_with_ai: {e}", exc_info=True)
            return False, f"Form filling error: {str(e)}"
    
    def _retry_with_error_context(self, errors: List[str], previous_results) -> bool:
        """
        Intelligently retry form filling using error messages as context
        Returns True if errors were successfully resolved
        """
        try:
            logger.info(f"🔄 Retrying with error context: {errors}")
            
            # Build error context for GPT
            error_context = "\\n".join(f"- {err}" for err in errors)
            
            # Find fields that likely caused errors
            for error_msg in errors:
                error_lower = error_msg.lower()
                
                # Identify field type from error message
                if "required" in error_lower or "cannot be blank" in error_lower:
                    # Try to fill empty required fields
                    if "phone" in error_lower:
                        self._retry_fill_specific_field("phone", error_msg)
                    elif "email" in error_lower:
                        self._retry_fill_specific_field("email", error_msg)
                    elif "linkedin" in error_lower:
                        self._retry_fill_specific_field("linkedin_url", error_msg)
                    elif "location" in error_lower:
                        self._retry_fill_specific_field("location", error_msg)
                    else:
                        # Generic required field - retry all text inputs
                        self._fill_text_inputs()
                
                elif "invalid" in error_lower or "format" in error_lower:
                    # Format error - retry with corrected format
                    if "phone" in error_lower:
                        self._retry_fill_specific_field("phone", error_msg, fix_format=True)
                    elif "url" in error_lower or "linkedin" in error_lower:
                        self._retry_fill_specific_field("linkedin_url", error_msg, fix_format=True)
                    elif "email" in error_lower:
                        self._retry_fill_specific_field("email", error_msg, fix_format=True)
                
                elif "numeric" in error_lower or "number" in error_lower:
                    # Numeric format error
                    self._retry_fill_specific_field("numeric", error_msg, fix_format=True)
            
            # Brief pause to let DOM update
            time.sleep(0.2)
            
            # Check if errors cleared
            remaining_errors = self._read_error_messages()
            if len(remaining_errors) < len(errors):
                logger.info(f"✅ Reduced errors from {len(errors)} to {len(remaining_errors)}")
                return True
            else:
                logger.warning(f"⚠️ Still have {len(remaining_errors)} errors after retry")
                return False
                
        except Exception as e:
            logger.error(f"Error in retry logic: {e}")
            return False
    
    def _retry_fill_specific_field(self, field_type: str, error_message: str, fix_format: bool = False):
        """Retry filling a specific field type with error context"""
        try:
            logger.info(f"🔧 Retrying {field_type} field due to: {error_message}")
            
            # Find all input fields that might match
            if field_type == "phone":
                selectors = ["input[type='tel']", "input[name*='phone']", "input[id*='phone']"]
                for selector in selectors:
                    try:
                        fields = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for field in fields:
                            if field.is_displayed():
                                field.clear()
                                # Format phone properly
                                phone = "+1-555-123-4567"  # Default format
                                field.send_keys(phone)
                                logger.info(f"✓ Retried phone field with: {phone}")
                                time.sleep(0.1)
                                return
                    except:
                        continue
            
            elif field_type == "email":
                selectors = ["input[type='email']", "input[name*='email']", "input[id*='email']"]
                for selector in selectors:
                    try:
                        fields = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for field in fields:
                            if field.is_displayed() and not field.get_attribute("value"):
                                field.clear()
                                # Extract or create email
                                import re
                                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', self.resume)
                                email = email_match.group(0) if email_match else "candidate@email.com"
                                field.send_keys(email)
                                logger.info(f"✓ Retried email field with: {email}")
                                time.sleep(0.1)
                                return
                    except:
                        continue
            
            elif field_type == "linkedin_url":
                selectors = ["input[name*='linkedin']", "input[id*='linkedin']", "input[placeholder*='linkedin' i]"]
                for selector in selectors:
                    try:
                        fields = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for field in fields:
                            if field.is_displayed():
                                field.clear()
                                # Format LinkedIn URL properly
                                linkedin_url = "https://linkedin.com/in/candidate-profile"
                                field.send_keys(linkedin_url)
                                logger.info(f"✓ Retried LinkedIn field with: {linkedin_url}")
                                time.sleep(0.1)
                                return
                    except:
                        continue
            
            elif field_type == "location":
                # Retry location fields
                self._fill_location_fields()
            
            elif field_type == "numeric":
                # Find numeric inputs and retry
                selectors = ["input[type='number']", "input[inputmode='numeric']"]
                for selector in selectors:
                    try:
                        fields = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for field in fields:
                            if field.is_displayed() and not field.get_attribute("value"):
                                field.clear()
                                field.send_keys("2")  # Default reasonable value
                                logger.info(f"✓ Retried numeric field with: 2")
                                time.sleep(0.1)
                    except:
                        continue
        
        except Exception as e:
            logger.error(f"Error retrying field {field_type}: {e}")
    
    def _fill_multiline_text(self) -> Tuple[bool, str]:
        """Fill multiline text fields (textareas) - covers summaries, cover letters, etc. - IMPROVED"""
        try:
            # Find all multiline text form components with enhanced selectors
            selectors = [
                "textarea",  # Most direct selector
                "[data-test-form-builder-multiline-text-form-component]",
                "textarea.artdeco-text-input--input",
                "[id*='multiline-text-form-component']",
                "[id*='text-area']",
                "div[data-test-form-builder-multiline-text-form-component] textarea",
                "input[data-test*='multiline']",
            ]
            
            textarea_elements = []
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    textarea_elements.extend(elements)
                except:
                    pass
            
            # Also search by XPath for textareas
            try:
                xpath_textareas = self.driver.find_elements(By.XPATH, "//textarea")
                textarea_elements.extend(xpath_textareas)
            except:
                pass
            
            if not textarea_elements:
                logger.info("No multiline text fields found")
                return True, "No multiline fields found"
            
            # Remove duplicates by comparing element location
            seen = set()
            unique_elements = []
            for elem in textarea_elements:
                try:
                    location = elem.location
                    loc_key = (location.get('x'), location.get('y'))
                    if loc_key not in seen:
                        seen.add(loc_key)
                        unique_elements.append(elem)
                except:
                    unique_elements.append(elem)
            
            textarea_elements = unique_elements
            logger.info(f"Found {len(textarea_elements)} multiline text fields")
            
            # Build questions for these textareas
            questions = []
            for idx, elem in enumerate(textarea_elements):
                try:
                    # Find the label for this textarea
                    label_text = ""
                    
                    # Try to find label in various ways
                    try:
                        # Method 1: Find label in parent form component
                        parent = elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'form-element') or contains(@class, 'form-component') or contains(@class, 'form-field') or contains(@class, 'fb-dash')][1]")
                        
                        # Try to find spans within parent (contains hints/labels)
                        try:
                            parent_spans = parent.find_elements(By.XPATH, ".//span")
                            if parent_spans:
                                span_texts = [s.text.strip() for s in parent_spans if s.text.strip() and len(s.text.strip()) > 3]
                                if span_texts:
                                    label_text = " | ".join(span_texts[:2])  # Use first 2 span texts
                        except:
                            pass
                        
                        # Fallback to label/legend elements
                        if not label_text:
                            try:
                                label_elem = parent.find_element(By.XPATH, ".//label | .//span[@class='artdeco-form-label']")
                                label_text = label_elem.text.strip()
                            except:
                                pass
                        
                        if not label_text:
                            try:
                                label_elem = parent.find_element(By.XPATH, ".//h3 | .//span[contains(@class, 'label')]")
                                label_text = label_elem.text.strip()
                            except:
                                pass
                    except:
                        pass
                    
                    # Method 2: Check field ID or name for hints
                    if not label_text:
                        field_id = elem.get_attribute("id") or ""
                        field_name = elem.get_attribute("name") or ""
                        
                        if "cover" in field_id.lower() or "cover" in field_name.lower():
                            label_text = "Cover Letter"
                        elif "summary" in field_id.lower() or "summary" in field_name.lower():
                            label_text = "Professional Summary"
                        elif "additional" in field_id.lower():
                            label_text = "Additional Information"
                        elif "message" in field_id.lower():
                            label_text = "Message"
                        else:
                            label_text = f"Additional Information {idx+1}"
                    
                    # Method 3: Get placeholder or aria-label
                    if not label_text:
                        placeholder = elem.get_attribute("placeholder") or ""
                        aria_label = elem.get_attribute("aria-label") or ""
                        if placeholder:
                            label_text = placeholder
                        elif aria_label:
                            label_text = aria_label
                        else:
                            label_text = f"Text field {idx+1}"
                    
                    questions.append(label_text)
                    
                except Exception as e:
                    logger.warning(f"Error processing textarea {idx}: {e}")
                    continue
            
            if not questions:
                return True, "No valid multiline questions"
            
            logger.info(f"Found multiline questions: {questions}")
            
            # Get AI answers for multiline fields
            answers = self._get_gpt_answers_for_multiline(questions)
            
            if not answers:
                logger.error("Failed to get AI answers for multiline fields")
                return False, "Failed to get answers"
            
            # Fill textareas
            filled_count = 0
            for i, textarea in enumerate(textarea_elements):
                if i >= len(answers):
                    break
                
                try:
                    answer = str(answers[i]).strip()
                    
                    # Step 1: Scroll into view
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", textarea
                    )
                    time.sleep(0.3)
                    
                    # Step 2: Check if element is visible and enabled before interacting
                    is_displayed = textarea.is_displayed()
                    is_enabled = textarea.is_enabled()
                    
                    if not is_displayed:
                        logger.warning(f"Textarea {i+1} is not displayed, skipping")
                        continue
                    
                    if not is_enabled:
                        logger.warning(f"Textarea {i+1} is not enabled, skipping")
                        continue
                    
                    # Step 3: Wait for element to be interactable with retry logic
                    interactable = False
                    for retry in range(3):
                        try:
                            wait = WebDriverWait(self.driver, 1)
                            wait.until(EC.element_to_be_clickable(textarea))
                            interactable = True
                            break
                        except:
                            if retry < 2:
                                time.sleep(0.2)
                            else:
                                logger.warning(f"Element {i+1} not interactable after retries, attempting anyway")
                    
                    # Step 4: Focus and clear the field using JavaScript for better reliability
                    try:
                        # Use JavaScript to set focus and clear
                        self.driver.execute_script("""
                            arguments[0].focus();
                            arguments[0].click();
                            arguments[0].value = '';
                            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                        """, textarea)
                        time.sleep(0.1)
                    except Exception as clear_error:
                        logger.warning(f"JavaScript clear failed for textarea {i+1}, trying Selenium methods: {clear_error}")
                        try:
                            textarea.click()
                            time.sleep(0.05)
                            textarea.send_keys(Keys.CONTROL + "a")
                            textarea.send_keys(Keys.DELETE)
                        except:
                            pass
                    
                    time.sleep(0.05)
                    
                    # Step 5: Fill the field with retry logic
                    fill_success = False
                    for retry in range(2):
                        try:
                            textarea.send_keys(answer)
                            time.sleep(0.1)
                            
                            # Verify
                            current_value = textarea.get_attribute("value")
                            if current_value == answer:
                                filled_count += 1
                                logger.info(f"✓ Filled multiline {i+1} ({questions[i]}): {answer[:50]}...")
                                fill_success = True
                                break
                            else:
                                logger.warning(f"Verification failed for {i+1}, retrying...")
                                if retry == 0:
                                    # Clear and retry
                                    self.driver.execute_script("arguments[0].value = '';", textarea)
                                    time.sleep(0.05)
                        except Exception as fill_error:
                            if retry == 0:
                                logger.warning(f"First attempt failed for {i+1}: {fill_error}, retrying...")
                                time.sleep(0.2)
                            else:
                                raise
                    
                    if not fill_success:
                        logger.error(f"Failed to fill multiline {i+1} after retries")
                        
                except Exception as e:
                    logger.error(f"Error filling multiline {i+1}: {e}", exc_info=False)
                    continue
            
            logger.info(f"Successfully filled {filled_count}/{len(textarea_elements)} multiline fields")
            return filled_count > 0, f"Multiline filled: {filled_count}/{len(textarea_elements)}"
            
        except Exception as e:
            logger.error(f"Error in _fill_multiline_text: {e}", exc_info=True)
            return False, f"Multiline error: {str(e)}"
    
    def _fill_location_fields(self) -> Tuple[bool, str]:
        """Fill location/typeahead fields - IMPROVED DETECTION"""
        try:
            # Find location/typeahead components with improved selectors
            # LinkedIn uses data-test-form-builder-single-typeahead-entity-form-component
            selectors = [
                "[data-test-form-builder-single-typeahead-entity-form-component]",
                "[id*='single-typeahead-entity-form-component']",
                "input[aria-label*='location' i]",
                "input[placeholder*='location' i]",
                "[data-test-form-builder-geo-location-form-component]",
            ]
            
            location_containers = []
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    location_containers.extend(elements)
                except:
                    pass
            
            # Also look for input fields inside location-specific parent divs
            try:
                parent_containers = self.driver.find_elements(
                    By.XPATH, "//div[contains(@class, 'form-element')]//input[contains(@id, 'location') or contains(@id, 'geo') or contains(@placeholder, 'location')]"
                )
                location_containers.extend(parent_containers)
            except:
                pass
            
            if not location_containers:
                logger.info("No location/typeahead fields found")
                return True, "No location fields found"
            
            # Remove duplicates by element id
            seen_ids = set()
            unique_containers = []
            for elem in location_containers:
                try:
                    elem_id = elem.get_attribute("id") or id(elem)
                    if elem_id not in seen_ids:
                        seen_ids.add(elem_id)
                        unique_containers.append(elem)
                except:
                    unique_containers.append(elem)
            
            location_containers = unique_containers
            logger.info(f"Found {len(location_containers)} location fields")
            
            # Build questions
            questions = []
            input_elements = []
            for idx, container in enumerate(location_containers):
                try:
                    # Find label
                    label_text = ""
                    input_elem = None
                    
                    # If container is already an input, use it
                    if container.tag_name.lower() == "input":
                        input_elem = container
                        # Try to find label for this input
                        input_id = input_elem.get_attribute("id")
                        if input_id:
                            try:
                                label = self.driver.find_element(By.XPATH, f"//label[@for='{input_id}']")
                                label_text = label.text.strip()
                            except:
                                pass
                    else:
                        # It's a container - find the input inside
                        try:
                            input_elem = container.find_element(By.CSS_SELECTOR, "input")
                        except:
                            try:
                                input_elem = container.find_element(By.XPATH, ".//input")
                            except:
                                pass
                    
                    # Try to find label from parent structure
                    if not label_text and input_elem:
                        try:
                            parent = input_elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'form-element') or contains(@class, 'form-component') or contains(@class, 'form-field')][1]")
                            label_elem = parent.find_element(By.XPATH, ".//label | .//span[@class='artdeco-form-label']")
                            label_text = label_elem.text.strip()
                        except:
                            pass
                    
                    if not label_text:
                        # Try alternative methods
                        if input_elem:
                            placeholder = input_elem.get_attribute("placeholder") or ""
                            aria_label = input_elem.get_attribute("aria-label") or ""
                            if placeholder:
                                label_text = placeholder
                            elif aria_label:
                                label_text = aria_label
                            else:
                                label_text = "Location"
                        else:
                            label_text = "Location"
                    
                    if input_elem:
                        questions.append(label_text)
                        input_elements.append(input_elem)
                    
                except Exception as e:
                    logger.warning(f"Error processing location {idx}: {e}")
                    continue
            
            if not questions:
                return True, "No valid location questions"
            
            logger.info(f"Location questions: {questions}")
            
            # Get location answers from AI
            answers = self._get_gpt_answers_for_locations(questions)
            
            if not answers:
                logger.error("Failed to get location answers from AI")
                return False, "Failed to get location answers"
            
            # Fill location fields
            filled_count = 0
            for i, input_elem in enumerate(input_elements):
                if i >= len(answers):
                    break
                
                try:
                    # Scroll into view
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", input_elem
                    )
                    time.sleep(0.05)
                    
                    # Click to activate quickly
                    try:
                        input_elem.click()
                    except:
                        self.driver.execute_script("arguments[0].click();", input_elem)
                    
                    # Clear field completely
                    for _ in range(3):
                        input_elem.send_keys(Keys.CONTROL + "a")
                        input_elem.send_keys(Keys.DELETE)
                    time.sleep(0.05)
                    
                    answer = str(answers[i]).strip()
                    
                    # Type answer quickly
                    input_elem.send_keys(answer)
                    
                    time.sleep(0.2)  # Wait for dropdown to populate
                    
                    # Try to select the first suggestion
                    try:
                        # Look for dropdown suggestions - multiple selectors for different LinkedIn versions
                        suggestions = self.driver.find_elements(
                            By.CSS_SELECTOR, 
                            "[role='option'], .artdeco-typeahead__op, li[role='option'], .typeahead-suggestion, div[data-test-typeahead-suggestion]"
                        )
                        
                        if suggestions:
                            # Click first suggestion
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", suggestions[0])
                            time.sleep(0.05)
                            suggestions[0].click()
                            
                            filled_count += 1
                            logger.info(f"✓ Selected location {i+1}: {answer}")
                        else:
                            # If no suggestions, press Tab or Enter to accept the value
                            input_elem.send_keys(Keys.TAB)
                            time.sleep(0.1)
                            filled_count += 1
                            logger.info(f"✓ Entered location {i+1}: {answer}")
                            
                    except Exception as e:
                        logger.warning(f"Error selecting location suggestion {i+1}: {e}")
                        # Try pressing Tab/Enter as fallback
                        try:
                            input_elem.send_keys(Keys.TAB)
                            time.sleep(0.3)
                            filled_count += 1
                        except:
                            pass
                        
                except Exception as e:
                    logger.error(f"Error filling location {i+1}: {e}")
                    continue
            
            logger.info(f"Successfully filled {filled_count}/{len(input_elements)} location fields")
            return filled_count > 0, f"Location filled: {filled_count}/{len(input_elements)}"
            
        except Exception as e:
            logger.error(f"Error in _fill_location_fields: {e}", exc_info=True)
            return False, f"Location error: {str(e)}"
    
    def _fill_text_inputs(self) -> Tuple[bool, str]:
        """Fill text input fields using AI - IMPROVED VERSION with better field type detection"""
        try:
            # Try to wait for form to be loaded, but don't crash if not present
            try:
                wait = WebDriverWait(self.driver, 5)
                wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input.artdeco-text-input--input")
                ))
            except TimeoutException:
                logger.info("No text input elements found within timeout")
                return True, "No text inputs found"
            
            time.sleep(0.3)  # Allow animations to complete quickly
            
            # Get fresh elements each time
            box_elements = self.driver.find_elements(
                By.CSS_SELECTOR, "label.artdeco-text-input--label"
            )
            
            if not box_elements:
                logger.info("No text input labels found")
                return True, "No text inputs found"
            
            # Build questions with field inspection
            questions = []
            field_types = []  # Track the type of each field
            
            for elem in box_elements:
                label_text = elem.text.strip()
                if not label_text:
                    continue
                
                # Try to find associated input to check attributes
                field_type = "text"
                try:
                    parent = elem.find_element(By.XPATH, "./parent::*")
                    input_elem = parent.find_element(By.CSS_SELECTOR, "input")
                    
                    # NEW: Look for nearby span messages that provide hints
                    try:
                        # Find spans in parent container
                        parent_container = input_elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'form-element') or contains(@class, 'form-field')][1]")
                        nearby_spans = parent_container.find_elements(By.XPATH, ".//span[normalize-space()]")
                        for span in nearby_spans:
                            span_text = span.text.strip()
                            if span_text and len(span_text) > 3 and span_text != label_text:
                                # Add span text to label for context
                                label_text = f"{label_text} ({span_text})"
                                break
                    except:
                        pass
                    
                    # Check for hints in placeholder, type, etc.
                    placeholder = input_elem.get_attribute("placeholder") or ""
                    input_type = input_elem.get_attribute("type") or "text"
                    field_id = input_elem.get_attribute("id") or ""
                    field_name = input_elem.get_attribute("name") or ""
                    
                    # Determine field type based on various attributes
                    if input_type == "number":
                        field_type = "numeric"
                        label_text = f"{label_text} (numeric answer only - no units or text)"
                    elif "linkedin" in field_id.lower() or "linkedin" in placeholder.lower() or "linkedin" in label_text.lower():
                        field_type = "linkedin_url"
                        label_text = f"{label_text} (LinkedIn profile URL - e.g., https://linkedin.com/in/yourprofile)"
                    elif "phone" in field_id.lower() or "phone" in placeholder.lower() or "phone" in label_text.lower():
                        field_type = "phone"
                        label_text = f"{label_text} (phone number)"
                    elif "email" in field_id.lower() or "email" in placeholder.lower() or "email" in label_text.lower():
                        field_type = "email"
                        label_text = f"{label_text} (email address)"
                    elif "year" in label_text.lower() or "experience" in label_text.lower():
                        field_type = "numeric"
                        label_text = f"{label_text} (numeric - e.g., 2.5 for 2-3 years)"
                    
                    if placeholder and "hint" not in label_text:
                        label_text = f"{label_text} (hint: {placeholder})"
                        
                except:
                    pass
                
                questions.append(label_text)
                field_types.append(field_type)
            
            if not questions:
                return True, "No valid text input questions"
            
            logger.info(f"Found {len(questions)} text input questions: {field_types}")
            
            # Get AI answers with field type context
            answers = self._get_gpt_answers_for_boxes(questions, field_types)
            
            if not answers:
                logger.error("Failed to get AI answers for text inputs")
                return False, "Failed to get AI answers for text inputs"
            
            # RE-QUERY for fresh input elements
            input_elements = self.driver.find_elements(
                By.CSS_SELECTOR, "input.artdeco-text-input--input"
            )
            
            filled_count = 0
            for i, inp in enumerate(input_elements):
                if i >= len(answers):
                    break

                try:
                    # Scroll into view
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", inp
                    )
                    time.sleep(0.05)

                    # Clear field
                    inp.clear()
                    time.sleep(0.05)

                    # Enter answer
                    answer = str(answers[i]).strip()

                    # Special handling for phone number fields
                    field_name = inp.get_attribute("name") or inp.get_attribute("id") or ""
                    if "phone" in field_name.lower():
                        import re
                        # Try to extract phone from resume/contact if available
                        phone_from_resume = None
                        import json as _json
                        try:
                            resume_json = _json.loads(self.resume) if isinstance(self.resume, str) else self.resume
                            contact = resume_json.get("basic_info", {}).get("contact", {})
                            phone_from_resume = contact.get("phone")
                        except Exception as e:
                            phone_from_resume = None
                        # Prefer phone from resume if valid
                        if phone_from_resume:
                            phone_digits = re.sub(r"\D", "", phone_from_resume)
                            if len(phone_digits) >= 10:
                                answer = phone_from_resume
                                logger.info(f"Using phone number from resume for input {i+1}: '{answer}'")
                            else:
                                logger.warning(f"Phone from resume invalid: '{phone_from_resume}'")
                        # Fallback to GPT answer if valid
                        phone_digits = re.sub(r"\D", "", answer)
                        # Regex to match any variant of the placeholder
                        placeholder_pattern = re.compile(r"^(\+?92[- ]?300[- ]?1234567|923001234567)$")
                        if len(phone_digits) < 10 or placeholder_pattern.match(answer.replace(" ", "").replace("-", "")):
                            logger.warning(f"Skipping invalid phone number for input {i+1}: '{answer}' (matched placeholder)")
                            answer = ""  # Leave blank or use a fallback if available
                        else:
                            logger.info(f"Using phone number for input {i+1}: '{answer}'")

                    # For numeric fields, ensure we only have numbers
                    if i < len(field_types) and field_types[i] == "numeric":
                        import re as regex_module
                        numeric_match = regex_module.search(r'-?\d+\.?\d*', answer)
                        if numeric_match:
                            answer = numeric_match.group(0)
                        logger.info(f"Numeric field {i+1}: using value '{answer}'")

                    inp.send_keys(answer)
                    time.sleep(0.05)

                    # Verify it was filled
                    current_value = inp.get_attribute("value")
                    if current_value == answer:
                        filled_count += 1
                        logger.info(f"✓ Filled input {i+1} ({field_types[i] if i < len(field_types) else 'text'}): {answer}")
                    else:
                        logger.warning(f"✗ Failed to verify input {i+1}")

                except Exception as e:
                    logger.error(f"Error filling input {i+1}: {e}")
                    continue
            
            logger.info(f"Successfully filled {filled_count}/{len(input_elements)} text inputs")
            
            
            # STEP 2: Check for validation errors and retry with corrections
            time.sleep(0.2)  # Let validation messages appear
            
            # Find all error messages
            error_elements = self.driver.find_elements(
                By.CSS_SELECTOR, ".artdeco-inline-feedback--error, .fb-dash-form-element__error-text"
            )
            
            if error_elements:
                errors_with_context = []
                
                for error_elem in error_elements:
                    error_text = error_elem.text.strip()
                    if not error_text:
                        continue
                    
                    # Try to find the associated input field and its label
                    try:
                        # Find parent container
                        parent = error_elem
                        for _ in range(5):
                            parent = parent.find_element(By.XPATH, "..")
                            # Look for input and label in this container
                            try:
                                input_field = parent.find_element(By.CSS_SELECTOR, "input")
                                label = parent.find_element(By.CSS_SELECTOR, "label")
                                label_text = label.text.strip()
                                current_value = input_field.get_attribute("value")
                                
                                errors_with_context.append({
                                    'label': label_text,
                                    'error': error_text,
                                    'current_value': current_value,
                                    'input_element': input_field
                                })
                                break
                            except:
                                continue
                    except:
                        pass
                
                if errors_with_context:
                    logger.warning(f"Found {len(errors_with_context)} validation errors, retrying with corrections...")
                    
                    # Build correction prompts
                    for err_info in errors_with_context:
                        correction_prompt = f"""VALIDATION ERROR CORRECTION NEEDED:

Question: {err_info['label']}
Your previous answer: {err_info['current_value']}
ERROR MESSAGE: {err_info['error']}

Resume: {self.resume}

The form rejected your answer. Based on the error message, provide the CORRECT answer.

CRITICAL RULES:
- If error says "Enter a decimal number", respond with ONLY a number (e.g., "1.0", "30.0")
- Convert text to numbers: "1 month" → "1.0", "2 weeks" → "0.5", "immediate" → "0.0"
- For notice periods in months, just give the number: "1.0", "2.0", "3.0"
- NO text, NO units, ONLY the numeric value

Provide ONLY the corrected answer, nothing else:"""
                        
                        corrected_answer = self.ask_gpt(correction_prompt)
                        if corrected_answer:
                            corrected_answer = corrected_answer.strip().strip('"\'')
                            
                            # Apply correction
                            try:
                                input_elem = err_info['input_element']
                                self.driver.execute_script(
                                    "arguments[0].scrollIntoView({block: 'center'});", input_elem
                                )
                                time.sleep(0.05)
                                input_elem.clear()
                                time.sleep(0.05)
                                input_elem.send_keys(corrected_answer)
                                time.sleep(0.1)
                                logger.info(f"✓ Corrected: '{err_info['current_value']}' → '{corrected_answer}'")
                                filled_count += 1
                            except Exception as e:
                                logger.error(f"Failed to apply correction: {e}")
            
            # Return success even if some failed
            return True, f"Text inputs filled: {filled_count}/{len(input_elements)}"
            
        except Exception as e:
            logger.error(f"Error in _fill_text_inputs: {e}", exc_info=True)
            return False, f"Text input error: {str(e)}"
    
    def _fill_radio_buttons(self) -> Tuple[bool, str]:
        """Fill radio buttons - IMPROVED VERSION with better matching"""
        try:
            wait = WebDriverWait(self.driver, 5)
            
            # Find all radio button fieldsets
            fieldsets = self.driver.find_elements(
                By.CSS_SELECTOR, "fieldset[data-test-form-builder-radio-button-form-component]"
            )
            
            if not fieldsets:
                # Try alternative selector
                fieldsets = self.driver.find_elements(
                    By.XPATH, "//fieldset[contains(@data-test, 'radio')]"
                )
            
            if not fieldsets:
                logger.info("No radio button fieldsets found")
                return True, "No radio buttons found"
            
            logger.info(f"Found {len(fieldsets)} radio button groups")
            
            questions = []
            radio_info = []  # Store info for matching later
            
            for fieldset_idx, fieldset in enumerate(fieldsets):
                try:
                    # Get question text - try multiple selectors
                    question_text = ""
                    try:
                        legend = fieldset.find_element(By.CSS_SELECTOR, "legend")
                        question_text = legend.text.strip()
                    except:
                        try:
                            legend = fieldset.find_element(By.XPATH, ".//label[1]")
                            question_text = legend.text.strip()
                        except:
                            try:
                                legend = fieldset.find_element(By.XPATH, ".//*[contains(@class, 'label') or contains(@class, 'legend')][1]")
                                question_text = legend.text.strip()
                            except:
                                pass
                    
                    # Get available options - find all radio buttons and their labels
                    options = []
                    labels = fieldset.find_elements(By.CSS_SELECTOR, "label")
                    
                    # Also try to find radio inputs
                    radio_inputs = fieldset.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                    
                    if labels:
                        options = [lbl.text.strip() for lbl in labels if lbl.text.strip()]
                    elif radio_inputs:
                        # If we found radio inputs but no label text, try to extract from parent labels
                        for radio in radio_inputs:
                            try:
                                parent = radio.find_element(By.XPATH, "./ancestor::label[1]")
                                parent_text = parent.text.strip()
                                if parent_text:
                                    options.append(parent_text)
                            except:
                                pass
                    
                    if question_text and options:
                        full_question = f"{question_text} Options: {', '.join(options)}"
                        questions.append(full_question)
                        radio_info.append({
                            'fieldset': fieldset,
                            'question': question_text,
                            'options': options,
                            'labels': labels,
                            'radio_inputs': radio_inputs
                        })
                    elif question_text:
                        # Even if no options extracted from labels, add the question
                        questions.append(f"{question_text} (radio button question)")
                        radio_info.append({
                            'fieldset': fieldset,
                            'question': question_text,
                            'options': options,
                            'labels': labels,
                            'radio_inputs': radio_inputs
                        })
                        
                except Exception as e:
                    logger.warning(f"Error parsing radio fieldset {fieldset_idx}: {e}")
                    continue
            
            if not questions:
                return True, "No valid radio questions"
            
            logger.info(f"Radio questions: {questions}")
            
            # Get AI answers
            answers = self._get_gpt_answers_for_radios(questions)
            
            if not answers or len(answers) != len(fieldsets):
                logger.error(f"Answer count mismatch: {len(answers)} answers for {len(fieldsets)} questions")
                # Try to continue anyway with partial answers
                if not answers:
                    return False, "Failed to get matching AI answers"
            
            # Fill each fieldset
            filled_count = 0
            for i, (fieldset, answer) in enumerate(zip(fieldsets, answers)):
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", fieldset
                    )
                    time.sleep(0.05)
                    
                    answer_clean = str(answer).strip().lower()
                    
                    # Get radio info for this fieldset
                    info = radio_info[i] if i < len(radio_info) else None
                    labels = info['labels'] if info else fieldset.find_elements(By.CSS_SELECTOR, "label")
                    radio_inputs = info['radio_inputs'] if info else fieldset.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                    
                    clicked = False
                    
                    # Try 1: Match by label text
                    for label in labels:
                        label_text = label.text.strip()
                        # Fuzzy matching - check if answer is contained in label or label in answer
                        if (answer_clean == label_text.lower() or 
                            answer_clean in label_text.lower() or 
                            label_text.lower() in answer_clean or
                            # Also try partial word matching
                            any(word in label_text.lower() for word in answer_clean.split())):
                            
                            try:
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", label)
                                time.sleep(0.05)
                                
                                # Click to select
                                label.click()
                                time.sleep(0.05)
                                
                                clicked = True
                                logger.info(f"✓ Selected radio {i+1} label: {label_text}")
                                filled_count += 1
                                break
                            except Exception as e:
                                logger.warning(f"Failed to click label: {e}")
                                # Try clicking the associated input instead
                                try:
                                    label_for = label.get_attribute("for")
                                    if label_for:
                                        input_elem = fieldset.find_element(By.ID, label_for)
                                        input_elem.click()
                                        time.sleep(0.05)
                                        clicked = True
                                        logger.info(f"✓ Selected radio {i+1} via input: {label_text}")
                                        filled_count += 1
                                        break
                                except:
                                    pass
                    
                    # Try 2: Match by radio input value attribute if label matching failed
                    if not clicked and radio_inputs:
                        for radio in radio_inputs:
                            radio_value = radio.get_attribute("value") or ""
                            radio_id = radio.get_attribute("id") or ""
                            
                            if (answer_clean == radio_value.lower() or 
                                answer_clean == radio_id.lower() or
                                answer_clean in radio_value.lower()):
                                
                                try:
                                    self.driver.execute_script("arguments[0].scrollIntoView(true);", radio)
                                    time.sleep(0.05)
                                    radio.click()
                                    time.sleep(0.1)
                                    clicked = True
                                    logger.info(f"✓ Selected radio {i+1} by value: {radio_value}")
                                    filled_count += 1
                                    break
                                except:
                                    pass
                    
                    # Try 3: If still not clicked, try to find the first matching label with fuzzy match
                    if not clicked:
                        logger.warning(f"Exact match not found for '{answer_clean}', trying fuzzy matching...")
                        answer_words = answer_clean.split()
                        
                        for label in labels:
                            label_text = label.text.strip().lower()
                            # Check if any significant word from answer is in the label
                            if any(len(word) > 2 and word in label_text for word in answer_words):
                                try:
                                    label.click()
                                    time.sleep(0.1)
                                    clicked = True
                                    logger.info(f"✓ Selected radio {i+1} (fuzzy match): {label.text.strip()}")
                                    filled_count += 1
                                    break
                                except:
                                    pass
                    
                    if not clicked:
                        logger.warning(f"✗ Could not find radio option matching '{answer_clean}'")
                        
                except Exception as e:
                    logger.error(f"Error filling radio {i+1}: {e}")
                    continue
            
            logger.info(f"Successfully filled {filled_count}/{len(fieldsets)} radio button groups")
            return filled_count > 0, f"Radio buttons filled: {filled_count}/{len(fieldsets)}"
            
        except Exception as e:
            logger.error(f"Error in _fill_radio_buttons: {e}", exc_info=True)
            return False, f"Radio button error: {str(e)}"
    
    def _fill_dropdowns(self) -> Tuple[bool, str]:
        """Fill dropdown/select fields using AI"""
        try:
            # Wait for any selects to be present
            time.sleep(0.2)
            
            # Find all <select> elements used in LinkedIn forms
            select_elements = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "select[data-test-text-entity-list-form-select]"
            )
            
            if not select_elements:
                logger.info("No select dropdowns found")
                return True, "No dropdowns found"
            
            logger.info(f"Found {len(select_elements)} select elements")
            
            filled_count = 0
            
            for idx, select_elem in enumerate(select_elements):
                try:
                    # Scroll into view
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", select_elem)
                    time.sleep(0.05)
                    
                    # Check if field is required
                    is_required = False
                    try:
                        # Check aria-required attribute
                        aria_required = select_elem.get_attribute("aria-required")
                        if aria_required and aria_required.lower() == "true":
                            is_required = True
                        
                        # Check required attribute
                        required_attr = select_elem.get_attribute("required")
                        if required_attr is not None:
                            is_required = True
                    except:
                        pass
                    
                    # Get the label for this select
                    label_text = ""
                    label_elem = None
                    try:
                        # Look for associated label
                        select_id = select_elem.get_attribute("id")
                        if select_id:
                            label_elem = self.driver.find_element(By.XPATH, f"//label[@for='{select_id}']")
                            label_text = label_elem.text.strip()
                    except:
                        pass
                    
                    if not label_text:
                        # Try to find label in parent
                        try:
                            parent = select_elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'form-element') or contains(@class, 'form-component')][1]")
                            label_elem = parent.find_element(By.XPATH, ".//label | .//span[contains(@class, 'label')]")
                            label_text = label_elem.text.strip()
                        except:
                            label_text = f"Dropdown {idx+1}"
                    
                    # Check if label contains asterisk (required field indicator)
                    if "*" in label_text or (label_elem and "*" in label_elem.get_attribute("innerHTML")):
                        is_required = True
                    
                    # Log required field status
                    required_indicator = " [REQUIRED]" if is_required else ""
                    logger.info(f"Processing select {idx+1}: {label_text}{required_indicator}")
                    
                    # Get all available options
                    select = Select(select_elem)
                    options = select.options
                    available_values = [opt.text.strip() for opt in options if opt.text.strip() != "Select an option"]
                    
                    logger.info(f"Available options: {available_values}")
                    
                    # Ask GPT what to select with field-aware context
                    # Provide specific instructions for common field types
                    field_specific_instructions = ""
                    label_lower = label_text.lower()
                    
                    if any(word in label_lower for word in ['gender', 'sex']):
                        field_specific_instructions = """\n\nIMPORTANT: This is a gender field. You can infer gender from:
1. The person's name (common gender associations)
2. Pronouns used in the resume (he/his = Male, she/her = Female)
3. Explicit statements

Do NOT select 'Other' unless explicitly stated. If you can reasonably infer Male or Female from name or pronouns, select that option. Only respond 'Skip' if the name is truly ambiguous AND no pronouns are used."""
                    elif any(word in label_lower for word in ['race', 'ethnicity', 'ethnic']):
                        field_specific_instructions = "\n\nIMPORTANT: This is an ethnicity/race field. Select ONLY if explicitly mentioned in the resume. Otherwise, select 'Prefer not to answer' if available, or skip this field."
                    elif any(word in label_lower for word in ['disability', 'veteran']):
                        field_specific_instructions = "\n\nIMPORTANT: This is a protected category field. Select ONLY if explicitly mentioned in the resume with affirmative answer. Otherwise select 'No' or 'Prefer not to answer'."
                    elif any(word in label_lower for word in ['experience', 'used', 'familiar', 'knowledge', 'skill', 'proficient']) and set(available_values) == {'Yes', 'No'}:
                        # Technical skill Yes/No questions
                        field_specific_instructions = """\n\nIMPORTANT: This is a technical skill question with Yes/No options. 
- Analyze the resume and job description to determine if the candidate has this skill or experience.
- If the skill is mentioned in the resume or is related to skills mentioned, select 'Yes'.
- If the skill is clearly NOT in the resume and seems unrelated to their background, select 'No'.
- Be reasonable: related experience or similar technologies can count as 'Yes'."""
                    
                    prompt = f"""Based on the resume provided, select the most appropriate option for this form question.

Question: {label_text}
Available options: {', '.join(available_values)}

Resume:
{self.resume}"""
                    
                    # Add job description if available
                    if self.job_description:
                        prompt += f"""

Job Description:
{self.job_description}"""
                    
                    prompt += f"""{field_specific_instructions}

CRITICAL RULES:
1. Respond with ONLY the exact option text from the list exactly as it appears.
2. Do not add quotes, explanation, or any other text.
3. {'THIS IS A REQUIRED FIELD - you MUST select an option. Choose the most reasonable option based on the resume.' if is_required else "If you cannot determine a safe answer, respond with 'Skip' to mark this field for manual review."}"""
                    
                    answer_text = self.ask_gpt(prompt)
                    if not answer_text:
                        logger.warning(f"No answer from GPT for select {idx+1}")
                        continue
                    
                    answer = answer_text.strip().strip('"\'')
                    
                    # Check if GPT wants to skip this field
                    if answer.lower() == 'skip':
                        if is_required:
                            logger.error(f"❌ GPT tried to skip REQUIRED select {idx+1}: {label_text}. This should not happen!")
                            # For required fields, we could potentially select a default safe option here
                        else:
                            logger.warning(f"⊘ GPT recommends skipping optional select {idx+1}: {label_text}")
                        continue
                    
                    logger.info(f"Attempting to select '{answer}' for select {idx+1} ({label_text})")
                    
                    # Try to select by visible text first
                    try:
                        select.select_by_visible_text(answer)
                        logger.info(f"✓ Successfully selected '{answer}' by visible text")
                        filled_count += 1
                        time.sleep(0.1)
                        continue
                    except:
                        pass
                    
                    # Try to select by value
                    try:
                        select.select_by_value(answer)
                        logger.info(f"✓ Successfully selected '{answer}' by value")
                        filled_count += 1
                        time.sleep(0.1)
                        continue
                    except:
                        pass
                    
                    # Try partial match
                    for option in options:
                        option_text = option.text.strip()
                        if answer.lower() in option_text.lower() or option_text.lower() in answer.lower():
                            try:
                                select.select_by_visible_text(option_text)
                                logger.info(f"✓ Successfully selected '{option_text}' (partial match for '{answer}')")
                                filled_count += 1
                                time.sleep(0.1)
                                break
                            except:
                                continue
                    else:
                        logger.warning(f"Could not find option matching '{answer}' in select {idx+1}")
                    
                except Exception as e:
                    logger.error(f"Error processing select {idx+1}: {e}")
                    continue
            
            logger.info(f"Successfully filled {filled_count} select dropdowns")
            return True, f"Selects filled: {filled_count}"
            
        except Exception as e:
            logger.error(f"Error filling select dropdowns: {e}")
            return True, "Skipping selects"
    
    def _fill_file_inputs(self) -> Tuple[bool, str]:
        """
        Fill file input fields with temporary enhanced resume PDF.
        
        This method handles resume file uploads during LinkedIn Easy Apply.
        Uses the temp_resume_path if available (for AI-enhanced resumes).
        
        Returns:
            Tuple of (success, message)
        """
        try:
            # Log presence of temp resume path for debugging
            dry_run_env = os.getenv("SINGLE_JOB_APPLIER_DRY_RUN", "false").lower()
            dry_run = dry_run_env in ("1", "true", "yes")

            logger.info(f"Temp resume path: {self.temp_resume_path} (exists={os.path.exists(self.temp_resume_path) if self.temp_resume_path else False}) | dry_run={dry_run}")

            if not self.temp_resume_path:
                logger.debug("No temp resume path set, skipping file input handling")
                return True, "No enhanced resume to upload"
            
            if not os.path.exists(self.temp_resume_path):
                logger.warning(f"Temp resume file not found: {self.temp_resume_path}")
                return False, "Enhanced resume file not found"
            
            # Find file input elements (resume upload fields)
            file_input_selectors = [
                "input[type='file']",
                "input[accept*='.pdf']",
                "input[accept*='application/pdf']",
                ".jobs-document-upload__container input[type='file']",
                "[data-test-form-builder-document-form-component] input[type='file']",
                ".js-jobs-document-upload__container input[type='file']",
            ]
            
            file_inputs = []
            for selector in file_input_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    file_inputs.extend(elements)
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            # Also try XPath for more complex selectors
            try:
                xpath_inputs = self.driver.find_elements(
                    By.XPATH, 
                    "//input[@type='file' and (contains(@accept, 'pdf') or contains(@accept, 'doc'))]"
                )
                file_inputs.extend(xpath_inputs)
            except:
                pass
            
            # Remove duplicates
            seen_ids = set()
            unique_inputs = []
            for inp in file_inputs:
                try:
                    inp_id = inp.get_attribute("id") or id(inp)
                    if inp_id not in seen_ids:
                        seen_ids.add(inp_id)
                        unique_inputs.append(inp)
                except:
                    unique_inputs.append(inp)
            
            file_inputs = unique_inputs
            
            if not file_inputs:
                logger.info("No file input fields found on current page")
                return True, "No file inputs found"
            
            logger.info(f"Found {len(file_inputs)} file input field(s)")
            
            uploaded_count = 0
            for idx, file_input in enumerate(file_inputs):
                try:
                    # Check if this is a resume/document upload field
                    input_name = file_input.get_attribute("name") or ""
                    input_id = file_input.get_attribute("id") or ""
                    accept_attr = file_input.get_attribute("accept") or ""
                    
                    # Look for parent container to identify if it's a resume field
                    is_resume_field = False
                    try:
                        parent = file_input.find_element(
                            By.XPATH, 
                            "./ancestor::div[contains(@class, 'document') or contains(@class, 'resume') or contains(@class, 'upload')][1]"
                        )
                        parent_classes = parent.get_attribute("class") or ""
                        parent_text = parent.text.lower() if parent.text else ""
                        
                        if any(kw in parent_text or kw in parent_classes.lower() 
                               for kw in ["resume", "cv", "document", "upload"]):
                            is_resume_field = True
                    except:
                        # If we can't find parent context, check accept attribute
                        if "pdf" in accept_attr.lower() or "doc" in accept_attr.lower():
                            is_resume_field = True
                    
                    # For LinkedIn Easy Apply, most file inputs are resume uploads
                    if not is_resume_field:
                        is_resume_field = True  # Default to treating as resume field
                    
                    if is_resume_field:
                        logger.info(f"📄 Preparing to upload enhanced resume to file input {idx+1} (id={input_id}, accept={accept_attr})")

                        # Make sure input is interactable (may be hidden)
                        try:
                            # Sometimes file inputs are hidden, use JS to make visible
                            self.driver.execute_script(
                                "arguments[0].style.display = 'block'; "
                                "arguments[0].style.visibility = 'visible'; "
                                "arguments[0].style.opacity = '1';",
                                file_input
                            )
                            time.sleep(0.1)
                        except Exception as js_exc:
                            logger.debug(f"JS show input failed: {js_exc}")

                        # Dry-run: only log what would be sent
                        if dry_run:
                            logger.info(f"DRY-RUN: would send file '{self.temp_resume_path}' to input {idx+1} (id={input_id})")
                            # Do not perform actual upload in dry-run mode
                            uploaded_count += 0
                        else:
                            try:
                                # Send the file path to the input
                                file_input.send_keys(self.temp_resume_path)
                                time.sleep(1)  # Wait for upload to process
                                logger.info(f"✓ Enhanced resume uploaded to file input {idx+1}")
                                uploaded_count += 1
                            except Exception as upload_err:
                                logger.error(f"Error during file send_keys for input {idx+1}: {upload_err}")
                    else:
                        logger.debug(f"Skipping non-resume file input {idx+1}")
                        
                except Exception as e:
                    logger.error(f"Error uploading to file input {idx+1}: {e}")
                    continue
            
            if uploaded_count > 0:
                logger.info(f"✅ Successfully uploaded enhanced resume to {uploaded_count} field(s)")
                return True, f"Resume uploaded to {uploaded_count} field(s)"
            else:
                return True, "No resume upload fields processed"
            
        except Exception as e:
            logger.error(f"Error in _fill_file_inputs: {e}")
            return False, f"File upload error: {str(e)}"
    
    def _get_gpt_answers_for_boxes(self, questions: List[str], field_types: List[str] = None) -> List[str]:
        """Get GPT answers for text box questions with field type awareness - OPTIMIZED"""
        if field_types is None:
            field_types = ["text"] * len(questions)
        
        import json as _json
        resume_json_str = _json.dumps(self.resume_json) if self.resume_json else (self.resume if isinstance(self.resume, str) else _json.dumps(self.resume))
        prompt = f"""I have attached my full resume JSON below (for maximum context):
```
{resume_json_str}
```
"""
        # Add job description if available
        if self.job_description:
            prompt += f"""

Job Description:
```
{self.job_description}
```
"""
        
        prompt += """
Read the resume carefully and understand the information in it."""
        
        if self.job_description:
            prompt += " Also consider the job requirements when answering."
        
        prompt += """
You are applying for a job by answering the below questions on behalf of the candidate in LinkedIn website.

        Now, answer the following questions step by step:
        """
        
        for i, (q, ftype) in enumerate(zip(questions, field_types), 1):
            prompt += f"\\nQuestion {i} ({ftype}): {q}"
        
        prompt += """

        Answer these questions using information from the resume. If not directly answered in the resume, 
        estimate creatively based on available information. Never say "not specified" or "don't know".
        
        CRITICAL FORMATTING RULES FOR EACH FIELD TYPE:
        
        FOR NUMERIC FIELDS:
        - Respond with ONLY a numeric value (e.g., "2.5", "3", "1.5")
        - Do NOT include units, explanations, or text
        - For years of experience, convert text ranges to decimals (e.g., "2-3 years" → "2.5")
        - For notice periods, use: "0.0" (immediate), "0.5" (2 weeks), "1.0" (1 month), "2.0" (2 months), "3.0" (3 months)
        
        FOR LINKEDIN_URL FIELDS:
        - Provide a FULL LinkedIn profile URL
        - Format MUST be: https://linkedin.com/in/yourprofile (all lowercase, use 'in' not 'pub')
        - Extract the name from resume and create realistic profile URL
        - NEVER respond with "no", "none", "not available", or any negative answer
        - MUST be a complete, valid URL starting with https://
        
        FOR PHONE FIELDS:
        - Provide a valid phone number format with country code
        - Format: +1-XXX-XXX-XXXX or similar valid format
        - Extract from resume if available
        
        FOR EMAIL FIELDS:
        - Provide a valid email address from the resume, or create a plausible one
        - Must contain @ symbol and valid domain
        
        FOR TEXT FIELDS:
        - Provide clear, concise answers
        - Keep answers relevant to the question
        
        IMPORTANT: If previous attempts had errors, adjust your answers to fix them.
        
        Provide answers in valid Python Dictionary format with question number as key and answer as value.
        Example: {"1": "2.5", "2": "https://linkedin.com/in/john-doe", "3": "Software Engineer"}
        """
        
        answer_text = self.ask_gpt(prompt, max_tokens=4096)
        if not answer_text:
            return []
        
        # Parse GPT response to extract answers
        parsed = self._parse_gpt_response(answer_text)
        
        # Validate LinkedIn URLs
        validated = []
        for i, answer in enumerate(parsed):
            if i < len(field_types) and field_types[i] == "linkedin_url":
                answer = answer.strip()
                # If answer doesn't look like a URL, generate one
                if not answer.lower().startswith("http"):
                    # Try to extract name from resume or create one
                    name_match = re.search(r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b', self.resume)
                    if name_match:
                        first, last = name_match.groups()
                        answer = f"https://linkedin.com/in/{first.lower()}-{last.lower()}"
                    else:
                        answer = "https://linkedin.com/in/candidate"
                validated.append(answer)
            else:
                validated.append(answer)
        
        return validated
    
    def _get_gpt_answers_for_radios(self, questions: List[str]) -> List[str]:
        """Get GPT answers for radio button questions"""
        prompt = f"""I have attached my resume below: ```"{self.resume}"```."""
        
        # Add job description if available
        if self.job_description:
            prompt += f"""
            
Job Description:
```
{self.job_description}
```
"""
        
        prompt += """
        
        Now, answer the following questions by selecting the appropriate radio button option:
        """
        
        for i, q in enumerate(questions, 1):
            prompt += f"Question {i}: {q}\n"
        
        prompt += """
        Use information from the resume to answer."""
        
        if self.job_description:
            prompt += " Also consider the job requirements when answering."
        
        prompt += """ If not directly addressed, use creativity to provide 
        reasonable answers. Never say "not specified" or "don't know". Select only one option per question.
        Provide answers in valid Python Dictionary format with question number as key and selected option as value.
        """
        
        answer_text = self.ask_gpt(prompt)
        if not answer_text:
            return []
        
        return self._parse_gpt_response(answer_text)
    
    def _get_gpt_answers_for_dropdowns(self, questions: List[str]) -> List[str]:
        """Get GPT answers for dropdown questions"""
        # Similar to radio buttons
        return self._get_gpt_answers_for_radios(questions)
    
    def _get_gpt_answers_for_multiline(self, questions: List[str]) -> List[str]:
        """Get GPT answers for multiline text fields (summaries, cover letters, etc.)"""
        prompt = f"""I have attached my resume below:
```
{self.resume}
```
"""
        
        # Add job description if available
        if self.job_description:
            prompt += f"""
Job Description:
```
{self.job_description}
```
"""
        
        prompt += """
You are applying for a job on LinkedIn. Answer the following questions with detailed, professional responses.
For cover letters and summaries, write compelling, well-formatted answers that highlight relevant experience.
"""

        if self.job_description:
            prompt += "Reference specific requirements from the job description when answering.\n"
        
        prompt += """
Questions to answer:
"""
        
        for i, q in enumerate(questions, 1):
            if "cover" in q.lower():
                prompt += f"\nQuestion {i}: {q}\nWrite a compelling cover letter that explains why you're interested in the position and how your experience makes you a good fit."
            elif "summary" in q.lower():
                prompt += f"\nQuestion {i}: {q}\nWrite a professional summary highlighting your key skills and achievements from the resume."
            else:
                prompt += f"\nQuestion {i}: {q}\nAnswer based on your resume and experience."
        
        prompt += """

Provide answers in valid Python Dictionary format with question number as key and answer as value.
Example: {"1": "Dear Hiring Manager...", "2": "I am a professional with..."}

Make responses detailed, professional, and engaging. For cover letters, keep them to 3-4 sentences. 
For summaries, keep them to 2-3 sentences.
"""
        
        answer_text = self.ask_gpt(prompt)
        if not answer_text:
            return []
        
        return self._parse_gpt_response(answer_text)
    
    def _get_gpt_answers_for_locations(self, questions: List[str]) -> List[str]:
        """Get GPT answers for location/typeahead fields"""
        import json as _json
        resume_json_str = _json.dumps(self.resume_json) if self.resume_json else (self.resume if isinstance(self.resume, str) else _json.dumps(self.resume))
        prompt = f"""I have attached my full resume JSON below (for maximum context):\n```
{resume_json_str}
```

Based on this resume, answer the following location/geography related questions.
Provide specific cities, regions, or countries as appropriate.

Questions:
"""
        
        for i, q in enumerate(questions, 1):
            prompt += f"Question {i}: {q}\n"
        
        prompt += """
For each question, provide the most relevant location information from the resume or a reasonable location 
that would fit the candidate's background. Keep answers concise (usually just a city or region).

Provide answers in valid Python Dictionary format with question number as key and location as value.
Example: {"1": "San Francisco", "2": "Remote"}
"""
        
        answer_text = self.ask_gpt(prompt)
        if not answer_text:
            return []
        
        return self._parse_gpt_response(answer_text)
    
    def _parse_gpt_response(self, response: str) -> List[str]:
        """Parse GPT response to extract answer values"""
        try:
            if not response or not isinstance(response, str):
                logger.warning(f"Invalid response type: {type(response)}")
                return []
            
            # Try to find JSON block in markdown code
            json_match = re.search(r'```(?:json)?\s*(\{.+?\})\s*```', response, re.DOTALL)
            if json_match:
                cleaned = json_match.group(1).strip()
            else:
                # Try to find JSON object directly
                json_match = re.search(r'(\{.+\})', response, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(1).strip()
                else:
                    cleaned = response.strip()
            
            # Clean up the JSON string: remove line breaks but preserve spacing inside quotes
            cleaned = cleaned.strip()

            # Protect string literals first: replace them with placeholders so comment removal
            # doesn't accidentally remove content inside strings (e.g., URLs with //)
            string_pattern = re.compile(r'("(?:(?:\\.)|[^"\\])*")|(\'(?:(?:\\.)|[^\\\'])*\')')
            literals: List[str] = []
            def _literal_repl(m):
                literals.append(m.group(0))
                return f'__STR_{len(literals)-1}__'

            cleaned_placeholders = string_pattern.sub(_literal_repl, cleaned)

            # First pass: handle inline comment patterns that appear before the next JSON key
            # e.g. { "1": "val", # comment "2": "val2" }
            try:
                cleaned_placeholders = re.sub(r'#\s*[^\r\n]*?(?=(\s*"[^"]+"\s*:))', '', cleaned_placeholders)
                cleaned_placeholders = re.sub(r'//\s*[^\r\n]*?(?=(\s*"[^"]+"\s*:))', '', cleaned_placeholders)
                # Remove C-style block comments safely on placeholder string
                cleaned_placeholders = re.sub(r'/\*.*?\*/', '', cleaned_placeholders, flags=re.DOTALL)
            except Exception:
                pass

            # Helper: remove comments (#, //, /* */) that are outside of string literals
            def _remove_comments(s: str) -> str:
                out_chars = []
                in_single = False
                in_double = False
                i = 0
                while i < len(s):
                    c = s[i]
                    # Toggle quote states
                    if c == "'" and not in_double:
                        in_single = not in_single
                        out_chars.append(c)
                        i += 1
                        continue
                    if c == '"' and not in_single:
                        in_double = not in_double
                        out_chars.append(c)
                        i += 1
                        continue

                    # If not in a string, strip comments
                    if not in_single and not in_double:
                        # Hash comments (# ...) skip to EOL
                        if c == '#':
                            while i < len(s) and s[i] not in '\r\n':
                                i += 1
                            continue
                        # C++ style // comment
                        if c == '/' and i + 1 < len(s) and s[i+1] == '/':
                            i += 2
                            while i < len(s) and s[i] not in '\r\n':
                                i += 1
                            continue
                        # C style /* */ comment
                        if c == '/' and i + 1 < len(s) and s[i+1] == '*':
                            i += 2
                            while i + 1 < len(s) and not (s[i] == '*' and s[i+1] == '/'):
                                i += 1
                            i += 2
                            continue

                    out_chars.append(c)
                    i += 1

                return ''.join(out_chars)

            cleaned = _remove_comments(cleaned_placeholders)

            # Restore string literals into cleaned text
            for i, lit in enumerate(literals):
                cleaned = cleaned.replace(f'__STR_{i}__', lit)

            # Remove code fence markers if present
            cleaned = re.sub(r'```\w*', '', cleaned)

            # Normalize whitespace but keep JSON structure
            cleaned = re.sub(r'\s+', ' ', cleaned)

            # Remove trailing commas before object/array closers: { ... , }  or [ ... , ]
            cleaned = re.sub(r',\s*([\]}])', r'\1', cleaned)

            # Try to parse with multiple strategies
            data = None
            parse_errors = []
            try:
                data = json.loads(cleaned)
            except Exception as e_json:
                parse_errors.append(('json', str(e_json)))
                try:
                    # demjson3 is lenient and can handle some non-standard JSON
                    data = demjson3.decode(cleaned)
                except Exception as e_dem:
                    parse_errors.append(('demjson3', str(e_dem)))
                    try:
                        # As a last resort, try Python literal eval (accepts single quotes)
                        import ast
                        data = ast.literal_eval(cleaned)
                    except Exception as e_ast:
                        parse_errors.append(('ast', str(e_ast)))
                        logger.error(f"All JSON parsing methods failed for: {cleaned[:200]}")
                        logger.debug(f"Parse errors: {parse_errors}")

                        # Fallback: try to extract simple "key": "value" pairs with regex (handles many malformed GPT replies)
                        try:
                            kv_pairs = re.findall(r'"(\d+)"\s*:\s*"(.*?)"', cleaned)
                            if kv_pairs:
                                # Sort by numeric key and return values
                                kv_pairs_sorted = sorted(kv_pairs, key=lambda x: int(x[0]) if x[0].isdigit() else x[0])
                                return [v for _, v in kv_pairs_sorted]
                        except Exception:
                            pass

                        return []
            
            # Extract values
            if isinstance(data, list):
                answers = []
                for item in data:
                    if isinstance(item, dict):
                        answers.extend(list(item.values()))
                    else:
                        answers.append(item)
            elif isinstance(data, dict):
                answers = list(data.values())
            else:
                answers = [str(data)]
            
            # Process answers - preserve numeric types but convert to strings for form entry
            processed = []
            for a in answers:
                if a is None or (isinstance(a, str) and not a.strip()):
                    continue
                
                # If it's a number (int or float), convert to string representation
                if isinstance(a, (int, float)):
                    processed.append(str(a))
                else:
                    # For strings, try to extract numeric values if it looks like a decimal number
                    a_str = str(a).strip()
                    # Check if this is a numeric string (includes decimals)
                    if re.match(r'^-?\d+\.?\d*$', a_str):
                        processed.append(a_str)
                    else:
                        processed.append(a_str)
            
            answers = processed
            
            return answers
            
        except Exception as e:
            logger.error(f"Error parsing GPT response: {e}")
            logger.debug(f"Response was: {response[:200]}")
            return []
    
    def submit_application(self) -> Tuple[bool, str]:
        """
        Navigate through form pages and submit - FIXED VERSION
        Only fills form once per page, properly detects when done
        """
        try:
            max_pages = 10
            page_count = 0
            pages_filled = []
            
            while page_count < max_pages:
                page_count += 1
                logger.info(f"--- Processing page {page_count} ---")
                
                # Wait for page to load (OPTIMIZED: reduced from 2s to 0.5s)
                time.sleep(0.5)
                
                # Check if we're on review/confirmation page
                try:
                    confirmation = self.driver.find_element(
                        By.XPATH, "//*[contains(text(), 'Review your application') or contains(text(), 'Review and submit')]"
                    )
                    logger.info("On review/confirmation page")
                except:
                    pass
                
                # Fill current page
                fill_success, fill_msg = self.fill_form_with_ai()
                pages_filled.append({
                    'page': page_count,
                    'success': fill_success,
                    'message': fill_msg
                })
                
                time.sleep(0.1)  # OPTIMIZED: reduced from 0.3s
                
                # Try to proceed to next step
                clicked_button = None
                
                # Special case: On first page, check for Submit button first if it's a simple form
                if page_count == 1:
                    try:
                        # Quick check for Submit button on first page
                        submit_selectors_quick = [
                            "button[aria-label='Submit application']",
                            "button[aria-label*='Submit']",
                            "//button[contains(text(), 'Submit application')]",
                            "//button[contains(text(), 'Submit') and not(contains(text(), 'question'))]",
                        ]

                        submit_btn = None
                        for selector in submit_selectors_quick:
                            try:
                                if selector.startswith("//"):
                                    submit_btn = WebDriverWait(self.driver, 1).until(
                                        EC.element_to_be_clickable((By.XPATH, selector))
                                    )
                                else:
                                    submit_btn = WebDriverWait(self.driver, 1).until(
                                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                    )
                                break
                            except TimeoutException:
                                continue

                        if submit_btn and not self._safe_click_element(submit_btn, "Submit (first page)"):
                            logger.warning("Submit button click blocked on first page")
                            raise TimeoutException("Submit button not clickable")
                        elif submit_btn:
                            logger.info("✓ Clicked Submit button (found on first page)")
                            time.sleep(0.5)  # OPTIMIZED: reduced from 3s

                            # Verify submission success
                            try:
                                success_indicator = self.driver.find_element(
                                    By.XPATH, "//*[contains(text(), 'Application sent') or contains(text(), 'Application submitted') or contains(text(), 'successfully applied')]"
                                )
                                logger.info("✓✓ Application submitted successfully! (single page form)")
                                return True, f"Application submitted (single page)"
                            except:
                                logger.info("Submit clicked on first page, verifying...")
                                time.sleep(2)
                                return True, f"Application submitted (single page)"
                    except TimeoutException:
                        pass
                
                # 1. Try Next/Continue button (first priority) - multiple selectors
                try:
                    next_selectors = [
                        "button[aria-label='Continue to next step']",
                        "button[aria-label*='Next']",
                        "button[aria-label='Continue']",
                        "//button[contains(text(), 'Next')]",
                        "//button[contains(text(), 'Continue')]",
                        "button[data-control-name='continue_unify']",
                    ]

                    next_btn = None
                    for selector in next_selectors:
                        try:
                            if selector.startswith("//"):
                                next_btn = WebDriverWait(self.driver, 1).until(
                                    EC.element_to_be_clickable((By.XPATH, selector))
                                )
                            else:
                                next_btn = WebDriverWait(self.driver, 1).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                )
                            break
                        except TimeoutException:
                            continue

                    if next_btn and not self._safe_click_element(next_btn, "Next"):
                        logger.warning("Next button click blocked; checking other buttons")
                    elif next_btn:
                        logger.info("✓ Clicked Next button")
                        clicked_button = "next"
                        time.sleep(2)
                        continue
                except TimeoutException:
                    pass
                
                # 2. Try Review button (second priority) - multiple selectors
                try:
                    review_selectors = [
                        "button[aria-label='Review your application']",
                        "button[aria-label*='Review']",
                        "//button[contains(text(), 'Review')]",
                        "button[data-control-name='review_unify']",
                    ]

                    review_btn = None
                    for selector in review_selectors:
                        try:
                            if selector.startswith("//"):
                                review_btn = WebDriverWait(self.driver, 1).until(
                                    EC.element_to_be_clickable((By.XPATH, selector))
                                )
                            else:
                                review_btn = WebDriverWait(self.driver, 1).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                )
                            break
                        except TimeoutException:
                            continue

                    if review_btn and not self._safe_click_element(review_btn, "Review"):
                        logger.warning("Review button click blocked; will re-evaluate form state")
                    elif review_btn:
                        logger.info("✓ Clicked Review button")
                        clicked_button = "review"
                        time.sleep(0.3)  # OPTIMIZED: reduced from 2s
                        continue
                except TimeoutException:
                    pass
                
                # 3. Try Submit button (last priority) - multiple selectors
                try:
                    # Try aria-label selectors first
                    submit_selectors = [
                        "button[aria-label='Submit application']",
                        "button[aria-label*='Submit']",
                        "button[aria-label='Submit your application']",
                        "button[aria-label='Send application']",
                        # Fallback to text-based selectors
                        "button[data-control-name='submit_unify']",
                        "//button[contains(text(), 'Submit application')]",
                        "//button[contains(text(), 'Submit') and not(contains(text(), 'question'))]",
                        "//button[contains(@class, 'submit')]",
                    ]

                    submit_btn = None
                    for selector in submit_selectors:
                        try:
                            if selector.startswith("//"):
                                submit_btn = WebDriverWait(self.driver, 1).until(
                                    EC.element_to_be_clickable((By.XPATH, selector))
                                )
                            else:
                                submit_btn = WebDriverWait(self.driver, 1).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                )
                            break  # Found one, stop looking
                        except TimeoutException:
                            continue

                    if submit_btn and not self._safe_click_element(submit_btn, "Submit"):
                        logger.warning("Submit button click blocked; will try other navigation buttons")
                        raise TimeoutException("Submit button not clickable")
                    elif submit_btn:
                        logger.info("✓ Clicked Submit button")
                        time.sleep(0.5)  # OPTIMIZED: reduced from 3s

                        # Verify submission success
                        try:
                            success_indicator = self.driver.find_element(
                                By.XPATH, "//*[contains(text(), 'Application sent') or contains(text(), 'Application submitted') or contains(text(), 'successfully applied')]"
                            )
                            logger.info("✓✓ Application submitted successfully!")
                            return True, f"Application submitted (filled {page_count} pages)"
                        except:
                            logger.info("Submit clicked, verifying...")
                            time.sleep(0.3)  # OPTIMIZED: reduced from 2s
                            return True, f"Application submitted (filled {page_count} pages)"
                except TimeoutException:
                    pass
                
                # No buttons found - might be done or stuck
                if clicked_button is None:
                    logger.warning(f"No navigation buttons found on page {page_count}")

                    # First, check if application was already submitted successfully
                    try:
                        success_indicators = self.driver.find_elements(
                            By.XPATH, "//*[contains(text(), 'Application sent') or contains(text(), 'Application submitted') or contains(text(), 'successfully applied') or contains(text(), 'Application Submitted')]"
                        )
                        if success_indicators:
                            logger.info("✓✓ Application submitted successfully! (detected by success text)")
                            return True, f"Application submitted (filled {page_count} pages)"
                    except Exception as e:
                        logger.debug(f"Error checking for success indicators: {e}")

                    # Check if submit failed due to validation errors
                    try:
                        errors = self.driver.find_elements(
                            By.CSS_SELECTOR, ".artdeco-inline-feedback--error"
                        )
                        if errors:
                            error_texts = [e.text for e in errors if e.text.strip()]
                            logger.error(f"Validation errors present: {error_texts}")
                            return False, f"Form validation failed: {error_texts[0] if error_texts else 'Unknown error'}"
                    except:
                        pass

                    # Try alternative button selectors that might work with newer LinkedIn UI
                    try:
                        # Look for any button with submit-related text
                        alt_buttons = self.driver.find_elements(
                            By.XPATH, "//button[contains(text(), 'Submit') or contains(text(), 'Apply') or contains(text(), 'Send')]"
                        )
                        for btn in alt_buttons:
                            if btn.is_displayed() and btn.is_enabled():
                                logger.info(f"Found alternative button with text: {btn.text}")
                                if self._safe_click_element(btn, f"Alternative-{btn.text}"):
                                    time.sleep(3)
                                    # Check for success after clicking
                                    try:
                                        success_check = self.driver.find_element(
                                            By.XPATH, "//*[contains(text(), 'Application sent') or contains(text(), 'Application submitted')]"
                                        )
                                        logger.info("✓✓ Application submitted successfully! (via alternative button)")
                                        return True, f"Application submitted (filled {page_count} pages)"
                                    except:
                                        logger.info("Alternative button clicked, continuing...")
                                        clicked_button = "alternative"
                                        time.sleep(2)
                                        continue
                    except Exception as e:
                        logger.debug(f"Error trying alternative buttons: {e}")

                    # Check if we're on a success/confirmation page
                    try:
                        confirmation_elements = self.driver.find_elements(
                            By.XPATH, "//*[contains(text(), 'review') or contains(text(), 'submitted') or contains(text(), 'complete')]"
                        )
                        if confirmation_elements:
                            logger.info("On confirmation/review page - application may be complete")
                            # Try one more time to find any clickable button
                            all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                            for btn in all_buttons:
                                if btn.is_displayed() and btn.is_enabled() and ('submit' in btn.text.lower() or 'apply' in btn.text.lower() or 'send' in btn.text.lower()):
                                    logger.info(f"Found button with submit-like text: {btn.text}")
                                    if self._safe_click_element(btn, f"Final-{btn.text}"):
                                        time.sleep(3)
                                        return True, f"Application submitted (filled {page_count} pages)"
                    except Exception as e:
                        logger.debug(f"Error in final button check: {e}")

                    # If we get here, assume we're done but it might be incomplete
                    return False, f"No more buttons found after {page_count} pages (might be incomplete)"
            
            return False, f"Reached max pages ({max_pages}) without submitting"
            
        except Exception as e:
            logger.error(f"Error in submit_application: {e}", exc_info=True)
            return False, f"Submission error: {str(e)}"
    
    def _build_result(
        self,
        *,
        success: bool,
        job_url: str,
        message: str,
        stage: Optional[str] = None,
        extra_details: Optional[Dict[str, Any]] = None,
    ) -> ApplicationResult:
        details = {"session": self.lifecycle.session_metadata()}
        if extra_details:
            details.update(extra_details)
        return ApplicationResult(
            success=success,
            job_url=job_url,
            message=message,
            error_stage=stage,
            details=details,
        )

    def apply_to_job(
        self,
        job_url: str,
        cookies: List[dict],
        headless: bool = True,
        session_id: Optional[str] = None,
        job_description: Optional[str] = None
    ) -> ApplicationResult:
        try:
            # Store job description for use in GPT prompts
            self.job_description = job_description
            
            self.lifecycle.start(self.session_context)
            if not self.lifecycle.record_apply_attempt():
                return self._build_result(
                    success=False,
                    job_url=job_url,
                    message="Session apply cap reached",
                    stage="session_cap",
                    extra_details={"session_tainted": False},
                )

            if session_id:
                # Reuse existing Selenium session managed elsewhere
                try:
                    from application.services.linkedin_session_manager import get_session_manager
                    session_manager = get_session_manager()
                    session = session_manager.get_session(session_id)
                    if not session or not session.driver:
                        return self._build_result(
                            success=False,
                            job_url=job_url,
                            message="LinkedIn session not found or driver unavailable",
                            stage="session",
                            extra_details={"session_tainted": True},
                        )
                    self.driver = session.driver
                    self.owns_driver = False
                    logger.info(f"Reusing shared Selenium session: {session_id}")
                except Exception as e:
                    logger.error(f"Failed to attach to existing session {session_id}: {e}")
                    return self._build_result(
                        success=False,
                        job_url=job_url,
                        message="Failed to attach to existing LinkedIn session",
                        stage="session",
                        extra_details={"session_tainted": True},
                    )
            else:
                # Create a dedicated driver
                if not self.setup_driver(headless=headless, session_context=self.session_context):
                    return self._build_result(
                        success=False,
                        job_url=job_url,
                        message="Failed to setup browser driver",
                        stage="driver_setup",
                    )
                self.owns_driver = True
            
            if not self._is_driver_alive():
                logger.error("Driver initialized but not functional")
                return self._build_result(
                    success=False,
                    job_url=job_url,
                    message="Driver crashed after initialization",
                    stage="driver_setup",
                )
            
            # Verify login (credentials-based session)
            if not self.verify_login():
                self._mark_session_tainted("login_verification_failed", critical=True)
                return self._build_result(
                    success=False,
                    job_url=job_url,
                    message="Failed to verify LinkedIn login",
                    stage="login_verification",
                    extra_details={"session_tainted": True},
                )

            logger.info("LinkedIn login verified")
            
            # Update status: Navigation
            if self.status_callback:
                try:
                    self.status_callback("navigation", {"job_url": job_url})
                except Exception as e:
                    logger.warning(f"Status callback failed (navigation): {e}")
            
            nav_ok, nav_reason = self.navigate_to_job(job_url)
            if not nav_ok:
                return self._build_result(
                    success=False,
                    job_url=job_url,
                    message="Navigation blocked (session tainted)",
                    stage="navigation",
                    extra_details={"reason": nav_reason, "session_tainted": True},
                )

            # Update status: Button Click
            if self.status_callback:
                try:
                    self.status_callback("button_click", {"navigation_success": True})
                except Exception as e:
                    logger.warning(f"Status callback failed (button_click): {e}")
            
            click_ok, click_reason = self.click_easy_apply()
            if not click_ok:
                # Check if job is expired/unavailable
                if click_reason and "job_expired" in click_reason:
                    return self._build_result(
                        success=False,
                        job_url=job_url,
                        message=f"Job expired or unavailable: {click_reason}",
                        stage="easy_apply_button",
                        extra_details={"reason": click_reason, "session_tainted": False},
                    )
                
                return self._build_result(
                    success=False,
                    job_url=job_url,
                    message="Easy Apply unavailable (session tainted)",
                    stage="easy_apply_button",
                    extra_details={"reason": click_reason, "session_tainted": True},
                )
            
            # Handle any popup that appears after clicking Easy Apply
            self.handle_easy_apply_popup()
            
            # Update status: Form Filling
            if self.status_callback:
                try:
                    self.status_callback("form_filling", {"button_clicked": True})
                except Exception as e:
                    logger.warning(f"Status callback failed (form_filling): {e}")
            
            success, msg = self.submit_application()
            
            fresh_cookies = self.get_fresh_cookies()
            session_details = {"fresh_cookies": fresh_cookies, "session_tainted": self.lifecycle.tainted}
            
            # Update status: Submission or Completed
            if self.status_callback:
                try:
                    if success:
                        self.status_callback("completed", {"submission_success": True})
                    else:
                        self.status_callback("submission", {"submission_success": False, "error": msg})
                except Exception as e:
                    logger.warning(f"Status callback failed (submission/completed): {e}")
            
            if success:
                return self._build_result(
                    success=True,
                    job_url=job_url,
                    message="Application submitted successfully",
                    extra_details=session_details,
                )
            else:
                return self._build_result(
                    success=False,
                    job_url=job_url,
                    message=msg,
                    stage="submission",
                    extra_details=session_details,
                )            
        except Exception as e:
            logger.error(f"Error applying to job: {e}")
            self._mark_session_tainted("runtime_exception", critical=True)
            return self._build_result(
                success=False,
                job_url=job_url,
                message=f"Application error: {str(e)}",
                stage="unknown",
                extra_details={"session_tainted": True},
            )
        finally:
            self.cleanup()    
    def cleanup(self):
        """Clean up driver resources"""
        try:
            # Only close the driver if we created it; shared session drivers are managed elsewhere
            if self.driver and self.owns_driver:
                logger.info("Cleaning up driver...")
                self.driver.quit()
                time.sleep(0.2)  # Quick cleanup wait
                self.driver = None
                logger.info("✓ Driver cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            self.driver = None  # Ensure it's set to None even on error
    
    def _is_driver_alive(self) -> bool:
        """Check if driver is still functional"""
        if not self.driver:
            return False
        try:
            _ = self.driver.current_url
            return True
        except:
            return False
    def get_fresh_cookies(self) -> List[dict]:
        if not self.driver:
            return []
        
        try:
            raw_cookies = self.driver.get_cookies()
            min_expiry = int(time.time()) + 172800
            
            whitelist = ["name", "value", "domain", "path", "expiry", "secure", "httpOnly"]
            normalized = []
            
            for cookie in raw_cookies:
                normalized_cookie = {}
                for field in whitelist:
                    if field == "domain":
                        normalized_cookie["domain"] = ".linkedin.com"
                    elif field == "expiry":
                        expiry = cookie.get("expiry")
                        normalized_cookie["expiry"] = expiry if expiry and expiry > min_expiry else min_expiry
                    else:
                        if field in cookie:
                            normalized_cookie[field] = cookie[field]
                
                if normalized_cookie.get("name") and normalized_cookie.get("value"):
                    normalized.append(normalized_cookie)
            
            return normalized
        except Exception as e:
            logger.error(f"Error extracting cookies: {e}")
            return []