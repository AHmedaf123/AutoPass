from typing import Dict, Optional, Tuple
from loguru import logger
import time
import json

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.service import Service
except ImportError:
    webdriver = None
    logger.warning("Selenium not installed. Credential verification will be simulated.")


class CredentialVerifier:
    """
    Service to verify third-party credentials (LinkedIn, Indeed) 
    via immediate Selenium login attempts.
    """
    
    # Stealth User-Agent (standard Windows 10 Chrome)
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # Cookie whitelist - only these fields are persisted
    COOKIE_WHITELIST = ["name", "value", "domain", "path", "expiry", "secure", "httpOnly"]
    
    def __init__(self):
        self.headless = True
    
    def _normalize_cookies(self, raw_cookies: list) -> dict:
        """
        Normalize Selenium cookies for persistent storage.
        
        - Whitelists only safe fields
        - Forces domain to '.linkedin.com'
        - Forces expiry to now + 172800 (48h) if None
        - Returns structured payload with environment fingerprint
        
        Returns:
            dict: {"cookies": [...], "user_agent": "...", "timezone": "...", "language": "..."}
        """
        normalized = []
        now_ts = int(time.time())
        expiry_48h = now_ts + 172800  # 48 hours
        
        for cookie in raw_cookies:
            normalized_cookie = {}
            for field in self.COOKIE_WHITELIST:
                if field == "domain":
                    # Always force LinkedIn domain
                    normalized_cookie["domain"] = ".linkedin.com"
                elif field == "expiry":
                    # Force expiry if None
                    expiry = cookie.get("expiry")
                    normalized_cookie["expiry"] = expiry if expiry else expiry_48h
                else:
                    if field in cookie:
                        normalized_cookie[field] = cookie[field]
            
            # Only include if we have name and value
            if normalized_cookie.get("name") and normalized_cookie.get("value"):
                normalized.append(normalized_cookie)
        
        return {
            "cookies": normalized,
            "user_agent": self.USER_AGENT,
            "timezone": "Asia/Karachi",
            "language": "en-US"
        }
    
    def _has_valid_li_at(self, profile: dict) -> bool:
        """
        Check if profile contains valid li_at cookie.
        
        li_at is the critical authentication cookie.
        """
        if not profile or not profile.get("cookies"):
            return False
        
        now_ts = int(time.time())
        for cookie in profile["cookies"]:
            if cookie.get("name") == "li_at":
                expiry = cookie.get("expiry", 0)
                if expiry > now_ts:
                    return True
        return False
    
    def _get_driver(self):
        """Initialize Chrome driver with Stealth Mode"""
        if not webdriver:
            raise ImportError("Selenium is required for credential verification")
            
        options = webdriver.ChromeOptions()
        
        # -------------------------------------------------------------------------
        # STEALTH MODE CONFIGURATION
        # -------------------------------------------------------------------------
        
        # 1. Use new Headless mode (undetectable by most simple checks)
        if self.headless:
            options.add_argument("--headless=new")
            
        # 2. Spoof User-Agent (use class constant for consistency)
        options.add_argument(f"user-agent={self.USER_AGENT}")
        
        # 3. Disable Automation Flags
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # 4. Standard Browser Arguments
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-browser-side-navigation")
        options.add_argument("--disable-gpu")
        
        # 5. Window Size (Look like a real monitor)
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")

        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            
            # 6. CDP Commands to mask webdriver property (The "Holy Grail" of basic selenium stealth)
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
            })
            
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise
            
    def verify_linkedin(self, email: str, password: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Attempt to login to LinkedIn.
        
        Returns:
            Tuple(success, error_message, cookies_dict)
        """
        if not webdriver:
            # Simulation for dev environment if selenium missing
            logger.warning("Simulating LinkedIn login success for dev")
            simulated_profile = {
                "cookies": [
                    {
                        "name": "li_at",
                        "value": "simulated_li_at_token_for_dev",
                        "domain": ".linkedin.com",
                        "path": "/",
                        "expiry": int(time.time()) + 172800,
                        "secure": True,
                        "httpOnly": True
                    }
                ],
                "user_agent": self.USER_AGENT,
                "timezone": "Asia/Karachi",
                "language": "en-US"
            }
            return True, None, simulated_profile

        driver = None
        try:
            logger.info(f"Verifying LinkedIn credentials for {email}...")
            driver = self._get_driver()
            
            driver.get("https://www.linkedin.com/login")
            
            # Enter email
            email_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            email_field.clear()
            email_field.send_keys(email)
            
            # Enter password
            pass_field = driver.find_element(By.ID, "password")
            pass_field.clear()
            pass_field.send_keys(password)
            
            # Click login
            submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
            submit_btn.click()
            
            # Wait for navigation
            time.sleep(3)
            
            current_url = driver.current_url
            
            # Check for success (redirect to feed or check for nav bar)
            if "linkedin.com/feed" in current_url or "linkedin.com/check/challenge" not in current_url:
                # Basic check: if we are not still on login page and not on a challenge page
                
                # Check for explicit errors on page
                try:
                    error_div = driver.find_element(By.ID, "error-for-password")
                    return False, f"Invalid password: {error_div.text}", None
                except NoSuchElementException:
                    pass
                    
                try:
                    error_div = driver.find_element(By.ID, "error-for-username")
                    return False, f"Invalid email: {error_div.text}", None
                except NoSuchElementException:
                    pass
                
                # Check for security challenge
                if "challenge" in current_url:
                    return False, "Security check triggered. Please temporarily disable 2FA or try a different network.", None
                
                # If we are here, likely success. Verify by checking for specific element
                try:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.ID, "global-nav"))
                    )
                    logger.info("LinkedIn login confirmed via navigation bar.")
                    
                    # Capture and normalize cookies
                    raw_cookies = driver.get_cookies()
                    profile = self._normalize_cookies(raw_cookies)
                    
                    # Validate li_at presence
                    if not self._has_valid_li_at(profile):
                        logger.warning("Login succeeded but li_at cookie not found - session may not persist")
                    
                    return True, None, profile
                    
                except TimeoutException:
                    # Could be success but slow, or a different page. 
                    # If we aren't on login page, assume success for now but warn
                    if "login" not in current_url:
                         logger.info("LinkedIn login likely successful (left login page).")
                         raw_cookies = driver.get_cookies()
                         profile = self._normalize_cookies(raw_cookies)
                         
                         if not self._has_valid_li_at(profile):
                             logger.warning("Login succeeded but li_at cookie not found - session may not persist")
                         
                         return True, None, profile
                    else:
                        return False, "Login failed (remained on login page)", None
            
            else:
                return False, "Login failed: Redirected to unexpected URL", None
                
        except Exception as e:
            logger.error(f"Selenium error during verification: {e}")
            return False, f"System error during verification: {str(e)}", None
        finally:
            if driver:
                driver.quit()

    def verify_indeed(self, email: str, password: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Placeholder for Indeed verification"""
        return False, "Indeed login not yet implemented", None
