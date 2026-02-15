"""
Pro Form Filler
Production-grade form filling with DOM-first detection, vision fallback,
batched LLM calls, and cost optimization.

Designed for 1k+ applications/day with $0.01-0.02 cost per page.
"""
import asyncio
import time
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from loguru import logger

try:
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from .dom_field_extractor import DOMFieldExtractor, FormField, FieldType, FormSchema
from .vision_form_extractor import VisionFormExtractor, take_cropped_screenshot
from .resume_context_manager import ResumeContextManager
from .form_answer_generator import FormAnswerGenerator
from .form_schema_cache import FormSchemaCache, get_form_cache
from .cost_tracker import CostTracker, get_cost_tracker


@dataclass
class FieldAnswer:
    """Answer for a form field with confidence"""
    question: str
    answer: str
    confidence: float  # 0.0 - 1.0
    source: str  # "quick", "batch", "default"
    field_type: FieldType = FieldType.TEXT


@dataclass
class PageFillResult:
    """Result of filling a single form page"""
    fields_found: int
    fields_filled: int
    fields_skipped: int
    source: str  # "dom", "vision", "cache"
    cost: float
    has_next: bool
    has_submit: bool


class ProFormFiller:
    """
    Production-grade form filler with cost optimization.
    
    Flow:
    1. Try DOM extraction (free)
    2. Check schema cache
    3. Vision fallback if needed
    4. Quick answers for common questions (no LLM)
    5. Batch remaining questions in single LLM call
    6. Fill fields with confidence scoring
    """
    
    def __init__(
        self,
        driver: WebDriver,
        resume_parsed: Dict[str, Any],
        job_data: Dict[str, Any],
        user_data: Dict[str, Any]
    ):
        """
        Initialize pro form filler.
        
        Args:
            driver: Selenium WebDriver
            resume_parsed: Parsed resume data
            job_data: Job details (title, company, description)
            user_data: User data (name, email, phone, etc.)
        """
        self.driver = driver
        self.job_data = job_data
        self.user_data = user_data
        
        # Initialize components
        self.dom_extractor = DOMFieldExtractor()
        self.vision_extractor = VisionFormExtractor()
        self.resume_manager = ResumeContextManager(resume_parsed)
        self.answer_generator = FormAnswerGenerator()
        self.schema_cache = get_form_cache()
        self.cost_tracker = get_cost_tracker()
        
        # Track page hashes to detect changes
        self._last_page_hash: Optional[str] = None
    
    async def fill_current_page(self) -> PageFillResult:
        """
        Fill the current form page using pro approach.
        
        Returns:
            PageFillResult with fill statistics
        """
        start_time = time.time()
        
        # Step 1: Try DOM extraction (free)
        fields, source = await self._extract_fields()
        
        if not fields:
            logger.warning("No fields found on page")
            return PageFillResult(
                fields_found=0,
                fields_filled=0,
                fields_skipped=0,
                source="none",
                cost=0.0,
                has_next=False,
                has_submit=False
            )
        
        # Step 2: Generate answers
        answers = await self._generate_answers(fields)
        
        # Step 3: Fill fields
        filled, skipped = self._fill_fields(fields, answers)
        
        # Get button status
        schema = self.dom_extractor.get_form_schema(self.driver)
        
        # Calculate cost
        page_cost = self.cost_tracker.current_job_cost
        
        duration = time.time() - start_time
        logger.info(
            f"Page filled: {filled}/{len(fields)} fields | "
            f"Source: {source} | Cost: ${page_cost:.4f} | "
            f"Time: {duration:.1f}s"
        )
        
        return PageFillResult(
            fields_found=len(fields),
            fields_filled=filled,
            fields_skipped=skipped,
            source=source,
            cost=page_cost,
            has_next=schema.has_next_button,
            has_submit=schema.has_submit_button
        )
    
    async def _extract_fields(self) -> Tuple[List[FormField], str]:
        """
        Extract fields using DOM-first, vision-fallback approach.
        
        Returns:
            Tuple of (fields list, source string)
        """
        # Step 1: Get page hash
        page_hash = self.dom_extractor.get_page_hash(self.driver)
        
        # Step 2: Check if same page (no re-extraction needed)
        if page_hash == self._last_page_hash:
            cached = self.schema_cache.get_schema(page_hash)
            if cached:
                logger.debug(f"Using cached schema (same page)")
                return cached.fields, "cache"
        
        self._last_page_hash = page_hash
        
        # Step 3: Check cache for this hash
        cached = self.schema_cache.get_schema(page_hash)
        if cached:
            logger.debug(f"Cache HIT for page hash {page_hash[:8]}")
            return cached.fields, "cache"
        
        # Step 4: Try DOM extraction (free)
        fields = self.dom_extractor.extract_fields(self.driver)
        
        if fields:
            # Cache the result
            schema = self.dom_extractor.get_form_schema(self.driver)
            self.schema_cache.cache_schema(
                page_hash=page_hash,
                fields=fields,
                has_next=schema.has_next_button,
                has_submit=schema.has_submit_button,
                source="dom"
            )
            return fields, "dom"
        
        # Step 5: Vision fallback (costs tokens)
        logger.info("DOM extraction failed, using vision fallback")
        
        screenshot = take_cropped_screenshot(self.driver)
        vision_result = await self.vision_extractor.extract_from_screenshot(screenshot)
        
        # Log vision cost
        self.cost_tracker.log_call(
            model="gpt-4o-mini",
            input_tokens=vision_result.tokens_used,
            output_tokens=50,
            purpose="vision"
        )
        
        if vision_result.fields:
            # Convert vision fields to FormField
            fields = [
                FormField(
                    label_text=vf.label,
                    field_type=FieldType(vf.field_type) if vf.field_type in [e.value for e in FieldType] else FieldType.TEXT,
                    is_required=vf.required,
                    options=vf.options or [],
                    needs_answer=True
                )
                for vf in vision_result.fields
            ]
            
            # Cache vision result
            self.schema_cache.cache_schema(
                page_hash=page_hash,
                fields=fields,
                has_next=vision_result.has_next_button,
                has_submit=vision_result.has_submit_button,
                source="vision"
            )
            
            return fields, "vision"
        
        return [], "none"
    
    async def _generate_answers(self, fields: List[FormField]) -> Dict[str, FieldAnswer]:
        """
        Generate answers for fields using quick + batch approach.
        
        Returns:
            Dict mapping label to FieldAnswer
        """
        answers: Dict[str, FieldAnswer] = {}
        questions_for_llm: List[Tuple[str, FormField]] = []
        
        # Step 1: Try quick answers first (no LLM cost)
        for field in fields:
            if not field.needs_answer:
                continue
            
            label = field.label_text
            
            # Check for direct user data
            quick_answer = self._get_quick_answer(label)
            if quick_answer:
                answers[label] = FieldAnswer(
                    question=label,
                    answer=quick_answer,
                    confidence=0.95,
                    source="quick",
                    field_type=field.field_type
                )
                continue
            
            # Check resume manager for quick answers
            resume_answer = self.resume_manager.answer_quick(label)
            if resume_answer:
                answers[label] = FieldAnswer(
                    question=label,
                    answer=resume_answer,
                    confidence=0.90,
                    source="quick",
                    field_type=field.field_type
                )
                continue
            
            # Need LLM for this question
            questions_for_llm.append((label, field))
        
        # Step 2: Batch LLM call for remaining questions
        if questions_for_llm:
            question_labels = [q[0] for q in questions_for_llm]
            
            # Get relevant resume context
            context = self.resume_manager.get_compressed_context(max_tokens=400)
            
            # Build user preferences dict for salary handling
            user_prefs = {
                "current_salary": self.user_data.get("current_salary"),
                "desired_salary": self.user_data.get("desired_salary"),
                "location": self.user_data.get("location"),
                "gender": self.user_data.get("gender"),
            }
            
            # Single batch call
            batch_answers = await self.answer_generator.batch_answer_questions(
                questions=question_labels,
                resume_context=context,
                job_title=self.job_data.get("title", ""),
                job_company=self.job_data.get("company", ""),
                user_preferences=user_prefs
            )
            
            # Log batch cost (estimate)
            input_tokens = len(context.split()) + sum(len(q.split()) for q in question_labels)
            output_tokens = sum(len(str(a).split()) for a in batch_answers.values())
            self.cost_tracker.log_call(
                model="gpt-4o-mini",
                input_tokens=input_tokens * 2,  # Rough token estimate
                output_tokens=output_tokens * 2,
                purpose="batch"
            )
            
            # Map answers back to fields
            for i, (label, field) in enumerate(questions_for_llm):
                answer_text = batch_answers.get(str(i + 1), "")
                if answer_text:
                    answers[label] = FieldAnswer(
                        question=label,
                        answer=answer_text,
                        confidence=0.75,
                        source="batch",
                        field_type=field.field_type
                    )
        
        logger.info(
            f"Generated {len(answers)} answers: "
            f"{sum(1 for a in answers.values() if a.source == 'quick')} quick, "
            f"{sum(1 for a in answers.values() if a.source == 'batch')} batch"
        )
        
        return answers
    
    def _get_quick_answer(self, label: str) -> Optional[str]:
        """Get quick answer from user data without LLM"""
        label_lower = label.lower()
        
        # Name
        if any(w in label_lower for w in ["full name", "your name", "name"]):
            return self.user_data.get("full_name", "")
        
        # Email
        if "email" in label_lower:
            return self.user_data.get("email", "")
        
        # Phone
        if any(w in label_lower for w in ["phone", "mobile", "contact"]):
            return self.user_data.get("phone", "")
        
        # LinkedIn
        if "linkedin" in label_lower:
            return self.user_data.get("linkedin_url", "")
        
        # Location - use user preferences, not hardcoded
        if any(w in label_lower for w in ["location", "city", "where", "based"]):
            # Try to get from preferences first
            location = self.user_data.get("location", "")
            if location:
                return location
            # Fallback to contact location
            return self.user_data.get("contact_location", "")
        
        # Current Salary - use preference
        if any(w in label_lower for w in ["current salary", "current compensation", "what is your current"]):
            current_salary = self.user_data.get("current_salary")
            if current_salary:
                return str(current_salary)
            return None
        
        # Desired/Expected Salary - use preference
        if any(w in label_lower for w in ["desired salary", "expected salary", "salary expectation", "what salary"]):
            desired_salary = self.user_data.get("desired_salary")
            if desired_salary:
                return str(desired_salary)
            return None
        
        # Gender
        if any(w in label_lower for w in ["gender", "sex", "male", "female"]):
            gender = self.user_data.get("gender")
            if gender:
                return gender
            return None
        
        return None
    
    def _fill_fields(
        self,
        fields: List[FormField],
        answers: Dict[str, FieldAnswer]
    ) -> Tuple[int, int]:
        """
        Fill form fields with generated answers.
        
        Returns:
            Tuple of (filled_count, skipped_count)
        """
        filled = 0
        skipped = 0
        
        for field in fields:
            if not field.needs_answer:
                continue
            
            answer = answers.get(field.label_text)
            
            if not answer:
                logger.debug(f"No answer for: {field.label_text}")
                skipped += 1
                continue
            
            # Skip low-confidence non-required fields
            if answer.confidence < 0.5 and not field.is_required:
                logger.debug(f"Skipping low-confidence field: {field.label_text}")
                skipped += 1
                continue
            
            # Fill the field
            success = self._fill_single_field(field, answer.answer)
            
            if success:
                filled += 1
            else:
                skipped += 1
        
        return filled, skipped
    
    def _fill_single_field(self, field: FormField, value: str) -> bool:
        """Fill a single form field"""
        if not SELENIUM_AVAILABLE:
            return False
        
        try:
            # Find element
            element = None
            
            if field.element_id:
                try:
                    element = self.driver.find_element(By.ID, field.element_id)
                except:
                    pass
            
            if not element and field.element_xpath:
                try:
                    element = self.driver.find_element(By.XPATH, field.element_xpath)
                except:
                    pass
            
            # Fallback: find by label text
            if not element:
                try:
                    # Find label, then associated input
                    labels = self.driver.find_elements(By.TAG_NAME, "label")
                    for label in labels:
                        if field.label_text.lower() in label.text.lower():
                            for_id = label.get_attribute("for")
                            if for_id:
                                element = self.driver.find_element(By.ID, for_id)
                                break
                except:
                    pass
            
            if not element:
                logger.warning(f"Could not find element for: {field.label_text}")
                return False
            
            # Fill based on field type
            if field.field_type in [FieldType.TEXT, FieldType.TEXTAREA]:
                element.clear()
                element.send_keys(value)
                return True
            
            elif field.field_type == FieldType.SELECT:
                from selenium.webdriver.support.ui import Select
                select = Select(element)
                # Try to match option
                for option in select.options:
                    if value.lower() in option.text.lower():
                        select.select_by_visible_text(option.text)
                        return True
                # Select first non-empty option as fallback
                if len(select.options) > 1:
                    select.select_by_index(1)
                    return True
            
            elif field.field_type == FieldType.CHECKBOX:
                if not element.is_selected() and value.lower() in ["yes", "true", "checked"]:
                    element.click()
                return True
            
            elif field.field_type == FieldType.RADIO:
                # Find matching radio button
                radios = self.driver.find_elements(
                    By.XPATH,
                    f"//input[@type='radio' and contains(following-sibling::*/text(), '{value}')]"
                )
                if radios:
                    radios[0].click()
                    return True
            
            return False
        
        except Exception as e:
            logger.warning(f"Error filling field '{field.label_text}': {e}")
            return False
    
    def click_next_or_submit(self) -> Tuple[str, bool]:
        """
        Click the next or submit button.
        
        Returns:
            Tuple of (action, success) where action is "next", "submit", or "none"
        """
        if not SELENIUM_AVAILABLE:
            return "none", False
        
        buttons = self.schema_cache.get_button_locations("linkedin.com")
        
        # Try submit first (more final)
        for selector in buttons.submit_selectors:
            try:
                btn = self.driver.find_element(By.XPATH, selector)
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    self.schema_cache.update_button_success("linkedin.com", "submit", selector)
                    time.sleep(1)
                    return "submit", True
            except:
                continue
        
        # Try next
        for selector in buttons.next_selectors:
            try:
                btn = self.driver.find_element(By.XPATH, selector)
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    self.schema_cache.update_button_success("linkedin.com", "next", selector)
                    time.sleep(1)
                    return "next", True
            except:
                continue
        
        return "none", False


async def apply_with_pro_filler(
    driver: WebDriver,
    job_url: str,
    user_data: Dict[str, Any],
    job_data: Dict[str, Any],
    max_pages: int = 10
) -> Tuple[bool, str]:
    """
    Apply to a job using the pro form filler.
    
    Args:
        driver: Selenium WebDriver
        job_url: URL of the job posting
        user_data: User data including resume
        job_data: Job details
        max_pages: Maximum form pages to process
        
    Returns:
        Tuple of (success, message)
    """
    cost_tracker = get_cost_tracker()
    cost_tracker.start_job(
        job_id=job_data.get("external_id", "unknown"),
        job_title=job_data.get("title", ""),
        company=job_data.get("company", "")
    )
    
    try:
        # Navigate to job
        driver.get(job_url)
        time.sleep(2)
        
        # Click Easy Apply
        try:
            easy_apply = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Easy Apply')]"))
            )
            easy_apply.click()
            time.sleep(2)
        except Exception as e:
            cost_tracker.finish_job(success=False)
            return False, f"Easy Apply button not found: {e}"
        
        # Initialize form filler
        resume_parsed = user_data.get("resume_parsed_data", {})
        filler = ProFormFiller(driver, resume_parsed, job_data, user_data)
        
        # Process form pages
        for page in range(max_pages):
            logger.info(f"Processing form page {page + 1}")
            
            result = await filler.fill_current_page()
            
            if result.fields_found == 0:
                # Might be confirmation page or error
                time.sleep(1)
            
            # Click next or submit
            action, success = filler.click_next_or_submit()
            
            if action == "submit":
                cost_tracker.finish_job(success=True)
                return True, "Application submitted successfully"
            
            if action == "none":
                # Check if we're on confirmation page
                page_text = driver.page_source.lower()
                if any(w in page_text for w in ["submitted", "thank you", "received"]):
                    cost_tracker.finish_job(success=True)
                    return True, "Application submitted successfully"
                
                cost_tracker.finish_job(success=False)
                return False, "Could not find next/submit button"
            
            time.sleep(2)  # Wait for next page
        
        cost_tracker.finish_job(success=False)
        return False, f"Exceeded max pages ({max_pages})"
    
    except Exception as e:
        logger.error(f"Pro filler error: {e}")
        cost_tracker.finish_job(success=False)
        return False, str(e)
