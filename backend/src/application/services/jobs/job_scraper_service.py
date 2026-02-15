"""
Job Scraper Service
Wraps LinkedIn job scraping functionality into reusable service
"""
import json
import time
import re
import random
import asyncio
from typing import List, Dict, Tuple, Optional
from urllib.parse import quote
from datetime import datetime
from uuid import UUID, uuid4
import socket
import threading

from loguru import logger

from .job_parser import (
    extract_job_id,
    parse_experience,
    parse_salary,
    parse_work_type,
    parse_location
)

# Selenium imports (optional, graceful fallback)
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not available - job scraping will be simulated")


class JobScraperService:
    """
    LinkedIn job scraping service
    
    Scrapes jobs based on user preferences, parses structured data,
    and returns fresh cookies for session persistence.
    """
    
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    def __init__(self):
        self.driver = None
    
    def _setup_driver(self, timeout: int = 60) -> Optional["webdriver.Chrome"]:
        """Initialize Chrome driver with stealth settings and connection timeout handling"""
        if not SELENIUM_AVAILABLE:
            return None
        
        try:
            logger.info(f"Setting up Chrome driver with {timeout}s timeout...")
            
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--no-default-browser-check")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument(f"user-agent={self.USER_AGENT}")
            # chrome_options.add_argument("--headless=new")  # DISABLED for debugging
            
            # Set implicit wait timeout
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(timeout)
            driver.set_script_timeout(timeout)
            driver.implicitly_wait(10)
            
            # Mask webdriver detection
            try:
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": """
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                    """
                })
            except Exception as e:
                logger.warning(f"Could not mask webdriver detection: {e}")
            
            driver.maximize_window()
            logger.info("✓ Chrome driver initialized successfully")
            return driver
            
        except WebDriverException as e:
            logger.error(f"WebDriver initialization failed (timeout/connection): {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during driver setup: {e}")
            return None
    
    def _verify_login(self, driver) -> bool:
        """Verify successful login"""
        time.sleep(3)
        current_url = driver.current_url
        
        logger.info(f"Current URL after cookie injection: {current_url}")
        logger.info(f"Page title: {driver.title}")
        
        # Check if we're on login or checkpoint page
        if "login" in current_url or "checkpoint" in current_url or "uas/login" in current_url:
            logger.error(f"❌ Still on login page: {current_url}")
            logger.info("This means cookies are invalid, expired, or LinkedIn detected automation")
            return False
        
        # Check if we're on feed (best case)
        if "linkedin.com/feed" in current_url:
            logger.info("✓ Successfully on feed page")
            return True
        
        # Try to find navigation bar (indicates logged in)
        try:
            driver.find_element(By.ID, "global-nav")
            logger.info("✓ Found global-nav element (logged in)")
            return True
        except:
            logger.debug("global-nav element not found")
        
        # Try alternative logged-in indicators
        try:
            driver.find_element(By.CSS_SELECTOR, "[data-control-name='identity_welcome_message']")
            logger.info("✓ Found identity welcome message (logged in)")
            return True
        except:
            logger.debug("identity_welcome_message not found")
        
        # Check page source for login indicators
        page_source = driver.page_source.lower()
        if "sign in" in page_source or "join now" in page_source:
            logger.error("❌ Page contains 'Sign in' or 'Join now' - not logged in")
            return False
        
        logger.warning("⚠️ Login status unclear, assuming logged in")
        return True
    
    def _extract_fresh_cookies(self, driver) -> List[dict]:
        """Extract and normalize current browser cookies"""
        raw_cookies = driver.get_cookies()
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
    
    def _search_jobs(self, driver, job_title: str, location: str, easy_apply: bool = True, experience_level: str = None, work_type: str = None, current_job_id: str = None, timeout: int = 60, start: int = 0) -> bool:
        """Navigate to LinkedIn jobs search with filters in URL (supports pagination via start parameter)"""
        try:
            driver.set_page_load_timeout(timeout)
            
            # Location to geoId mapping for common regions
            location_to_geoid = {
                "lahore": "104112529",
                "lahore, pakistan": "104112529",
                "karachi": "104112529",
                "karachi, pakistan": "104112529",
                "islamabad": "104112529",
                "islamabad, pakistan": "104112529",
                "pakistan": "104112529",
                "united states": "103663517",
                "us": "103663517",
                "canada": "102713980",
                "united kingdom": "101165590",
                "uk": "101165590",
                "india": "102713980",
                "remote": "104112529",  # Default to Pakistan for remote
            }
            
            # Get geoId for location (case-insensitive)
            geo_id = location_to_geoid.get(location.lower(), "104112529")  # Default to Pakistan
            
            # Build URL with parameters in correct order (LinkedIn cares about parameter order!)
            # Order: currentJobId (optional) -> filters (f_AL, f_E, f_WT) -> geoId -> keywords -> origin -> refresh -> start
            search_url = "https://www.linkedin.com/jobs/search/?"
            
            # 1. Add currentJobId first if provided
            if current_job_id:
                search_url += f"currentJobId={current_job_id}&"
            
            # 2. Add all filter parameters (f_AL, f_E, f_WT)
            if easy_apply:
                search_url += "f_AL=true&"
            
            # Experience level filter (f_E parameter)
            if experience_level:
                experience_map = {
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
                exp_code = experience_map.get(experience_level.lower())
                if exp_code:
                    search_url += f"f_E={exp_code}&"
                    logger.info(f"✓ Added experience level filter: {experience_level} (f_E={exp_code})")
            
            # Work type filter (f_WT parameter)
            if work_type:
                work_type_map = {
                    "on-site": "1",
                    "onsite": "1",
                    "on site": "1",
                    "remote": "2",
                    "hybrid": "3"
                }
                wt_code = work_type_map.get(work_type.lower())
                if wt_code:
                    search_url += f"f_WT={wt_code}&"
                    logger.info(f"✓ Added work type filter: {work_type} (f_WT={wt_code})")
            
            # 3. Add geoId
            search_url += f"geoId={geo_id}&"
            
            # 4. Add keywords
            keywords_enc = quote(job_title)
            search_url += f"keywords={keywords_enc}&"
            
            # 5. Add origin
            search_url += "origin=JOB_SEARCH_PAGE_SEARCH_BUTTON&"
            
            # 6. Add refresh
            search_url += "refresh=true"
            
            # 7. Add pagination parameter (start) if not first page
            if start > 0:
                search_url += f"&start={start}"
            
            logger.info(f"Search URL: {search_url}")
            
            try:
                driver.get(search_url)
                time.sleep(3)
            except TimeoutException:
                logger.warning("Job search page load timed out, continuing with extraction anyway...")
            
            return True
            
        except Exception as e:
            logger.error(f"Error navigating to job search: {e}")
            return False
    
    def _check_no_matching_jobs(self, driver) -> bool:
        """
        Check if LinkedIn shows "no matching jobs found" message
        
        Returns:
            True if no matching jobs message is detected, False otherwise
        """
        try:
            # Check for "no matching jobs" message using multiple selectors
            no_jobs_selectors = [
                "body > div.application-outlet > div.authentication-outlet > div.scaffold-layout.scaffold-layout--breakpoint-none.scaffold-layout--list-detail.scaffold-layout--single-column.scaffold-layout--reflow.scaffold-layout--has-list-detail.jobs-search-two-pane__layout > div > div.scaffold-layout__row.scaffold-layout__header > div > p",
                ".jobs-search-no-results-banner",
                ".jobs-search-two-pane__no-results",
                ".artdeco-empty-state__message",
                "[data-test-no-search-results]"
            ]
            
            for selector in no_jobs_selectors:
                try:
                    element = driver.find_element(By.CSS_SELECTOR, selector)
                    text = element.text.lower()
                    
                    # Check for various "no results" messages
                    no_jobs_keywords = [
                        "no matching jobs",
                        "no jobs found",
                        "no results found",
                        "couldn't find any jobs",
                        "no search results"
                    ]
                    
                    if any(keyword in text for keyword in no_jobs_keywords):
                        logger.warning(f"✗ No matching jobs found message detected: '{text[:100]}'")
                        return True
                        
                except Exception:
                    continue
            
            # Also check page source as fallback
            try:
                page_source = driver.page_source.lower()
                if "no matching jobs found" in page_source or "couldn't find any jobs" in page_source:
                    logger.warning("✗ No matching jobs found in page source")
                    return True
            except Exception as e:
                logger.debug(f"Page source check failed: {e}")
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking for no matching jobs: {e}")
            return False
    
    # Removed filter verification because filters are applied via URL parameters
    
    def _apply_filters(self, driver, experience_level: str = None, work_type: str = None, easy_apply: bool = True) -> None:
        """Log filter expectations; filters are already applied via URL"""
        wait = WebDriverWait(driver, 10)
        
        try:
            # Verify Easy Apply filter is active (should be from URL parameter)
            if easy_apply:
                try:
                    # Check if Easy Apply pill/badge is visible (indicates filter is active)
                    easy_apply_pill = driver.find_element(By.XPATH, "//li[contains(@class, 'search-reusables__filter-pill-container')]//button[contains(., 'Easy Apply')]")
                    logger.info("✓ Easy Apply filter is active")
                except:
                    logger.info("Easy Apply filter pill not visible (may still be applied)")
            
            # Verify experience level filter if specified
            if experience_level:
                try:
                    exp_pill = driver.find_element(By.XPATH, f"//li[contains(@class, 'search-reusables__filter-pill-container')]\n+                                                             //button[contains(., '{experience_level}')]")
                    logger.info(f"✓ Experience level filter is active: {experience_level}")
                except:
                    logger.info(f"Experience level filter pill not visible: {experience_level}")
            
            # Verify work type filter if specified
            if work_type:
                try:
                    wt_pill = driver.find_element(By.XPATH, f"//li[contains(@class, 'search-reusables__filter-pill-container')]\n+                                                             //button[contains(., '{work_type}')]")
                    logger.info(f"✓ Work type filter is active: {work_type}")
                except:
                    logger.info(f"Work type filter pill not visible: {work_type}")
                    
        except Exception as e:
            logger.warning(f"Filter verification warning: {e}")
    
    def _extract_job_data(self, driver, job_element) -> Optional[dict]:
        """
        Extract structured data from a single job listing card.
        
        Returns dict with 6 required fields:
        - title: Job title
        - company: Company name
        - location: Job location
        - description: Job description
        - apply_url: Direct apply link (includes currentJobId param)
        - job_id: LinkedIn external job ID
        """
        wait = WebDriverWait(driver, 10)
        
        try:
            # Extract job_id from the element's data attribute BEFORE clicking
            job_id = job_element.get_attribute("data-job-id") or job_element.get_attribute("data-occludable-job-id")
            if not job_id:
                logger.debug("Cannot extract job_id - skipping job")
                return None
            
            # Click job card to load details panel
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", job_element)
            time.sleep(0.5)
            
            try:
                driver.execute_script("arguments[0].click();", job_element)
            except Exception as e:
                logger.debug(f"Could not click job card: {e}")
                # Sometimes clicking isn't necessary
            
            time.sleep(2)
            
            # Get current URL which should include currentJobId parameter
            current_url = driver.current_url
            
            # Initialize structured job data with required fields
            job_data = {
                "title": "",
                "company": "",
                "location": "",
                "description": "",
                "apply_url": current_url,
                "job_id": job_id,
                "easy_apply": False,
            }
            
            # Check for Easy Apply button - try multiple selectors
            easy_apply_selectors = [
                "//button[contains(@class, 'jobs-apply-button') and contains(., 'Easy Apply')]",
                "//button[contains(text(), 'Easy Apply')]",
                "//button[contains(@aria-label, 'Easy Apply')]",
                ".jobs-apply-button--top-card button",
                "button[aria-label*='Easy Apply']",
                ".artdeco-button[aria-label*='Easy Apply']"
            ]
            
            # Check for already applied indicators
            applied_selectors = [
                "//span[contains(text(), 'Applied')]",
                "//button[contains(text(), 'Applied')]",
                "//div[contains(text(), 'Applied')]",
                ".jobs-apply-button--applied",
                "[data-test='applied-indicator']"
            ]
            
            # Check for no longer accepting applications
            closed_selectors = [
                "//span[contains(text(), 'No longer accepting applications')]",
                "//div[contains(text(), 'No longer accepting applications')]",
                "//span[contains(text(), 'Applications closed')]",
                "//div[contains(text(), 'Applications closed')]",
                "//span[contains(text(), 'Position filled')]",
                "//div[contains(text(), 'Position filled')]"
            ]
            
            job_data["already_applied"] = False
            job_data["no_longer_accepting"] = False
            
            # Check if already applied
            for selector in applied_selectors:
                try:
                    if selector.startswith("//"):
                        driver.find_element(By.XPATH, selector)
                    else:
                        driver.find_element(By.CSS_SELECTOR, selector)
                    job_data["already_applied"] = True
                    logger.debug("Job already applied to")
                    break
                except:
                    continue
            
            # Check if no longer accepting
            for selector in closed_selectors:
                try:
                    if selector.startswith("//"):
                        driver.find_element(By.XPATH, selector)
                    else:
                        driver.find_element(By.CSS_SELECTOR, selector)
                    job_data["no_longer_accepting"] = True
                    logger.debug("Job no longer accepting applications")
                    break
                except:
                    continue
            
            # Only set easy_apply to True if not already applied and still accepting
            if not job_data["already_applied"] and not job_data["no_longer_accepting"]:
                for selector in easy_apply_selectors:
                    try:
                        if selector.startswith("//"):
                            driver.find_element(By.XPATH, selector)
                        else:
                            driver.find_element(By.CSS_SELECTOR, selector)
                        job_data["easy_apply"] = True
                        break
                    except:
                        continue
            
            # Extract job title - try multiple selectors
            job_title_selectors = [
                ".job-details-jobs-unified-top-card__job-title h1",
                ".jobs-unified-top-card__job-title",
                ".job-card-list__title",
                "h1[data-test-job-title]",
                ".t-24",
                "[data-test-job-title]"
            ]
            
            for selector in job_title_selectors:
                try:
                    job_title_element = driver.find_element(By.CSS_SELECTOR, selector)
                    title_text = job_title_element.text.strip()
                    if title_text:
                        job_data["title"] = title_text
                        logger.debug(f"Found job title using selector '{selector}': {job_data['title']}")
                        break
                except:
                    continue
            
            # Extract company name - try multiple selectors
            company_selectors = [
                ".job-details-jobs-unified-top-card__company-name a",
                ".jobs-unified-top-card__company-name",
                ".job-card-container__company-name",
                "[data-test-company-name]",
                ".t-16"
            ]
            
            for selector in company_selectors:
                try:
                    company_element = driver.find_element(By.CSS_SELECTOR, selector)
                    company_text = company_element.text.strip()
                    if company_text:
                        job_data["company"] = company_text
                        logger.debug(f"Found company using selector '{selector}': {job_data['company']}")
                        break
                except:
                    continue
            
            # Extract location - try multiple selectors
            location_selectors = [
                ".job-details-jobs-unified-top-card__location",
                ".jobs-unified-top-card__location",
                "[data-test-job-location]",
                ".job-details-base-card__metadata li:first-child"
            ]
            
            for selector in location_selectors:
                try:
                    location_element = driver.find_element(By.CSS_SELECTOR, selector)
                    location_text = location_element.text.strip()
                    if location_text:
                        job_data["location"] = location_text
                        logger.debug(f"Found location using selector '{selector}': {job_data['location']}")
                        break
                except:
                    continue
            
            # Extract description
            try:
                try:
                    show_more_button = driver.find_element(By.CSS_SELECTOR, ".jobs-description__footer-button")
                    driver.execute_script("arguments[0].click();", show_more_button)
                    time.sleep(1)
                except:
                    pass
                
                description_selectors = [
                    ".jobs-description-content__text",
                    ".jobs-box__html-content",
                    "[data-test-job-description]"
                ]
                
                for selector in description_selectors:
                    try:
                        description_element = driver.find_element(By.CSS_SELECTOR, selector)
                        desc_text = description_element.text.strip()
                        if desc_text:
                            job_data["description"] = desc_text
                            break
                    except:
                        continue
            except:
                pass
            
            return job_data
            
        except Exception as e:
            logger.warning(f"Error extracting job data: {e}")
            return None
    
    def _extract_all_jobs(self, driver) -> List[dict]:
        """Extract data from all job listings on current page by scrolling"""
        jobs_data = []
        processed_jobs = set()
        scroll_attempts = 0
        max_scroll_attempts = 10
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        logger.info("Extracting jobs from current page...")
        
        # Wait for job results container to be visible (indicates page fully loaded)
        wait = WebDriverWait(driver, 30)
        try:
            logger.info("Waiting for job results container to load...")
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-search-results")))
            logger.info("✓ Job results container detected")
            time.sleep(3)  # Wait for jobs to render
        except Exception as e:
            logger.warning(f"Results container not found: {e}")
        
        # Scroll the jobs list area to trigger lazy loading
        try:
            logger.info("Scrolling jobs list to trigger loading...")
            jobs_list = driver.find_element(By.CSS_SELECTOR, ".jobs-search-results-list")
            driver.execute_script("arguments[0].scrollTop = 0;", jobs_list)
            time.sleep(2)
        except Exception as e:
            logger.debug(f"Could not scroll jobs list: {e}")
        
        # Now wait for actual job cards to load
        try:
            logger.info("Waiting for job cards to appear in DOM (with 30s timeout)...")
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-job-id]")))
            logger.info("✓ Job cards detected in DOM")
            time.sleep(3)  # Additional wait for all cards to render
        except Exception as e:
            logger.warning(f"Timeout waiting for job cards after {e}")
            logger.info("Will continue with extraction - cards may still be available")
        
        while scroll_attempts < max_scroll_attempts:
            try:
                time.sleep(1)
                
                # Try to find job cards with best selector first
                job_cards = []
                best_selector = None
                
                job_card_selectors = [
                    "[data-job-id]",                    # Most reliable (uses data attribute)
                    "[data-occludable-job-id]",         # Alternative modern selector
                    ".base-card",                        # New LinkedIn UI
                    ".job-card-container",               # Older LinkedIn UI
                    ".jobs-search-results__list-item",   # List item
                    ".jobs-details-base-card"            # Alternative
                ]
                
                for selector in job_card_selectors:
                    try:
                        found_cards = driver.find_elements(By.CSS_SELECTOR, selector)
                        if found_cards and len(found_cards) > 0:
                            job_cards = found_cards
                            best_selector = selector
                            logger.info(f"✓ Found {len(job_cards)} job cards using selector: {selector}")
                            break
                    except Exception as e:
                        logger.debug(f"Selector '{selector}' failed: {e}")
                        continue
                
                if not job_cards:
                    logger.warning("No job cards found with any selector. Checking page source...")
                    # Try to see if jobs container exists at all
                    try:
                        results_container = driver.find_element(By.CSS_SELECTOR, ".jobs-search-results")
                        logger.info("Results container found, but no job cards - trying JavaScript extraction")
                        # Execute JavaScript to check what's actually in the page
                        job_count_js = driver.execute_script("return document.querySelectorAll('[data-job-id]').length;")
                        logger.info(f"JavaScript found {job_count_js} job cards with [data-job-id]")
                        if job_count_js == 0:
                            # Try to get page source for debugging
                            page_source = driver.page_source[2000:4000]  # Middle part of page
                            logger.debug(f"Page source sample: {page_source}")
                    except Exception as debug_e:
                        logger.debug(f"Debug check failed: {debug_e}")
                    
                    scroll_attempts += 1
                    if scroll_attempts < 3:
                        # Try scrolling more aggressively
                        try:
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            logger.info("Scrolled page, retrying...")
                            time.sleep(3)
                        except:
                            pass
                    continue
                
                initial_job_count = len(jobs_data)
                
                for idx, job_card in enumerate(job_cards):
                    try:
                        job_id = job_card.get_attribute("data-job-id") or job_card.get_attribute("data-occludable-job-id")
                        if not job_id:
                            logger.debug(f"Job card {idx} has no job ID, skipping")
                            continue
                            
                        if job_id in processed_jobs:
                            logger.debug(f"Job {job_id} already processed, skipping")
                            continue
                        
                        processed_jobs.add(job_id)
                        
                        job_info = self._extract_job_data(driver, job_card)
                        if job_info and (job_info["title"] or job_info["company"]):
                            jobs_data.append(job_info)
                            logger.info(f"  ✓ Job {len(jobs_data)}: {job_info['title'][:50]} @ {job_info['company'][:30]}")
                        else:
                            logger.debug(f"Job {job_id}: No title or company found")
                    except Exception as e:
                        logger.debug(f"Error processing job card {idx}: {e}")
                        continue
                
                # Scroll down to load more jobs on same page
                try:
                    job_list = driver.find_element(By.CSS_SELECTOR, ".jobs-search-results-list")
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", job_list)
                    logger.debug("Scrolled job list to bottom")
                except:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    logger.debug("Scrolled page to bottom")
                
                time.sleep(2)
                
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height and len(jobs_data) == initial_job_count:
                    scroll_attempts += 1
                    logger.debug(f"No new content after scroll. Attempt {scroll_attempts}/{max_scroll_attempts}")
                else:
                    scroll_attempts = 0
                    logger.debug(f"Found {len(jobs_data) - initial_job_count} new jobs after scroll")
                last_height = new_height
                
            except Exception as e:
                logger.error(f"Error during job extraction: {e}")
                scroll_attempts += 1
        
        logger.info(f"✓ Extracted {len(jobs_data)} jobs from current page")
        return jobs_data
    
    def scrape_jobs(
        self,
        job_title: str,
        location: str,
        session_id: str,
        experience_level: str = None,
        work_type: str = None,
        easy_apply: bool = True,
        current_job_id: str = None,
        page_load_timeout: int = 60,
        script_timeout: int = 120,
        max_pages: int = 1,
    ) -> List[dict]:
        """
        Scrape LinkedIn jobs for given parameters using live Selenium session
        
        Args:
            job_title: Job title to search
            location: Location to search
            session_id: Selenium session ID with live login (required)
            experience_level: Optional experience level filter
            work_type: Optional work type filter (Remote/Hybrid/Onsite)
            easy_apply: Filter for Easy Apply jobs only
            page_load_timeout: Page load timeout in seconds (default 60)
            script_timeout: Script execution timeout in seconds (default 120)
            max_pages: Maximum number of pages to scrape (default 1, use -1 for all available pages)
        
        Returns:
            List of parsed jobs
        """
        if not session_id:
            raise ValueError("session_id is required. Must use live Selenium session with authenticated login.")
        
        logger.info(f"Starting job scrape using Selenium session: {session_id}")
        logger.info(f"   Job title: {job_title}, Location: {location}")
        logger.info(f"   Timeouts - Page Load: {page_load_timeout}s, Script: {script_timeout}s")
        
        # Note: Cookie injection removed - session must be pre-authenticated via live Selenium login
        all_parsed_jobs = []
        
        driver = None  # Initialize driver variable
        try:
            # Get driver from existing Selenium session (authenticated)
            from application.services.linkedin_session_manager import get_session_manager
            session_manager = get_session_manager()
            
            session = session_manager.get_session(session_id)
            if not session:
                logger.error(f"LinkedIn session {session_id} not found")
                return []
            
            # Get driver from session (should be open)
            driver = session.driver
            if not driver:
                logger.error(f"Driver not available for session {session_id} - browser may have been closed")
                return []
            
            logger.info(f"🔐 Using live Selenium session: {session_id}")
            
            # Verify login is still active
            if not self._verify_login(driver):
                logger.error("Login verification failed - session may have expired")
                return []
            
            logger.info(f"✅ Login verified, searching jobs with Easy Apply: {easy_apply}")
            
            # Pagination loop
            current_page = 1
            jobs_on_current_page = 0
            
            while True:
                # Check page limit
                if max_pages > 0 and current_page > max_pages:
                    logger.info(f"Reached maximum page limit ({max_pages}). Stopping pagination.")
                    break
                
                # Calculate start parameter for LinkedIn pagination (0, 25, 50, 75, etc.)
                start = (current_page - 1) * 25
                
                logger.info(f"--- Scraping Page {current_page} (start={start}) ---")
                
                # Search jobs for current page
                if not self._search_jobs(
                    driver, 
                    job_title, 
                    location, 
                    easy_apply, 
                    experience_level, 
                    work_type, 
                    current_job_id, 
                    timeout=page_load_timeout,
                    start=start  # New pagination parameter
                ):
                    logger.error(f"Job search navigation failed for page {current_page}")
                    break
                
                # Apply filters (already in URL); skip on-page verification to avoid brittle checks
                self._apply_filters(driver, experience_level, work_type, easy_apply)
                
                # Check for "no matching jobs found" message
                if self._check_no_matching_jobs(driver):
                    logger.warning(f"✗ No matching jobs found for '{job_title}' in '{location}'. Stopping scraping for this role.")
                    return []
                
                # Extract jobs from current page
                logger.info(f"Extracting jobs from page {current_page}...")
                raw_jobs = self._extract_all_jobs(driver)
                jobs_on_current_page = len(raw_jobs)
                
                if jobs_on_current_page == 0:
                    logger.info(f"No jobs found on page {current_page}. Stopping pagination.")
                    break
                
                # Parse jobs with structured data
                for job in raw_jobs:
                    try:
                        job_id = extract_job_id(job.get("apply_url", ""))
                        experience = parse_experience(job.get("job_description", ""))
                        salary_min, salary_max, currency = parse_salary(job.get("job_description", ""))
                        detected_work_type = parse_work_type(job.get("job_description", ""))
                        
                        parsed_job = {
                            "external_id": job_id,
                            "title": job.get("job_title", ""),
                            "company": job.get("company_name", ""),
                            "description": job.get("job_description", ""),
                            "url": job.get("apply_url", ""),
                            "location": location,
                            "work_type": detected_work_type or work_type,
                            "salary_min": salary_min,
                            "salary_max": salary_max,
                            "salary_currency": currency,
                            "experience_years": experience,
                            "platform": "linkedin",
                            "easy_apply": job.get("has_easy_apply", False),
                            "page_number": current_page,  # NEW: Track pagination source
                            "scraped_at": datetime.utcnow(),  # NEW: Track scrape timestamp
                        }
                        all_parsed_jobs.append(parsed_job)
                    except Exception as e:
                        logger.warning(f"Error parsing job {job.get('job_title', 'Unknown')}: {e}")
                        continue
                
                logger.info(f"Page {current_page}: Parsed {jobs_on_current_page} jobs (Total: {len(all_parsed_jobs)})")
                
                # Move to next page with randomized delay
                current_page += 1
                
                # Add randomized delay between pages (90-120 seconds) to prevent rate limiting
                if not (max_pages > 0 and current_page > max_pages) and jobs_on_current_page > 0:
                    delay_seconds = 90 + random.uniform(0, 30)  # 90-120 second range
                    logger.info(f"Waiting {delay_seconds:.1f}s before scraping next page (anti-429 rate limiting)...")
                    time.sleep(delay_seconds)
            
            logger.info(f"✓ Scraping complete! Scraped {len(all_parsed_jobs)} total jobs across {current_page - 1} pages for '{job_title}' in '{location}'")
            return all_parsed_jobs
            
        except TimeoutException as e:
            logger.error(f"Timeout during job scraping (timeout={script_timeout}s): {e}")
            logger.info("Timeout usually means: Selenium hung waiting for page load, browser command took too long, or server not responding")
            return all_parsed_jobs  # Return whatever was scraped so far
        except WebDriverException as e:
            logger.error(f"WebDriver error during job scraping: {e}")
            return all_parsed_jobs
        except Exception as e:
            logger.error(f"Unexpected error during job scraping: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return all_parsed_jobs
        finally:
            # Don't close driver - keep it alive for subsequent operations
            # The session manager will handle cleanup after 30 minutes
            logger.info("Keeping driver alive for session reuse")
            pass
    
    def scrape_jobs_by_url(
        self,
        search_url: str,
        cookies: List[dict],
        page_load_timeout: int = 60,
        script_timeout: int = 120,
        max_pages: int = 1,
    ) -> Tuple[List[dict], List[dict], dict]:
        """
        Scrape LinkedIn jobs using a pre-built search URL
        
        This method accepts a complete LinkedIn search URL with all filters already embedded.
        It's designed to work with URLs generated by LinkedInURLBuilder.
        
        Args:
            search_url: Complete LinkedIn job search URL with all filters embedded
            cookies: Browser cookies for authentication
            page_load_timeout: Page load timeout in seconds (default 60)
            script_timeout: Script execution timeout in seconds (default 120)
            max_pages: Maximum number of pages to scrape (default 1, use -1 for all available pages)
        
        Returns:
            Tuple of (parsed_jobs, fresh_cookies, filter_verification_results)
        """
        if not SELENIUM_AVAILABLE:
            logger.warning("Simulating job scraping (Selenium not available)")
            return self._simulate_scraping("Job from URL"), cookies, {}
        
        driver = None
        all_parsed_jobs = []
        fresh_cookies = cookies
        filter_verification = {}
        
        try:
            logger.info(f"Starting job scrape with pre-built URL: {search_url}")
            logger.info(f"Timeouts - Page Load: {page_load_timeout}s, Script: {script_timeout}s")
            logger.info(f"Pagination - Max pages to scrape: {max_pages if max_pages > 0 else 'All available'}")
            
            # Initialize driver with timeout
            driver = self._setup_driver(timeout=page_load_timeout)
            if not driver:
                logger.error("Failed to initialize driver")
                return [], cookies, {}
            
            # Inject cookies
            if not self._inject_cookies(driver, cookies, timeout=30):
                logger.error("Failed to inject cookies")
                return [], cookies, {}
            
            # Verify login
            if not self._verify_login(driver):
                logger.error("Login verification failed")
                return [], cookies, {}
            
            logger.info("Login verified, navigating to pre-built search URL")
            
            # Pagination loop
            current_page = 1
            jobs_on_current_page = 0
            
            while True:
                # Check page limit
                if max_pages > 0 and current_page > max_pages:
                    logger.info(f"Reached maximum page limit ({max_pages}). Stopping pagination.")
                    break
                
                # Calculate start parameter for LinkedIn pagination (0, 25, 50, 75, etc.)
                start = (current_page - 1) * 25
                
                logger.info(f"--- Scraping Page {current_page} (start={start}) ---")
                
                # Build URL for current page (add/update start parameter)
                page_url = search_url
                if start > 0:
                    # Add or update start parameter
                    if "&start=" in page_url or "?start=" in page_url:
                        # Replace existing start parameter
                        import re
                        page_url = re.sub(r'[&?]start=\d+', f'&start={start}', page_url)
                    else:
                        # Add start parameter
                        page_url += f"&start={start}"
                
                logger.info(f"Navigating to: {page_url}")
                
                # Navigate to search URL
                try:
                    driver.set_page_load_timeout(page_load_timeout)
                    driver.get(page_url)
                    time.sleep(3)
                except TimeoutException:
                    logger.warning(f"Page load timed out for page {current_page}, continuing anyway...")
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Navigation error for page {current_page}: {e}")
                    break
                
                # Check for "no matching jobs found" message
                if self._check_no_matching_jobs(driver):
                    logger.warning(f"✗ No matching jobs found. Stopping scraping.")
                    fresh_cookies = self._extract_fresh_cookies(driver)
                    return [], fresh_cookies, filter_verification
                
                # Extract jobs from current page
                logger.info(f"Extracting jobs from page {current_page}...")
                raw_jobs = self._extract_all_jobs(driver)
                jobs_on_current_page = len(raw_jobs)
                
                if jobs_on_current_page == 0:
                    logger.info(f"No jobs found on page {current_page}. Stopping pagination.")
                    break
                
                # Parse jobs with structured data
                for job in raw_jobs:
                    try:
                        job_id = extract_job_id(job.get("apply_url", ""))
                        experience = parse_experience(job.get("job_description", ""))
                        salary_min, salary_max, currency = parse_salary(job.get("job_description", ""))
                        detected_work_type = parse_work_type(job.get("job_description", ""))
                        
                        # Extract location from job data if available
                        job_location = job.get("location", "Unknown")
                        
                        parsed_job = {
                            "external_id": job_id,
                            "title": job.get("job_title", ""),
                            "company": job.get("company_name", ""),
                            "description": job.get("job_description", ""),
                            "url": job.get("apply_url", ""),
                            "location": job_location,
                            "work_type": detected_work_type,
                            "salary_min": salary_min,
                            "salary_max": salary_max,
                            "salary_currency": currency,
                            "experience_years": experience,
                            "platform": "linkedin",
                            "easy_apply": job.get("has_easy_apply", False),
                        }
                        all_parsed_jobs.append(parsed_job)
                    except Exception as e:
                        logger.warning(f"Error parsing job {job.get('job_title', 'Unknown')}: {e}")
                        continue
                
                logger.info(f"Page {current_page}: Parsed {jobs_on_current_page} jobs (Total: {len(all_parsed_jobs)})")
                
                # Move to next page
                current_page += 1
                time.sleep(2)  # Pause between pages to avoid rate limiting
            
            # Extract fresh cookies
            fresh_cookies = self._extract_fresh_cookies(driver)
            
            logger.info(f"✓ Scraping complete! Scraped {len(all_parsed_jobs)} total jobs across {current_page - 1} pages")
            return all_parsed_jobs, fresh_cookies, filter_verification
            
        except TimeoutException as e:
            logger.error(f"Timeout during job scraping (timeout={script_timeout}s): {e}")
            logger.info("Timeout usually means: Selenium hung waiting for page load, browser command took too long, or server not responding")
            return all_parsed_jobs, fresh_cookies, filter_verification  # Return whatever was scraped so far
        except WebDriverException as e:
            logger.error(f"WebDriver error during job scraping: {e}")
            return all_parsed_jobs, fresh_cookies, filter_verification
        except Exception as e:
            logger.error(f"Unexpected error during job scraping: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return all_parsed_jobs, fresh_cookies, filter_verification
        finally:
            if driver:
                try:
                    driver.quit()
                    logger.info("Driver closed successfully")
                except Exception as e:
                    logger.warning(f"Error closing driver: {e}")
    
    def _simulate_scraping(self, job_title: str) -> List[dict]:
        """Simulate job scraping for testing"""
        return [
            {
                "external_id": f"sim_{int(time.time())}",
                "title": f"Simulated {job_title}",
                "company": "Test Company",
                "description": "Simulated job description",
                "url": "https://linkedin.com/jobs/simulated",
                "location": "Remote",
                "work_type": "Remote",
                "salary_min": 50000,
                "salary_max": 100000,
                "salary_currency": "USD",
                "experience_years": 2,
                "platform": "linkedin",
                "easy_apply": True,
            }
        ]
