"""
Human-Like Behavior Simulator for Selenium Automation
Adds realistic human behavior patterns to avoid bot detection:
- Randomized typing speed with natural pauses
- Randomized mouse movements and clicks
- Scrolling with natural acceleration/deceleration
- Visual scanning patterns
- Activity logging for auditing
"""
import time
import random
import math
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
from enum import Enum

try:
    from selenium import webdriver
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.common.exceptions import (
        TimeoutException,
        NoSuchElementException,
        WebDriverException,
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class BehaviorAction(str, Enum):
    """Types of human-like actions performed"""
    TYPING = "typing"
    MOUSE_MOVE = "mouse_move"
    MOUSE_CLICK = "mouse_click"
    SCROLL = "scroll"
    PAUSE = "pause"
    FORM_FIELD_FILL = "form_field_fill"
    KEYBOARD_SHORTCUT = "keyboard_shortcut"
    PAGE_NAVIGATION = "page_navigation"
    ELEMENT_FOCUS = "element_focus"
    DROPDOWN_SELECT = "dropdown_select"


@dataclass
class BehaviorEvent:
    """Records a single human-like behavior action"""
    timestamp: datetime
    action_type: BehaviorAction
    description: str
    duration_ms: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "action_type": self.action_type.value,
            "description": self.description,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata or {}
        }


class HumanBehaviorSimulator:
    """
    Simulates human-like behavior in Selenium automation
    
    Features:
    - Realistic typing speeds (30-100 WPM with natural variation)
    - Mouse movement with acceleration/deceleration
    - Natural scrolling patterns
    - Random pauses and hesitations
    - Comprehensive activity logging for auditing
    """

    def __init__(self, driver, activity_logger=None):
        """
        Initialize behavior simulator
        
        Args:
            driver: Selenium WebDriver instance
            activity_logger: Optional callback to log activities
        """
        self.driver = driver
        self.activity_logger = activity_logger
        self.behavior_events: List[BehaviorEvent] = []
        
        # Typing speed parameters (WPM - Words Per Minute)
        self.min_wpm = 30  # Slow typing
        self.max_wpm = 100  # Fast typing
        self.error_rate = 0.02  # 2% chance of typo (very low)
        
        # Mouse movement parameters
        self.mouse_speed_min = 100  # pixels per second (slow)
        self.mouse_speed_max = 500  # pixels per second (fast)
        
        # Scroll parameters
        self.scroll_distance_min = 200  # pixels
        self.scroll_distance_max = 600  # pixels
        self.scroll_pause_min = 0.5  # seconds
        self.scroll_pause_max = 2.0  # seconds
        
        # Pause/hesitation parameters
        self.thinking_pause_min = 0.5  # seconds
        self.thinking_pause_max = 3.0  # seconds
        self.microbreak_chance = 0.15  # 15% chance of micro break
        self.microbreak_duration = (0.2, 0.8)  # seconds

    def log_event(self, event: BehaviorEvent):
        """Log a behavior event for auditing"""
        self.behavior_events.append(event)
        
        if self.activity_logger:
            self.activity_logger(
                event_type=event.action_type.value,
                description=event.description,
                metadata=event.metadata
            )
        
        logger.debug(
            f"[{event.action_type.value.upper()}] {event.description} "
            f"({event.duration_ms:.0f}ms)" if event.duration_ms else f"({0}ms)"
        )

    def random_wpm(self) -> float:
        """Get random typing speed in WPM"""
        # Use normal distribution for more human-like variation
        wpm = random.gauss(
            (self.min_wpm + self.max_wpm) / 2,
            (self.max_wpm - self.min_wpm) / 4
        )
        # Clamp to valid range
        return max(self.min_wpm, min(self.max_wpm, wpm))

    def wpm_to_chars_per_second(self, wpm: float) -> float:
        """Convert WPM to characters per second"""
        # Average word = 5 characters + 1 space
        return (wpm * 6) / 60

    def calculate_typing_delay(self, text: str, wpm: Optional[float] = None) -> float:
        """
        Calculate realistic typing delay for text
        
        Args:
            text: Text to type
            wpm: Optional Words Per Minute (uses random if not provided)
            
        Returns:
            Total delay in seconds including natural pauses
        """
        if wpm is None:
            wpm = self.random_wpm()
        
        chars_per_second = self.wpm_to_chars_per_second(wpm)
        
        # Add natural variation per character (±30%)
        total_delay = 0
        for char in text:
            char_delay = 1.0 / chars_per_second
            # Add variation (±30%)
            variation = random.gauss(1.0, 0.3)
            total_delay += char_delay * max(0.1, variation)
        
        # Add occasional thinking pauses (every 5-10 words)
        words = len(text.split())
        if words > 5:
            pause_count = max(1, words // random.randint(5, 10))
            for _ in range(pause_count):
                total_delay += random.uniform(
                    self.thinking_pause_min,
                    self.thinking_pause_max
                )
        
        return total_delay

    def type_like_human(
        self,
        element,
        text: str,
        clear_first: bool = True,
        add_pauses: bool = True
    ) -> float:
        """
        Type text in a human-like manner with realistic speed and pauses
        
        Args:
            element: Selenium element to type in
            text: Text to type
            clear_first: Whether to clear field before typing
            add_pauses: Whether to add thinking pauses
            
        Returns:
            Total typing time in seconds
        """
        start_time = time.time()
        
        try:
            # Focus on element first
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            element.click()
            
            # Small pause after focus
            time.sleep(random.uniform(0.2, 0.5))
            
            # Clear field if requested
            if clear_first:
                element.clear()
                time.sleep(random.uniform(0.1, 0.3))
            
            # Get random WPM for this typing session
            wpm = self.random_wpm()
            chars_per_second = self.wpm_to_chars_per_second(wpm)
            
            # Type character by character with realistic delays
            for i, char in enumerate(text):
                # Occasional typos (very rare)
                if random.random() < self.error_rate:
                    wrong_char = chr(random.randint(97, 122))  # Random letter
                    element.send_keys(wrong_char)
                    time.sleep(0.2)
                    element.send_keys(Keys.BACKSPACE)
                    time.sleep(0.1)
                
                # Type character
                element.send_keys(char)
                
                # Variable delay between characters
                char_delay = (1.0 / chars_per_second) * random.gauss(1.0, 0.2)
                time.sleep(max(0.05, char_delay))
                
                # Occasional micro-breaks while typing long text
                if add_pauses and i % random.randint(10, 20) == 0 and i > 0:
                    if random.random() < self.microbreak_chance:
                        pause_duration = random.uniform(*self.microbreak_duration)
                        time.sleep(pause_duration)
            
            # Pause after typing
            time.sleep(random.uniform(0.2, 0.6))
            
            elapsed = time.time() - start_time
            
            # Log the typing action
            self.log_event(BehaviorEvent(
                timestamp=datetime.utcnow(),
                action_type=BehaviorAction.TYPING,
                description=f"Typed {len(text)} characters at {wpm:.0f} WPM",
                duration_ms=elapsed * 1000,
                metadata={
                    "text_length": len(text),
                    "wpm": round(wpm, 1),
                    "chars_per_second": round(chars_per_second, 2)
                }
            ))
            
            return elapsed
            
        except Exception as e:
            logger.error(f"Error in human-like typing: {e}")
            # Fallback to normal typing
            element.send_keys(text)
            return 0

    def move_mouse_like_human(
        self,
        source_element,
        target_element,
        click: bool = False
    ) -> float:
        """
        Move mouse from source to target element with human-like motion
        
        Args:
            source_element: Starting element
            target_element: Target element
            click: Whether to click after moving
            
        Returns:
            Total movement time in seconds
        """
        start_time = time.time()
        
        try:
            actions = ActionChains(self.driver)
            
            # Get element positions
            source_loc = source_element.location
            target_loc = target_element.location
            
            # Calculate distance
            dx = target_loc['x'] - source_loc['x']
            dy = target_loc['y'] - source_loc['y']
            distance = math.sqrt(dx**2 + dy**2)
            
            # Random movement speed (pixels per second)
            speed = random.uniform(self.mouse_speed_min, self.mouse_speed_max)
            movement_time = distance / speed
            
            # Move to target with small random deviations for natural look
            actions.move_to_element(source_element)
            
            # Simulate natural movement with curved path
            steps = max(5, int(distance / 50))  # More steps = smoother curve
            for i in range(1, steps + 1):
                # Ease-in-out function for natural acceleration
                progress = i / steps
                eased = progress ** 2 if progress < 0.5 else 1 - (1 - progress) ** 2
                
                x = source_loc['x'] + dx * eased
                y = source_loc['y'] + dy * eased
                
                # Add small random jitter for realistic movement
                x += random.uniform(-5, 5)
                y += random.uniform(-5, 5)
                
                actions.move_by_offset(
                    (x - source_loc['x']) / steps if i == 1 else 0,
                    (y - source_loc['y']) / steps if i == 1 else 0
                )
                
                time.sleep(movement_time / steps)
            
            # Move to target
            actions.move_to_element(target_element)
            
            if click:
                # Small pause before clicking
                time.sleep(random.uniform(0.1, 0.3))
                actions.click()
            
            actions.perform()
            
            elapsed = time.time() - start_time
            
            # Log the movement
            self.log_event(BehaviorEvent(
                timestamp=datetime.utcnow(),
                action_type=BehaviorAction.MOUSE_MOVE,
                description=f"Moved mouse {distance:.0f}px at {speed:.0f}px/s",
                duration_ms=elapsed * 1000,
                metadata={
                    "distance_pixels": round(distance, 1),
                    "speed_px_per_sec": round(speed, 1),
                    "click": click
                }
            ))
            
            return elapsed
            
        except Exception as e:
            logger.error(f"Error in human-like mouse movement: {e}")
            # Fallback to direct click
            if click:
                target_element.click()
            return 0

    def scroll_like_human(
        self,
        direction: str = "down",
        distance: Optional[float] = None,
        pause_after: bool = True
    ) -> float:
        """
        Scroll page with human-like behavior
        
        Args:
            direction: "up" or "down"
            distance: Distance to scroll in pixels (random if not provided)
            pause_after: Whether to pause after scrolling
            
        Returns:
            Total scroll time in seconds
        """
        start_time = time.time()
        
        try:
            if distance is None:
                distance = random.uniform(
                    self.scroll_distance_min,
                    self.scroll_distance_max
                )
            
            # Determine scroll direction
            scroll_amount = distance if direction.lower() == "down" else -distance
            
            # Simulate natural scrolling with acceleration/deceleration
            steps = random.randint(5, 10)
            for i in range(steps):
                # Ease-out function for natural deceleration
                progress = (i + 1) / steps
                eased = 1 - (1 - progress) ** 2  # Ease-out
                
                scroll_distance = scroll_amount * eased
                self.driver.execute_script(
                    f"window.scrollBy(0, {scroll_distance / steps});"
                )
                
                time.sleep(random.uniform(0.05, 0.15))
            
            elapsed = time.time() - start_time
            
            # Optional pause after scrolling to "look" at content
            if pause_after:
                pause_duration = random.uniform(
                    self.scroll_pause_min,
                    self.scroll_pause_max
                )
                time.sleep(pause_duration)
                elapsed += pause_duration
            
            # Log the scroll
            self.log_event(BehaviorEvent(
                timestamp=datetime.utcnow(),
                action_type=BehaviorAction.SCROLL,
                description=f"Scrolled {direction} {abs(distance):.0f}px",
                duration_ms=elapsed * 1000,
                metadata={
                    "direction": direction,
                    "distance_pixels": round(distance, 1),
                    "pause_after": pause_after
                }
            ))
            
            return elapsed
            
        except Exception as e:
            logger.error(f"Error in human-like scrolling: {e}")
            return 0

    def think_like_human(self, label: str = "thinking") -> float:
        """
        Add a natural thinking pause (hesitation)
        
        Args:
            label: Description of what user is thinking about
            
        Returns:
            Pause duration in seconds
        """
        duration = random.uniform(
            self.thinking_pause_min,
            self.thinking_pause_max
        )
        time.sleep(duration)
        
        # Log the pause
        self.log_event(BehaviorEvent(
            timestamp=datetime.utcnow(),
            action_type=BehaviorAction.PAUSE,
            description=f"Thinking about: {label}",
            duration_ms=duration * 1000,
            metadata={"label": label}
        ))
        
        return duration

    def click_like_human(self, element, by_double_click: bool = False) -> float:
        """
        Click element with human-like behavior
        
        Args:
            element: Element to click
            by_double_click: Whether to double-click
            
        Returns:
            Total click time in seconds
        """
        start_time = time.time()
        
        try:
            # Scroll element into view
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            
            # Small delay before click
            time.sleep(random.uniform(0.1, 0.3))
            
            # Perform click
            if by_double_click:
                ActionChains(self.driver).double_click(element).perform()
            else:
                element.click()
            
            # Small delay after click
            time.sleep(random.uniform(0.1, 0.3))
            
            elapsed = time.time() - start_time
            
            # Log the click
            self.log_event(BehaviorEvent(
                timestamp=datetime.utcnow(),
                action_type=BehaviorAction.MOUSE_CLICK,
                description=f"Clicked element {'(double-click)' if by_double_click else ''}",
                duration_ms=elapsed * 1000,
                metadata={"double_click": by_double_click}
            ))
            
            return elapsed
            
        except Exception as e:
            logger.error(f"Error in human-like click: {e}")
            return 0

    def fill_form_field_like_human(
        self,
        field_element,
        field_value: str,
        field_label: Optional[str] = None
    ) -> float:
        """
        Fill a form field in a human-like way
        
        Args:
            field_element: Form field element
            field_value: Value to fill
            field_label: Optional label for logging
            
        Returns:
            Total fill time in seconds
        """
        start_time = time.time()
        
        try:
            # Move mouse to field
            self.move_mouse_like_human(
                self.driver.find_element(By.TAG_NAME, "body"),
                field_element,
                click=True
            )
            
            # Type value
            self.type_like_human(field_element, field_value)
            
            elapsed = time.time() - start_time
            
            # Log the form fill
            self.log_event(BehaviorEvent(
                timestamp=datetime.utcnow(),
                action_type=BehaviorAction.FORM_FIELD_FILL,
                description=f"Filled form field: {field_label or 'unnamed'}",
                duration_ms=elapsed * 1000,
                metadata={
                    "field_label": field_label,
                    "value_length": len(field_value)
                }
            ))
            
            return elapsed
            
        except Exception as e:
            logger.error(f"Error in form field fill: {e}")
            # Fallback
            field_element.clear()
            field_element.send_keys(field_value)
            return 0

    def get_behavior_summary(self) -> Dict[str, Any]:
        """Get summary of all recorded behaviors"""
        if not self.behavior_events:
            return {}
        
        summary = {
            "total_events": len(self.behavior_events),
            "total_duration_seconds": sum(
                (e.duration_ms or 0) / 1000 for e in self.behavior_events
            ),
            "events_by_type": {},
            "timeline": [e.to_dict() for e in self.behavior_events]
        }
        
        # Count by action type
        for event in self.behavior_events:
            action_type = event.action_type.value
            if action_type not in summary["events_by_type"]:
                summary["events_by_type"][action_type] = 0
            summary["events_by_type"][action_type] += 1
        
        return summary

    def export_activity_log(self) -> List[Dict[str, Any]]:
        """Export behavior events as activity log entries"""
        return [e.to_dict() for e in self.behavior_events]
