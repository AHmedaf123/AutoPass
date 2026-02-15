"""
Easy Apply Automation - FIXED VERSION
Selenium-based LinkedIn Easy Apply form automation
"""
import time
import json
import tempfile
import base64
import os
import random
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from loguru import logger

# Selenium imports (optional)
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import Select
    from selenium.common.exceptions import (
        TimeoutException, 
        NoSuchElementException,
        ElementClickInterceptedException,
        StaleElementReferenceException
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not available - Easy Apply will be simulated")


@dataclass
class ApplicationResult:
    """Result of an application attempt"""
    success: bool
    job_id: str
    message: str
    error: Optional[str] = None


class EasyApplyAutomation:
    """
    LinkedIn Easy Apply automation using Selenium.
    
    Handles multi-page forms, field detection, and form submission.
    """
    
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    def __init__(self, form_answer_generator=None):
        """
        Initialize Easy Apply automation.
        
        Args:
            form_answer_generator: Optional FormAnswerGenerator for AI answers
        """
        self.driver = None
        self.form_generator = form_answer_generator
        self.temp_resume_path = None
        self.answered_questions = {}  # Cache of questions already answered
    
    def setup_driver(self, headless: bool = True) -> Optional[Any]:
        """Initialize Chrome driver with stealth settings"""
        if not SELENIUM_AVAILABLE:
            logger.warning("Selenium not available")
            return None
        
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument(f"user-agent={self.USER_AGENT}")
        
        if headless:
            chrome_options.add_argument("--headless=new")
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            
            # Mask webdriver detection
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
            })
            
            self.driver.maximize_window()
            return self.driver
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            return None
    
    def inject_cookies(self, cookies: List[dict]) -> None:
        """Inject LinkedIn cookies into browser session"""
        if not self.driver:
            return
        
        try:
            self.driver.get("https://www.linkedin.com")
            time.sleep(2)
            
            min_expiry = int(time.time()) + 172800  # 48 hours
            
            for cookie in cookies:
                cookie_dict = {
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': '.linkedin.com',
                    'path': cookie.get('path', '/'),
                    'secure': cookie.get('secure', True)
                }
                
                original_expiry = cookie.get('expiry')
                if original_expiry is None or original_expiry < min_expiry:
                    cookie_dict['expiry'] = min_expiry
                else:
                    cookie_dict['expiry'] = original_expiry
                
                if 'httpOnly' in cookie:
                    cookie_dict['httpOnly'] = cookie['httpOnly']
                
                try:
                    self.driver.add_cookie(cookie_dict)
                except Exception as e:
                    logger.debug(f"Failed to add cookie {cookie.get('name')}: {e}")
            
            # Navigate to feed to verify login
            self.driver.get("https://www.linkedin.com/feed/")
            time.sleep(3)
        except Exception as e:
            logger.error(f"Failed to inject cookies: {e}")
    
    def verify_login(self) -> bool:
        """Verify successful LinkedIn login"""
        if not self.driver:
            return False
        
        try:
            current_url = self.driver.current_url
            
            if "linkedin.com/feed" in current_url:
                return True
            
            try:
                self.driver.find_element(By.ID, "global-nav")
                return True
            except NoSuchElementException:
                pass
            
            if "login" in current_url or "checkpoint" in current_url:
                return False
            
            return False
        except Exception as e:
            logger.error(f"Error verifying login: {e}")
            return False
    
    def create_temp_resume(self, resume_base64: str) -> str:
        """
        Create temporary resume PDF file from base64.
        
        Args:
            resume_base64: Base64 encoded PDF
            
        Returns:
            Path to temporary resume file
        """
        try:
            resume_bytes = base64.b64decode(resume_base64)
            
            temp_file = tempfile.NamedTemporaryFile(
                suffix=".pdf",
                delete=False,
                prefix="resume_"
            )
            temp_file.write(resume_bytes)
            temp_file.close()
            
            self.temp_resume_path = temp_file.name
            return self.temp_resume_path
        except Exception as e:
            logger.error(f"Failed to create temp resume: {e}")
            return ""

    @staticmethod
    def _normalize_job_url(job_url: str) -> str:
        """Normalize LinkedIn job URLs to a stable currentJobId search URL.

        Examples:
        - https://www.linkedin.com/jobs/search/?currentJobId=4235967640&f_AL=true -> https://www.linkedin.com/jobs/search/?currentJobId=4235967640
        - https://www.linkedin.com/jobs/view/4235967640 -> stays unchanged
        """
        try:
            match = re.search(r"currentJobId=(\d+)", job_url)
            if match:
                job_id = match.group(1)
                return f"https://www.linkedin.com/jobs/search/?currentJobId={job_id}"
        except Exception as exc:
            logger.debug(f"Job URL normalization failed: {exc}")
        return job_url
    
    def navigate_to_job(self, job_url: str) -> bool:
        """Navigate to job listing page with refresh and cookie update strategy"""
        if not self.driver:
            return False
        
        try:
            target_url = self._normalize_job_url(job_url)
            logger.info(f"Navigating to job URL (normalized): {target_url}")

            self.driver.get(target_url)
            
            # Wait for initial page load
            time.sleep(3)
            
            # Refresh the page to ensure fresh content and cookies
            logger.info("Refreshing page to get latest content...")
            self.driver.refresh()
            time.sleep(3)
            
            current_url = self.driver.current_url
            logger.info(f"Current URL after navigation and refresh: {current_url}")
            
            # Wait for page elements to load
            try:
                wait = WebDriverWait(self.driver, 10)
                wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".jobs-unified-top-card, .job-details-jobs-unified-top-card")
                    )
                )
                logger.info("Job details card loaded successfully")
            except TimeoutException:
                logger.warning("Job details card did not load within timeout")
            
            # Check for error pages but allow if Easy Apply button exists
            page_source = self.driver.page_source.lower()
            if "no matching jobs found" in page_source or "problem loading" in page_source:
                try:
                    easy_apply_elements = self.driver.find_elements(
                        By.XPATH, 
                        "//a[contains(., 'Easy Apply')] | //button[contains(., 'Easy Apply')]"
                    )
                    if easy_apply_elements:
                        logger.warning("Error text detected but Easy Apply elements present; continuing")
                        return True
                except Exception:
                    pass
                logger.warning(f"LinkedIn reported error page; continuing anyway: {current_url}")
                return True
            
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to job: {e}")
            return False
    
    def click_easy_apply(self) -> bool:
        """Find and click the Easy Apply button/anchor"""
        if not self.driver:
            return False
        
        # First, wait for page to fully load
        time.sleep(3)
        
        wait = WebDriverWait(self.driver, 15)
        
        # LinkedIn uses ANCHOR TAGS for Easy Apply
        anchor_selectors = [
            "//a[.//span[contains(text(), 'Easy Apply')]]",
            "//a[contains(., 'Easy Apply')]",
            "//a[contains(@class, 'jobs-apply-button')]",
            "//a[@data-control-name='jobdetails_topcard_inapply']",
            "//a[@data-job-id]//span[contains(text(), 'Easy Apply')]/ancestor::a",
        ]
        
        for selector in anchor_selectors:
            try:
                anchor = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                logger.info(f"Found Easy Apply anchor with: {selector}")
                
                # Scroll into view
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", anchor)
                time.sleep(1.5)
                
                # Try multiple click methods
                clicked = False
                
                # Method 1: Regular click
                try:
                    anchor.click()
                    clicked = True
                    logger.info("Clicked anchor with regular click")
                except Exception as e:
                    logger.debug(f"Regular click failed: {e}")
                
                # Method 2: JS click if regular failed
                if not clicked:
                    try:
                        self.driver.execute_script("arguments[0].click();", anchor)
                        clicked = True
                        logger.info("Clicked anchor with JS click")
                    except Exception as e:
                        logger.debug(f"JS click failed: {e}")
                
                # Method 3: ActionChains click
                if not clicked:
                    try:
                        self._human_click(anchor)
                        clicked = True
                        logger.info("Clicked anchor with ActionChains")
                    except Exception as e:
                        logger.debug(f"ActionChains click failed: {e}")
                
                if clicked:
                    # Wait longer for modal to appear after first click
                    logger.info("Waiting for Easy Apply modal to load...")
                    time.sleep(5)
                    try:
                        modal_wait = WebDriverWait(self.driver, 10)
                        modal_wait.until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, "[role='dialog'], .artdeco-modal, .jobs-easy-apply-modal")
                            )
                        )
                        logger.info("✓ Easy Apply modal appeared after click")
                        # Additional wait to ensure modal is fully rendered
                        time.sleep(2)
                        return True
                    except TimeoutException:
                        logger.warning("Modal did not appear after anchor click, continuing to buttons...")
                        continue
                        
            except TimeoutException:
                continue
            except Exception as e:
                logger.debug(f"Anchor selector {selector} failed: {e}")
                continue
        
        # Fallback to button selectors
        button_selectors = [
            "//button[contains(@class, 'jobs-apply-button')]",
            "//button[contains(@class, 'jobs-apply-button--top-card')]",
            "//button[contains(@class, 'artdeco-button') and contains(., 'Easy Apply')]",
            "//button[contains(., 'Easy Apply')]",
            "//button[contains(@aria-label, 'Easy Apply')]",
            "//span[contains(text(), 'Easy Apply')]/ancestor::button",
            "//button[@data-control-name='jobdetails_topcard_inapply']",
        ]
        
        for selector in button_selectors:
            try:
                button = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                logger.info(f"Found Easy Apply button with: {selector}")
                
                # Scroll into view
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                time.sleep(1.5)
                
                # Try multiple click methods
                clicked = False
                
                # Method 1: Regular click
                try:
                    button.click()
                    clicked = True
                    logger.info("Clicked button with regular click")
                except Exception as e:
                    logger.debug(f"Regular click failed: {e}")
                
                # Method 2: JS click if regular failed
                if not clicked:
                    try:
                        self.driver.execute_script("arguments[0].click();", button)
                        clicked = True
                        logger.info("Clicked button with JS click")
                    except Exception as e:
                        logger.debug(f"JS click failed: {e}")
                
                # Method 3: ActionChains click
                if not clicked:
                    try:
                        self._human_click(button)
                        clicked = True
                        logger.info("Clicked button with ActionChains")
                    except Exception as e:
                        logger.debug(f"ActionChains click failed: {e}")
                
                if clicked:
                    # Wait longer for modal to appear after first click
                    logger.info("Waiting for Easy Apply modal to load...")
                    time.sleep(5)
                    try:
                        modal_wait = WebDriverWait(self.driver, 10)
                        modal_wait.until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, "[role='dialog'], .artdeco-modal, .jobs-easy-apply-modal")
                            )
                        )
                        logger.info("✓ Easy Apply modal appeared after click")
                        # Additional wait to ensure modal is fully rendered
                        time.sleep(2)
                        return True
                    except TimeoutException:
                        logger.warning("Modal did not appear after button click, continuing...")
                        continue
                        
            except TimeoutException:
                continue
            except Exception as e:
                logger.debug(f"Button selector {selector} failed: {e}")
                continue
        
        # Last resort: text search with verification
        try:
            logger.info("Trying text search as last resort...")
            elements = self.driver.find_elements(By.CSS_SELECTOR, "a, button")
            for elem in elements:
                try:
                    elem_text = elem.text.lower()
                    if "easy apply" in elem_text and elem.is_displayed() and elem.is_enabled():
                        logger.info(f"Found Easy Apply via text search: {elem.tag_name} - '{elem.text}'")
                        
                        # Scroll and click
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                        time.sleep(1.5)
                        
                        try:
                            elem.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", elem)
                        
                        # Wait longer for modal
                        logger.info("Waiting for Easy Apply modal to load...")
                        time.sleep(5)
                        try:
                            modal_wait = WebDriverWait(self.driver, 10)
                            modal_wait.until(
                                EC.presence_of_element_located(
                                    (By.CSS_SELECTOR, "[role='dialog'], .artdeco-modal, .jobs-easy-apply-modal")
                                )
                            )
                            logger.info("✓ Easy Apply modal appeared after text search click")
                            # Additional wait to ensure modal is fully rendered
                            time.sleep(2)
                            return True
                        except TimeoutException:
                            logger.debug("Modal did not appear, trying next element...")
                            continue
                            
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"Text search element failed: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Text search failed: {e}")
        
        logger.error("Could not find or click Easy Apply button - no modal appeared")
        return False
    
    def _human_click(self, element) -> None:
        """Perform human-like click with random movement"""
        if not self.driver:
            return
        
        try:
            actions = ActionChains(self.driver)
            
            # Move to element with slight offset
            offset_x = random.randint(-5, 5)
            offset_y = random.randint(-5, 5)
            
            actions.move_to_element_with_offset(element, offset_x, offset_y)
            actions.pause(random.uniform(0.1, 0.3))
            actions.click()
            actions.perform()
        except Exception as e:
            logger.debug(f"Human click failed: {e}")
            # Fallback to JS click
            self.driver.execute_script("arguments[0].click();", element)

    def _scroll_modal_to_bottom(self) -> None:
        """Scroll the Easy Apply modal to bottom to reveal footer buttons."""
        if not self.driver:
            return
        try:
            # Try modal container
            modal = None
            try:
                modal = self.driver.find_element(By.CSS_SELECTOR, "[role='dialog'] .artdeco-modal__content")
            except NoSuchElementException:
                try:
                    modal = self.driver.find_element(By.CSS_SELECTOR, ".artdeco-modal__content")
                except NoSuchElementException:
                    pass
            
            if modal:
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", modal)
                time.sleep(0.5)
            
            # Also scroll page as fallback
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.3)
        except Exception as e:
            logger.debug(f"Scroll modal failed: {e}")
    
    def _sanitize_text(self, text: str, max_len: int = 500) -> str:
        """Sanitize text: remove emojis/non-printables and trim length."""
        try:
            if not text:
                return ""
            import re
            # Remove non-printable and emoji characters
            cleaned = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
            cleaned = re.sub(r"[\ud800-\udfff]", "", cleaned)
            cleaned = re.sub(r"[^\n\r\t\x20-\x7E]", "", cleaned)
            cleaned = cleaned.strip()
            if len(cleaned) > max_len:
                cleaned = cleaned[:max_len]
            return cleaned
        except Exception:
            return str(text)[:max_len] if text else ""

    def _select_radio_option(self, radio_elements, preferred_value: str = "yes") -> bool:
        """Select a radio option matching the preferred value."""
        try:
            preferred = (preferred_value or "").lower()
            
            # Try to match by label or value
            for elem in radio_elements:
                try:
                    label_text = ""
                    try:
                        label = elem.find_element(By.XPATH, "following-sibling::*[1]")
                        label_text = (label.text or "").strip()
                    except (NoSuchElementException, StaleElementReferenceException):
                        pass

                    value_attr = (elem.get_attribute("value") or "").strip()
                    if preferred and (
                        preferred in label_text.lower() or preferred in value_attr.lower()
                    ):
                        if elem.is_displayed() and elem.is_enabled():
                            self._human_click(elem)
                            return True
                except StaleElementReferenceException:
                    continue

            # Fallback: pick first displayed option
            for elem in radio_elements:
                try:
                    if elem.is_displayed() and elem.is_enabled():
                        self._human_click(elem)
                        return True
                except StaleElementReferenceException:
                    continue
        except Exception as e:
            logger.debug(f"Failed to select radio option: {e}")
        return False
    
    def fill_form_field(
        self,
        field_element,
        value: str,
        field_type: str = "text"
    ) -> bool:
        """Fill a form field with the given value."""
        try:
            if field_type in ["text", "textarea"]:
                field_element.clear()
                # Type like a human
                for char in str(value):
                    field_element.send_keys(char)
                    time.sleep(random.uniform(0.02, 0.08))
                return True
            
            elif field_type == "dropdown":
                select = Select(field_element)
                # Try to find matching option
                for option in select.options:
                    if str(value).lower() in option.text.lower():
                        select.select_by_visible_text(option.text)
                        return True
                # Default to first non-empty option
                if len(select.options) > 1:
                    select.select_by_index(1)
                return True
            
            elif field_type == "checkbox":
                if not field_element.is_selected():
                    self._human_click(field_element)
                return True
            
            elif field_type == "file":
                if value and os.path.exists(value):
                    field_element.send_keys(value)
                    return True
                return False
            
        except Exception as e:
            logger.warning(f"Failed to fill field: {e}")
            return False
        
        return False
    
    def process_form_page(
        self,
        user_data: Dict[str, Any],
        job_data: Dict[str, Any],
        context: Any = None
    ) -> bool:
        """Process current form page and fill all fields (synchronous version)."""
        if not self.driver:
            return False
        
        try:
            # Find all form groups
            form_groups = self.driver.find_elements(
                By.CSS_SELECTOR, 
                ", ".join([
                    ".jobs-easy-apply-form-section__grouping",
                    ".fb-form-element",
                    "[data-test-form-builder-text-input-form-component]",
                    "[data-test-form-builder-text-area-form-component]",
                    "[data-test-form-builder-dropdown-form-component]",
                    "[data-test-form-builder-radio-button-form-component]",
                    "[data-test-form-builder-checkbox-form-component]",
                    "[data-test-form-builder-file-upload-form-component]",
                ])
            )
            
            for group in form_groups:
                try:
                    self._process_form_group(group, user_data, job_data, context)
                except StaleElementReferenceException:
                    logger.debug("Stale element in form group, skipping")
                    continue
            
            return True
        
        except Exception as e:
            logger.error(f"Error processing form page: {e}")
            return False
    
    async def process_form_page_async(
        self,
        user_data: Dict[str, Any],
        job_data: Dict[str, Any]
    ) -> bool:
        """Async version: Process form page with LLM answers for unknown questions."""
        if not self.driver:
            return False
        
        try:
            # Find all form groups
            form_groups = self.driver.find_elements(
                By.CSS_SELECTOR, 
                ", ".join([
                    ".jobs-easy-apply-form-section__grouping",
                    ".fb-form-element",
                    "[data-test-form-builder-text-input-form-component]",
                    "[data-test-form-builder-text-area-form-component]",
                    "[data-test-form-builder-dropdown-form-component]",
                    "[data-test-form-builder-radio-button-form-component]",
                    "[data-test-form-builder-checkbox-form-component]",
                    "[data-test-form-builder-file-upload-form-component]",
                ])
            )

            # Collect unanswered questions for batch LLM answering
            pending_questions = []
            from .form_answer_generator import detect_field_type, FormAnswerContext

            for group in form_groups:
                try:
                    # Extract question/label
                    question = ""
                    try:
                        label_elem = group.find_element(By.CSS_SELECTOR, "label, legend, span.t-bold")
                        question = (label_elem.text or "").strip()
                    except (NoSuchElementException, StaleElementReferenceException):
                        pass
                    
                    if not question:
                        continue

                    field_type = detect_field_type(question)

                    # Identify input element
                    input_elem = None
                    input_type = "text"
                    radio_elements = []

                    try:
                        input_elem = group.find_element(By.CSS_SELECTOR, 
                            "input[type='text'], input[type='email'], input[type='tel'], input[type='number'], input[type='url']")
                    except (NoSuchElementException, StaleElementReferenceException):
                        pass

                    if not input_elem:
                        try:
                            input_elem = group.find_element(By.CSS_SELECTOR, "textarea")
                            input_type = "textarea"
                        except (NoSuchElementException, StaleElementReferenceException):
                            pass

                    if not input_elem:
                        try:
                            input_elem = group.find_element(By.CSS_SELECTOR, "select")
                            input_type = "dropdown"
                        except (NoSuchElementException, StaleElementReferenceException):
                            pass

                    if not input_elem:
                        try:
                            input_elem = group.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                            input_type = "checkbox"
                        except (NoSuchElementException, StaleElementReferenceException):
                            pass

                    if not input_elem:
                        try:
                            input_elem = group.find_element(By.CSS_SELECTOR, "input[type='file']")
                            input_type = "file"
                        except (NoSuchElementException, StaleElementReferenceException):
                            pass

                    if not input_elem:
                        try:
                            radio_elements = group.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                            if radio_elements:
                                input_type = "radio"
                        except (NoSuchElementException, StaleElementReferenceException):
                            pass

                    if not input_elem and not radio_elements:
                        continue

                    # Try standard value mapping first
                    value = self._get_field_value(field_type, user_data, job_data, None, question)

                    # Specialized generation for headline/summary/cover letter
                    if not value and self.form_generator and field_type in ["headline", "summary", "cover_letter"]:
                        try:
                            context = FormAnswerContext(
                                job_title=job_data.get("title", ""),
                                company=job_data.get("company", ""),
                                job_description=job_data.get("description", ""),
                                user_name=user_data.get("full_name", ""),
                                user_email=user_data.get("email", ""),
                                resume_summary=user_data.get("resume_summary", ""),
                                skills=user_data.get("skills", []),
                                experience=user_data.get("experience", []),
                                education=user_data.get("education", [])
                            )
                            if field_type == "headline":
                                value = await self.form_generator.generate_headline(context)
                            elif field_type == "summary":
                                value = await self.form_generator.generate_summary(context)
                            elif field_type == "cover_letter":
                                value = await self.form_generator.generate_cover_letter(context)
                        except Exception as e:
                            logger.warning(f"Failed specialized generation for {field_type}: {e}")
                            value = ""

                    # File inputs: auto attach resume
                    if input_type == "file" and not value and self.temp_resume_path:
                        value = self.temp_resume_path

                    # If we have a value, fill now; else collect for batch
                    if value:
                        value = self._sanitize_text(value, 1000 if field_type == "cover_letter" else 300)
                        if input_type == "radio":
                            self._select_radio_option(radio_elements, value or "Yes")
                        else:
                            self.fill_form_field(input_elem, value, input_type)
                    else:
                        pending_questions.append({
                            "question": question,
                            "input_type": input_type,
                            "elem": input_elem,
                            "radio_elems": radio_elements,
                            "field_type": field_type
                        })
                except StaleElementReferenceException:
                    logger.debug("Stale element in async processing, skipping")
                    continue

            # Batch answer remaining questions
            if pending_questions and self.form_generator:
                try:
                    # Build resume context
                    parts = [user_data.get("resume_summary", "")] + [
                        f"Skills: {', '.join(user_data.get('skills', [])[:10])}" if user_data.get("skills") else "",
                    ]
                    resume_context = "\n".join(p for p in parts if p)

                    questions = [pq["question"] for pq in pending_questions]
                    answers_map = await self.form_generator.batch_answer_questions(
                        questions=questions,
                        resume_context=resume_context,
                        job_title=job_data.get("title", ""),
                        job_company=job_data.get("company", "")
                    )

                    # Fill using answers
                    for idx, pq in enumerate(pending_questions, start=1):
                        try:
                            ans = answers_map.get(str(idx), "")
                            ans = self._sanitize_text(ans, 300)
                            if pq["input_type"] == "radio":
                                self._select_radio_option(pq["radio_elems"], ans or "Yes")
                            else:
                                if pq["elem"]:
                                    self.fill_form_field(pq["elem"], ans, pq["input_type"])
                        except StaleElementReferenceException:
                            logger.debug("Stale element when filling batch answer, skipping")
                            continue
                except Exception as e:
                    logger.warning(f"Batch answering failed: {e}")

            return True

        except Exception as e:
            logger.error(f"Error processing form page: {e}")
            return False
    
    def _process_form_group(
        self,
        group,
        user_data: Dict[str, Any],
        job_data: Dict[str, Any],
        context: Any
    ) -> None:
        """Process a single form group/field"""
        try:
            # Get label text
            label = ""
            try:
                label_elem = group.find_element(By.CSS_SELECTOR, "label, legend, span.t-bold")
                label = label_elem.text.strip()
            except (NoSuchElementException, StaleElementReferenceException):
                pass
            
            if not label:
                return
            
            logger.debug(f"Processing field: {label}")
            
            # Detect field type from label
            from .form_answer_generator import detect_field_type
            field_type = detect_field_type(label)
            
            # Find input element
            input_elem = None
            input_type = "text"
            radio_elements = []
            
            try:
                input_elem = group.find_element(By.CSS_SELECTOR, 
                    "input[type='text'], input[type='email'], input[type='tel'], input[type='number'], input[type='url']")
            except (NoSuchElementException, StaleElementReferenceException):
                pass
            
            if not input_elem:
                try:
                    input_elem = group.find_element(By.CSS_SELECTOR, "textarea")
                    input_type = "textarea"
                except (NoSuchElementException, StaleElementReferenceException):
                    pass
            
            if not input_elem:
                try:
                    input_elem = group.find_element(By.CSS_SELECTOR, "select")
                    input_type = "dropdown"
                except (NoSuchElementException, StaleElementReferenceException):
                    pass
            
            if not input_elem:
                try:
                    input_elem = group.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                    input_type = "checkbox"
                except (NoSuchElementException, StaleElementReferenceException):
                    pass
            
            if not input_elem:
                try:
                    input_elem = group.find_element(By.CSS_SELECTOR, "input[type='file']")
                    input_type = "file"
                except (NoSuchElementException, StaleElementReferenceException):
                    pass

            if not input_elem:
                try:
                    radio_elements = group.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                    if radio_elements:
                        input_elem = radio_elements[0]
                        input_type = "radio"
                except (NoSuchElementException, StaleElementReferenceException):
                    pass
            
            if not input_elem:
                return
            
            # Get value based on field type
            value = self._get_field_value(field_type, user_data, job_data, context, label)
            if input_type == "file" and not value and self.temp_resume_path:
                value = self.temp_resume_path
            
            if input_type == "radio":
                self._select_radio_option(radio_elements, value or "Yes")
                return
            
            if value:
                self.fill_form_field(input_elem, value, input_type)
        
        except StaleElementReferenceException:
            logger.debug("Stale element in _process_form_group")
        except Exception as e:
            logger.debug(f"Error processing form group: {e}")
    
    def _get_field_value(
        self,
        field_type: Optional[str],
        user_data: Dict[str, Any],
        job_data: Dict[str, Any],
        context: Any,
        label: str
    ) -> str:
        """Get appropriate value for a field"""
        
        # Direct mappings
        if field_type == "name":
            return user_data.get("full_name", "")
        elif field_type == "email":
            return user_data.get("email", "")
        elif field_type == "phone":
            return user_data.get("phone", user_data.get("resume_parsed_data", {}).get("contact", {}).get("phone", ""))
        elif field_type == "linkedin":
            return user_data.get("linkedin_url", "")
        elif field_type == "years_experience":
            total = sum([
                user_data.get("exp_years_internship", 0) or 0,
                user_data.get("exp_years_entry_level", 0) or 0,
                user_data.get("exp_years_associate", 0) or 0,
                user_data.get("exp_years_mid_senior_level", 0) or 0,
                user_data.get("exp_years_director", 0) or 0,
                user_data.get("exp_years_executive", 0) or 0,
            ])
            return str(max(total, 2))
        elif field_type == "current_title":
            resume = user_data.get("resume_parsed_data", {})
            exp = resume.get("experience", [])
            return exp[0].get("title", "") if exp else user_data.get("target_job_title", "")
        elif field_type == "current_company":
            resume = user_data.get("resume_parsed_data", {})
            exp = resume.get("experience", [])
            return exp[0].get("company", "") if exp else ""
        elif field_type == "salary":
            return "Open to discussion based on total compensation"
        elif field_type == "sponsorship":
            return "Yes"  # Authorized to work
        elif field_type == "start_date":
            return "Available within 2 weeks"
        elif field_type == "relocation":
            return "Yes"
        
        # AI-generated fields
        elif field_type in ["cover_letter", "summary", "why_interested", "headline"]:
            if field_type == "cover_letter" and context:
                return user_data.get("generated_cover_letter", "I am excited to apply for this position...")
            elif field_type == "summary":
                return user_data.get("resume_summary", "Experienced professional seeking new opportunities...")
            elif field_type == "headline":
                return user_data.get("generated_headline", "Experienced Professional")
            else:
                return "I am interested in this opportunity because it aligns with my skills and career goals."
        
        # Unknown field - return empty
        return ""
    
    def click_next_or_submit(self) -> Tuple[str, bool]:
        """
        Click Next or Submit button with multiple fallback strategies.
        
        PRIORITY 1: Submit buttons (final submission)
        PRIORITY 2: Next/Continue buttons (go to next page)
        
        Returns:
            Tuple of (action_taken, success)
            action_taken: 'next', 'submit', or 'error'
        """
        if not self.driver:
            return ("error", False)
        
        try:
            # Scroll to bottom of modal/page to reveal footer buttons
            self._scroll_modal_to_bottom()
            
            # ============ PRIORITY 1: Find SUBMIT button (final submission) ============
            submit_selectors = [
                "//button[contains(@aria-label, 'Submit application')]",
                "//button[contains(@aria-label, 'Submit your application')]",
                "//button[contains(., 'Submit application')]",
                "//button[contains(., 'Submit') and not(contains(., 'Cancel'))]",
                "//button[@type='submit' and not(contains(., 'Cancel'))]",
                "//div[contains(@class,'artdeco-modal')]//footer//button[contains(@class,'artdeco-button--primary')]",
            ]
            
            for selector in submit_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for button in buttons:
                        try:
                            if button.is_displayed() and button.is_enabled():
                                logger.info(f"Found SUBMIT button: '{button.text}'")
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
                                time.sleep(1)
                                self._human_click(button)
                                time.sleep(2)
                                logger.info("✓ Clicked SUBMIT button")
                                return ("submit", True)
                        except ElementClickInterceptedException:
                            try:
                                self.driver.execute_script("arguments[0].click();", button)
                                time.sleep(2)
                                logger.info("✓ Clicked SUBMIT button (JS)")
                                return ("submit", True)
                            except Exception:
                                continue
                        except Exception as e:
                            logger.debug(f"Could not click submit: {e}")
                            continue
                except Exception as e:
                    logger.debug(f"Error finding submit: {e}")
                    continue
            
            # ============ PRIORITY 2: Find NEXT/CONTINUE button (go to next page) ============
            next_selectors = [
                "//button[contains(@aria-label, 'Continue')]",
                "//button[contains(@aria-label, 'Next')]",
                "//button[contains(., 'Next') and not(contains(., 'Cancel'))]",
                "//button[contains(., 'Continue') and not(contains(., 'Cancel'))]",
                "//button[contains(., 'Review')]",
                "//button[@type='submit']",
                "//div[@role='dialog']//button[@type='button' and not(contains(., 'Cancel')) and contains(@class, 'artdeco-button')]",
                "//div[contains(@class,'artdeco-modal')]//footer//button[contains(@class,'artdeco-button--primary') and not(contains(., 'Cancel'))]",
            ]
            
            for selector in next_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for button in buttons:
                        try:
                            button_text = (button.text or "").lower()
                            # Skip invalid buttons
                            if any(skip in button_text for skip in ['cancel', 'back', 'skip', 'close']):
                                continue
                            
                            if button.is_displayed() and button.is_enabled():
                                logger.info(f"Found NEXT button: '{button.text}'")
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
                                time.sleep(1)
                                try:
                                    self._human_click(button)
                                    time.sleep(2)
                                    logger.info("✓ Clicked NEXT button")
                                    return ("next", True)
                                except Exception as click_err:
                                    logger.debug(f"Human click failed, attempting JS click: {click_err}")
                                    try:
                                        self.driver.execute_script("arguments[0].click();", button)
                                        time.sleep(2)
                                        logger.info("✓ Clicked NEXT button (JS)")
                                        return ("next", True)
                                    except Exception as js_err:
                                        logger.debug(f"JS click also failed: {js_err}")
                                        continue
                        except ElementClickInterceptedException:
                            try:
                                self.driver.execute_script("arguments[0].click();", button)
                                time.sleep(2)
                                logger.info("✓ Clicked NEXT button (JS)")
                                return ("next", True)
                            except Exception:
                                continue
                        except Exception as e:
                            logger.debug(f"Could not click next: {e}")
                            continue
                except Exception as e:
                    logger.debug(f"Error finding next: {e}")
                    continue

            # Retry once more after forcing another scroll
            self._scroll_modal_to_bottom()
            time.sleep(0.5)
            for selector in next_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for button in buttons:
                        try:
                            button_text = (button.text or "").lower()
                            if any(skip in button_text for skip in ['cancel', 'back', 'skip', 'close']):
                                continue
                            if button.is_displayed() and button.is_enabled():
                                logger.info(f"Retry: Found NEXT button: '{button.text}'")
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
                                time.sleep(0.5)
                                try:
                                    self._human_click(button)
                                    time.sleep(2)
                                    logger.info("✓ Clicked NEXT button on retry")
                                    return ("next", True)
                                except Exception:
                                    try:
                                        self.driver.execute_script("arguments[0].click();", button)
                                        time.sleep(2)
                                        logger.info("✓ Clicked NEXT button (JS) on retry")
                                        return ("next", True)
                                    except Exception:
                                        continue
                        except Exception as e:
                            logger.debug(f"Retry could not click next: {e}")
                            continue
                except Exception:
                    continue
            
            logger.warning("Could not find any clickable Submit or Next buttons")
            return ("error", False)
        
        except Exception as e:
            logger.error(f"Error in click_next_or_submit: {e}")
            return ("error", False)
    
    def verify_application_submitted(self) -> bool:
        """
        Verify that application was submitted successfully.
        
        Checks multiple indicators:
        1. Success page text
        2. Easy Apply button no longer clickable
        3. Modal dialog closed
        4. Page redirection
        """
        if not self.driver:
            return False
        
        try:
            # Give the page time to fully process submission
            time.sleep(3)
            
            # Get current state
            page_text = self.driver.page_source.lower()
            current_url = self.driver.current_url.lower()
            
            logger.info(f"Verifying submission - URL: {current_url}")
            
            # ============ CHECK 1: Look for explicit success messages ============
            success_indicators = [
                "application submitted",
                "your application was sent",
                "application sent",
                "successfully applied",
                "application complete",
                "application received",
                "you've been added",
                "thank you for applying",
                "submitted an application",
                "sent you an application",
            ]
            
            for indicator in success_indicators:
                if indicator in page_text:
                    logger.info(f"✓ Found success indicator: '{indicator}'")
                    return True
            
            # ============ CHECK 2: Is the modal/dialog still open? ============
            try:
                modal = self.driver.find_element(By.CSS_SELECTOR, "[role='dialog'], .artdeco-modal")
                modal_visible = modal.is_displayed()
                
                if not modal_visible:
                    logger.info("✓ Modal closed after submission")
                    return True
            except NoSuchElementException:
                logger.info("✓ Modal not found - likely closed/submitted")
                return True
            
            # ============ CHECK 3: Easy Apply button state ============
            try:
                easy_apply_button = self.driver.find_element(
                    By.XPATH, 
                    "//button[contains(@class, 'jobs-apply-button')] | //button[contains(., 'Easy Apply')]"
                )
                
                if not easy_apply_button.is_displayed():
                    logger.info("✓ Easy Apply button hidden - application likely submitted")
                    return True
                
                aria_disabled = easy_apply_button.get_attribute("aria-disabled")
                if aria_disabled == "true":
                    logger.info("✓ Easy Apply button disabled - application likely submitted")
                    return True
                
                logger.warning("✗ Easy Apply button still visible and enabled")
                return False
                
            except NoSuchElementException:
                logger.info("✓ Easy Apply button not found - likely submitted")
                return True
            
        except Exception as e:
            logger.error(f"Error verifying submission: {e}")
            return False
    
    async def apply_to_job(
        self,
        job_url: str,
        user_data: Dict[str, Any],
        job_data: Dict[str, Any],
        max_pages: int = 20
    ) -> ApplicationResult:
        """
        Complete Easy Apply process for a single job.
        
        Args:
            job_url: LinkedIn job URL
            user_data: User profile data dictionary
            job_data: Job listing data dictionary
            max_pages: Maximum form pages to process
            
        Returns:
            ApplicationResult with success status and message
        """
        job_id = job_data.get("external_id", "unknown")
        
        try:
            # Navigate to job
            if not self.navigate_to_job(job_url):
                return ApplicationResult(
                    success=False,
                    job_id=job_id,
                    message="Failed to navigate to job page",
                    error="Navigation failed"
                )
            
            # Click Easy Apply
            if not self.click_easy_apply():
                return ApplicationResult(
                    success=False,
                    job_id=job_id,
                    message="Easy Apply button not found",
                    error="No Easy Apply"
                )

            # Wait for the Easy Apply modal to appear
            try:
                if SELENIUM_AVAILABLE:
                    wait = WebDriverWait(self.driver, 10)
                    wait.until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "[role='dialog'], .artdeco-modal")
                        )
                    )
                    time.sleep(0.5)
            except TimeoutException:
                logger.debug("Easy Apply modal did not appear within timeout; continuing anyway")
            
            # Process form pages
            for page in range(max_pages):
                logger.info(f"Processing form page {page + 1}")
                
                # Fill current page with on-the-spot LLM answers for unknown questions
                await self.process_form_page_async(user_data, job_data)
                
                # Give form time to process
                time.sleep(1)
                
                # Click next or submit
                action, success = self.click_next_or_submit()
                
                if not success:
                    # If on last page, verify submission before failing
                    if page >= max_pages - 1:
                        logger.info("On last page and button click failed, attempting verification...")
                        time.sleep(2)
                        if self.verify_application_submitted():
                            logger.info("Application was submitted despite button click failure")
                            return ApplicationResult(
                                success=True,
                                job_id=job_id,
                                message="Application submitted successfully"
                            )
                    
                    return ApplicationResult(
                        success=False,
                        job_id=job_id,
                        message=f"Failed at form page {page + 1}",
                        error="Button click failed"
                    )
                
                if action == "submit":
                    break
            
            # Verify submission
            if self.verify_application_submitted():
                return ApplicationResult(
                    success=True,
                    job_id=job_id,
                    message="Application submitted successfully"
                )
            else:
                return ApplicationResult(
                    success=False,
                    job_id=job_id,
                    message="Submission verification failed",
                    error="Could not verify"
                )
        
        except Exception as e:
            logger.error(f"Error applying to job {job_id}: {e}")
            return ApplicationResult(
                success=False,
                job_id=job_id,
                message="Application failed with error",
                error=str(e)
            )
    
    def cleanup(self) -> None:
        """Cleanup resources"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        
        if self.temp_resume_path and os.path.exists(self.temp_resume_path):
            try:
                os.remove(self.temp_resume_path)
            except Exception:
                pass
            self.temp_resume_path = None
    
    def get_fresh_cookies(self) -> List[dict]:
        """Extract current browser cookies"""
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