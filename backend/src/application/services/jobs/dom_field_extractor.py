"""
DOM Field Extractor
Extract form fields directly from DOM - fast, free, no API cost
"""
import hashlib
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class FieldType(str, Enum):
    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    FILE = "file"
    UNKNOWN = "unknown"


@dataclass
class FormField:
    """Represents a form field extracted from DOM"""
    label_text: str
    field_type: FieldType
    element_id: Optional[str] = None
    element_xpath: Optional[str] = None
    is_required: bool = False
    current_value: str = ""
    options: List[str] = field(default_factory=list)  # For select/radio
    needs_answer: bool = True  # False if already filled or auto-fillable
    
    def to_dict(self) -> dict:
        return {
            "label": self.label_text,
            "type": self.field_type.value,
            "required": self.is_required,
            "id": self.element_id,
            "needs_answer": self.needs_answer
        }


@dataclass
class FormSchema:
    """Schema of a form page"""
    fields: List[FormField]
    page_hash: str
    has_next_button: bool = False
    has_submit_button: bool = False


class DOMFieldExtractor:
    """
    Extract form fields from DOM - fast, free, no API cost.
    
    LinkedIn Easy Apply form selectors are hardcoded for reliability.
    Falls back to generic selectors for other platforms.
    """
    
    # LinkedIn-specific selectors (most reliable)
    LINKEDIN_FORM_SELECTORS = [
        ".jobs-easy-apply-form-section__grouping",
        ".fb-dash-form-element",
        "[data-test-form-builder-radio-button-form-component]",
        "[data-test-text-entity-list-form-component]",
        ".jobs-easy-apply-form-element",
    ]
    
    # Generic form field selectors (fallback)
    GENERIC_FIELD_SELECTORS = [
        ".form-group",
        ".field-group",
        "[class*='form-field']",
        "[class*='input-group']",
    ]
    
    # Input element selectors
    INPUT_SELECTORS = {
        FieldType.TEXT: ["input[type='text']", "input[type='email']", "input[type='tel']", "input[type='number']", "input:not([type])"],
        FieldType.TEXTAREA: ["textarea"],
        FieldType.SELECT: ["select"],
        FieldType.CHECKBOX: ["input[type='checkbox']"],
        FieldType.RADIO: ["input[type='radio']"],
        FieldType.FILE: ["input[type='file']"],
    }
    
    # Label selectors (priority order)
    LABEL_SELECTORS = [
        "label",
        "legend",
        ".fb-dash-form-element__label",
        "[class*='label']",
        "span.t-bold",
        ".artdeco-text-input--label",
    ]
    
    def __init__(self):
        self._field_cache: Dict[str, FormField] = {}
    
    def extract_fields(self, driver: WebDriver) -> List[FormField]:
        """
        Extract all form fields from current page.
        
        Returns:
            List of FormField objects with element references
        """
        if not SELENIUM_AVAILABLE:
            logger.warning("Selenium not available")
            return []
        
        fields = []
        
        # Try LinkedIn selectors first
        form_groups = self._find_form_groups(driver, self.LINKEDIN_FORM_SELECTORS)
        
        # Fallback to generic selectors
        if not form_groups:
            form_groups = self._find_form_groups(driver, self.GENERIC_FIELD_SELECTORS)
        
        for group in form_groups:
            try:
                field = self._extract_field_from_group(group)
                if field and field.label_text:
                    fields.append(field)
            except Exception as e:
                logger.debug(f"Error extracting field: {e}")
                continue
        
        # Deduplicate by label
        seen_labels = set()
        unique_fields = []
        for f in fields:
            if f.label_text.lower() not in seen_labels:
                seen_labels.add(f.label_text.lower())
                unique_fields.append(f)
        
        logger.info(f"DOM extracted {len(unique_fields)} fields")
        return unique_fields
    
    def _find_form_groups(self, driver: WebDriver, selectors: List[str]) -> List[WebElement]:
        """Find form groups using multiple selectors"""
        groups = []
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                groups.extend(elements)
            except Exception:
                continue
        return groups
    
    def _extract_field_from_group(self, group: WebElement) -> Optional[FormField]:
        """Extract field info from a form group element"""
        
        # Get label text
        label_text = self._extract_label(group)
        if not label_text:
            return None
        
        # Find input element and determine type
        field_type, input_elem = self._find_input_element(group)
        if not input_elem:
            return None
        
        # Get element identifier
        element_id = input_elem.get_attribute("id")
        element_xpath = None
        if not element_id:
            try:
                # Generate xpath for element
                element_xpath = self._generate_xpath(input_elem)
            except:
                pass
        
        # Check if required
        is_required = self._is_field_required(group, input_elem)
        
        # Get current value
        current_value = self._get_current_value(input_elem, field_type)
        
        # Get options for select/radio
        options = []
        if field_type == FieldType.SELECT:
            options = self._get_select_options(input_elem)
        elif field_type == FieldType.RADIO:
            options = self._get_radio_options(group)
        
        # Determine if needs answer
        needs_answer = self._needs_answer(field_type, current_value, label_text)
        
        return FormField(
            label_text=label_text.strip(),
            field_type=field_type,
            element_id=element_id,
            element_xpath=element_xpath,
            is_required=is_required,
            current_value=current_value,
            options=options,
            needs_answer=needs_answer
        )
    
    def _extract_label(self, group: WebElement) -> str:
        """Extract label text from group"""
        for selector in self.LABEL_SELECTORS:
            try:
                label = group.find_element(By.CSS_SELECTOR, selector)
                text = label.text.strip()
                if text and len(text) > 1:
                    # Clean up asterisks and extra whitespace
                    text = text.replace("*", "").strip()
                    return text
            except:
                continue
        
        # Try aria-label on input
        try:
            inputs = group.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                aria = inp.get_attribute("aria-label")
                if aria:
                    return aria.strip()
        except:
            pass
        
        return ""
    
    def _find_input_element(self, group: WebElement) -> tuple:
        """Find the input element and its type"""
        for field_type, selectors in self.INPUT_SELECTORS.items():
            for selector in selectors:
                try:
                    elem = group.find_element(By.CSS_SELECTOR, selector)
                    if elem.is_displayed():
                        return (field_type, elem)
                except:
                    continue
        return (FieldType.UNKNOWN, None)
    
    def _is_field_required(self, group: WebElement, input_elem: WebElement) -> bool:
        """Check if field is required"""
        try:
            # Check input required attribute
            if input_elem.get_attribute("required"):
                return True
            if input_elem.get_attribute("aria-required") == "true":
                return True
            
            # Check for asterisk in group
            if "*" in group.text:
                return True
            
            # Check for required class
            classes = group.get_attribute("class") or ""
            if "required" in classes.lower():
                return True
                
        except:
            pass
        return False
    
    def _get_current_value(self, input_elem: WebElement, field_type: FieldType) -> str:
        """Get current value of input"""
        try:
            if field_type == FieldType.CHECKBOX:
                return "checked" if input_elem.is_selected() else ""
            elif field_type == FieldType.SELECT:
                from selenium.webdriver.support.ui import Select
                select = Select(input_elem)
                return select.first_selected_option.text if select.first_selected_option else ""
            else:
                return input_elem.get_attribute("value") or ""
        except:
            return ""
    
    def _get_select_options(self, select_elem: WebElement) -> List[str]:
        """Get options from select element"""
        try:
            from selenium.webdriver.support.ui import Select
            select = Select(select_elem)
            return [opt.text for opt in select.options if opt.text.strip()]
        except:
            return []
    
    def _get_radio_options(self, group: WebElement) -> List[str]:
        """Get options from radio group"""
        try:
            radios = group.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            options = []
            for radio in radios:
                label = radio.find_element(By.XPATH, "./following-sibling::label | ./parent::label")
                if label:
                    options.append(label.text.strip())
            return options
        except:
            return []
    
    def _needs_answer(self, field_type: FieldType, current_value: str, label: str) -> bool:
        """Determine if field needs an answer"""
        # Already filled
        if current_value and field_type != FieldType.CHECKBOX:
            return False
        
        # File uploads handled separately
        if field_type == FieldType.FILE:
            return False
        
        # Auto-filled fields (name, email often pre-filled)
        label_lower = label.lower()
        if any(w in label_lower for w in ["upload", "attach", "resume", "cv"]):
            return False  # File upload
        
        return True
    
    def _generate_xpath(self, element: WebElement) -> str:
        """Generate xpath for element (simplified)"""
        try:
            tag = element.tag_name
            element_id = element.get_attribute("id")
            if element_id:
                return f"//*[@id='{element_id}']"
            
            name = element.get_attribute("name")
            if name:
                return f"//{tag}[@name='{name}']"
            
            placeholder = element.get_attribute("placeholder")
            if placeholder:
                return f"//{tag}[@placeholder='{placeholder}']"
            
            return f"//{tag}"
        except:
            return ""
    
    def get_page_hash(self, driver: WebDriver) -> str:
        """
        Generate hash of form structure for caching.
        
        Hash is based on field labels only, not values.
        Same form structure = same hash.
        """
        fields = self.extract_fields(driver)
        labels = sorted([f.label_text.lower() for f in fields])
        content = json.dumps(labels, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def get_form_schema(self, driver: WebDriver) -> FormSchema:
        """Get complete form schema including buttons"""
        fields = self.extract_fields(driver)
        page_hash = self.get_page_hash(driver)
        
        # Check for buttons
        has_next = self._has_button(driver, ["Next", "Continue", "Review"])
        has_submit = self._has_button(driver, ["Submit", "Apply", "Send"])
        
        return FormSchema(
            fields=fields,
            page_hash=page_hash,
            has_next_button=has_next,
            has_submit_button=has_submit
        )
    
    def _has_button(self, driver: WebDriver, texts: List[str]) -> bool:
        """Check if page has button with given text"""
        for text in texts:
            try:
                buttons = driver.find_elements(
                    By.XPATH, 
                    f"//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{text.lower()}')]"
                )
                if any(b.is_displayed() for b in buttons):
                    return True
            except:
                continue
        return False
