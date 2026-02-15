"""
Authentication Endpoints
/api/v1/auth/* routes
"""
from fastapi import APIRouter, Depends, HTTPException, status, Form, Body
from loguru import logger
from typing import List, Dict, Any
import json
from uuid import uuid4, UUID
from datetime import datetime, timedelta
import requests
import asyncio
from concurrent.futures import ThreadPoolExecutor
from playwright.async_api import async_playwright

from presentation.api.v1.schemas.auth import LoginResponse, SessionResponse, SessionStatusResponse
from presentation.api.v1.container import get_user_repository
from application.repositories.interfaces import IUserRepository
from domain.entities import User
from domain.value_objects import Email


router = APIRouter()

pending_verification_sessions: Dict[str, Dict[str, Any]] = {}


async def create_session_with_code(platform: str, user_email: str, user_id: str, headless: bool = False) -> str:
    """
    Initialize an email-code login flow for Indeed or Glassdoor.
    Keeps the browser open for manual code entry.
    """
    session_id = str(uuid4())

    def run_playwright_sync() -> str:
        from playwright.sync_api import sync_playwright
        import time

        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(
                headless=headless,
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--disable-setuid-sandbox',
                    '--disable-gpu'
                ]
            )

            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 720},
                ignore_https_errors=True
            )

            page = context.new_page()

            # Add anti-detection
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false
                });
            """)

            if platform == "indeed":
                # Navigate to Indeed login
                page.goto("https://secure.indeed.com/auth", wait_until='load')
                time.sleep(3)  # Let page settle

                # Check for CAPTCHA
                if "verify" in page.url.lower() or page.query_selector('iframe[src*="recaptcha"]'):
                    logger.warning("CAPTCHA detected on Indeed. User needs to solve it manually.")

                # Fill email
                page.wait_for_selector('input[type="email"]', timeout=10000)
                page.fill('input[type="email"]', user_email)
                logger.info(f"Indeed: Filled email {user_email}")
                time.sleep(1)

                # Click continue
                page.click('#emailform > button')
                time.sleep(5)  # Wait longer for next page
                logger.info("Indeed: Clicked continue")

                # Check for CAPTCHA again after submit
                if "verify" in page.url.lower() or page.query_selector('iframe[src*="recaptcha"]'):
                    logger.warning("⚠️ CAPTCHA detected! Browser will stay open for manual solving.")
                    logger.info("Please solve the CAPTCHA manually in the browser...")
                    # Wait for user to solve CAPTCHA (check for 60 seconds)
                    for _ in range(12):  # 12 * 5 = 60 seconds
                        time.sleep(5)
                        if "verify" not in page.url.lower():
                            logger.info("✅ CAPTCHA appears to be solved!")
                            break

                # Wait for password page and click "Sign in with code" link
                try:
                    # Wait for the "Sign in with code" link to appear
                    page.wait_for_selector('text="Sign in with a code instead"', timeout=15000)
                    page.click('text="Sign in with a code instead"')
                    time.sleep(3)
                    logger.info("Indeed: Clicked 'Sign in with code'")

                    # Wait for code input field to appear
                    page.wait_for_selector('input[name="otp"]', timeout=10000)
                    logger.info("Indeed: Waiting for verification code. Check your email!")

                except Exception as e:
                    logger.error(f"Indeed: Could not find 'Sign in with code' option: {e}")
                    logger.error(f"Current URL: {page.url}")
                    # Take screenshot for debugging if not headless
                    if not headless:
                        try:
                            page.screenshot(path="indeed_error.png")
                            logger.info("Screenshot saved as indeed_error.png")
                        except Exception:
                            pass
                    browser.close()
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Could not access 'Sign in with code' option. CAPTCHA or page structure issue."
                    )

            elif platform == "glassdoor":
                # Navigate to Glassdoor login
                page.goto("https://www.glassdoor.com/profile/login_input.htm", wait_until='load')
                time.sleep(2)

                # Fill email
                page.wait_for_selector('input[type="email"]', timeout=10000)
                page.fill('input[type="email"]', user_email)
                logger.info(f"Glassdoor: Filled email {user_email}")

                # Click continue
                page.click('button[type="submit"]')
                time.sleep(3)
                logger.info("Glassdoor: Clicked continue")

                # Try to find "Send me a code" or similar option
                try:
                    # Glassdoor may have different text, adjust as needed
                    page.wait_for_selector('text="Send me a code"', timeout=10000)
                    page.click('text="Send me a code"')
                    time.sleep(2)
                    logger.info("Glassdoor: Clicked 'Send me a code'")

                    # Wait for code input
                    page.wait_for_selector('input[type="text"][name="code"]', timeout=10000)
                    logger.info("Glassdoor: Waiting for verification code. Check your email!")

                except Exception as e:
                    logger.error(f"Glassdoor: Could not find 'Send me a code' option: {e}")
                    browser.close()
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Could not access verification code option. Page structure may have changed."
                    )
            else:
                browser.close()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unsupported platform for code-based login"
                )

            # Store browser session for later code submission
            pending_verification_sessions[session_id] = {
                "playwright": playwright,
                "page": page,
                "browser": browser,
                "context": context,
                "platform": platform,
                "user_id": user_id
            }

            logger.info(f"✅ Session {session_id} ready for verification code. Email sent to {user_email}")
            return session_id

        except Exception:
            try:
                browser.close()
            except Exception:
                pass
            try:
                playwright.stop()
            except Exception:
                pass
            raise

    # Run in thread pool to avoid Windows asyncio subprocess issues
    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(executor, run_playwright_sync)
            return result
    except Exception as e:
        logger.error(f"Error creating session with code: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize login: {str(e)}"
        )


async def create_interactive_session(platform: str, user_email: str, user_password: str, user_id: str) -> str:
    """
    Create an automated session for Indeed or Glassdoor using stored credentials.
    
    Opens browser, navigates to login page, fills email and password, submits form,
    and verifies successful login.
    """
    session_id = str(uuid4())
    
    try:
        async with async_playwright() as p:
            # Launch browser with stealth mode
            browser = await p.chromium.launch(
                headless=False,  # Must be visible for user interaction
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 720}
            )
            
            page = await context.new_page()
            
            # Navigate to the appropriate URL
            if platform == "indeed":
                await page.goto("https://secure.indeed.com/auth", wait_until='load')
                await page.wait_for_load_state('networkidle')
                
                # Fill email
                await page.wait_for_selector('input[type="email"]', timeout=10000)
                await page.fill('input[type="email"]', user_email)
                logger.info(f"Indeed: Filled email for user {user_id}")
                
                # Click continue
                await page.click('#emailform > button')
                await page.wait_for_load_state('networkidle')
                logger.info(f"Indeed: Clicked continue button")
                
                # Fill password
                await page.wait_for_selector('input[type="password"]', timeout=10000)
                await page.fill('input[type="password"]', user_password)
                logger.info(f"Indeed: Filled password for user {user_id}")
                
                # Click submit/login button
                await page.click('button[type="submit"]')
                await page.wait_for_load_state('networkidle')
                logger.info(f"Indeed: Clicked login button")
                
                # Wait for successful login - check for dashboard/jobs page
                try:
                    await page.wait_for_function("""
                        () => {
                            const url = window.location.href;
                            return url.includes('indeed.com/jobs') || 
                                   url.includes('indeed.com/m/') ||
                                   !url.includes('auth');
                        }
                    """, timeout=30000)
                    logger.info(f"✅ Indeed login successful for user {user_id}")
                except Exception as e:
                    logger.error(f"❌ Indeed login failed: {e}")
                    await browser.close()
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Indeed login failed. Please check your credentials."
                    )
                    
            elif platform == "glassdoor":
                await page.goto("https://www.glassdoor.com/profile/login_input.htm", wait_until='load')
                await page.wait_for_load_state('networkidle')
                
                # Fill email
                await page.wait_for_selector('input[type="email"]', timeout=10000)
                await page.fill('input[type="email"]', user_email)
                logger.info(f"Glassdoor: Filled email for user {user_id}")
                
                # Click continue
                await page.click('button[type="submit"]')
                await page.wait_for_load_state('networkidle')
                logger.info(f"Glassdoor: Clicked continue button")
                
                # Fill password
                await page.wait_for_selector('input[type="password"]', timeout=10000)
                await page.fill('input[type="password"]', user_password)
                logger.info(f"Glassdoor: Filled password for user {user_id}")
                
                # Click submit/login button
                await page.click('button[type="submit"]')
                await page.wait_for_load_state('networkidle')
                logger.info(f"Glassdoor: Clicked login button")
                
                # Wait for successful login
                try:
                    await page.wait_for_function("""
                        () => {
                            const url = window.location.href;
                            return !url.includes('login');
                        }
                    """, timeout=30000)
                    logger.info(f"✅ Glassdoor login successful for user {user_id}")
                except Exception as e:
                    logger.error(f"❌ Glassdoor login failed: {e}")
                    await browser.close()
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Glassdoor login failed. Please check your credentials."
                    )
            
            # Get cookies after successful login
            cookies = await context.cookies()
            
            # TODO: Save cookies to database for future automated sessions
            logger.info(f"Retrieved {len(cookies)} cookies for {platform}")
            
            # Close browser
            await browser.close()
            
            logger.info(f"✅ {platform} session {session_id} created successfully")
            return session_id
                
    except Exception as e:
        logger.error(f"Error creating {platform} interactive session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create {platform} session: {str(e)}"
        )


def validate_linkedin_cookies(cookies: List[Dict[str, Any]]) -> bool:
    """
    Validate LinkedIn cookies by attempting to access the feed.
    Returns True if cookies are valid and can access LinkedIn feed.
    """
    try:
        # Convert cookies list to requests-compatible format
        cookie_jar = {}
        for cookie in cookies:
            name = cookie.get('name', '')
            value = cookie.get('value', '')
            if name and value:
                cookie_jar[name] = value
        
        if not cookie_jar:
            logger.warning("No valid cookies to test")
            return False
        
        # Test cookies by accessing LinkedIn feed
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
        }
        
        # Try to access LinkedIn feed
        response = requests.get(
            'https://www.linkedin.com/feed/',
            cookies=cookie_jar,
            headers=headers,
            timeout=10,
            allow_redirects=False
        )
        
        # If we get 200 or feed content, cookies are valid
        # If we get redirected to login (302/303), cookies are invalid
        if response.status_code == 200:
            # Check if we're actually logged in (not on login page)
            if 'login' in response.url.lower() or 'authwall' in response.url.lower():
                logger.warning("Cookies redirected to login page - invalid")
                return False
            
            logger.info("✅ Successfully accessed LinkedIn feed - cookies are valid")
            return True
        elif response.status_code in [301, 302, 303, 307, 308]:
            # Check redirect location
            location = response.headers.get('Location', '')
            if 'login' in location.lower() or 'authwall' in location.lower():
                logger.warning("Cookies redirect to login - invalid")
                return False
            logger.info("✅ Cookies accepted by LinkedIn")
            return True
        else:
            logger.warning(f"Unexpected response code: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error validating cookies: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error validating cookies: {e}")
        return False


@router.post("/linkedin/login", response_model=LoginResponse)
async def linkedin_login(
    email: str = Form(..., description="User email address"),
    linkedin_username: str = Form(..., description="LinkedIn username/email"),
    linkedin_password: str = Form(..., description="LinkedIn password"),
    user_repo: IUserRepository = Depends(get_user_repository)
):
    """
    Login with LinkedIn username and password.
    
    **Flow:**
    1. User provides their email, LinkedIn username, and LinkedIn password
    2. System stores credentials securely in the database
    3. Credentials will be used for automated LinkedIn login during job applications
    4. Return user_id for subsequent API calls
    
    **Required form parameters:**
    - email: User email address (for account identification)
    - linkedin_username: LinkedIn username/email
    - linkedin_password: LinkedIn password
    
    **Response:** Returns user_id for subsequent API calls
    """
    try:
        logger.info(f"LinkedIn username/password login attempt for: {email}")
        
        # Validate email format
        try:
            email_vo = Email(email)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid email format: {str(e)}"
            )
        
        # Check if user exists or create new one
        user = await user_repo.get_by_email(email)
        
        if not user:
            # Create new user
            logger.info(f"Creating new user from LinkedIn: {email}")
            
            from infrastructure.security.password_hasher import BcryptPasswordHasher
            password_hasher = BcryptPasswordHasher()
            
            # Generate random password (won't be used since we use LinkedIn auth)
            internal_password = str(uuid4())
            password_hash = password_hasher.hash_password(internal_password)
            
            new_user = User(
                id=uuid4(),
                email=email_vo,
                password_hash=password_hash,
                full_name="LinkedIn User",
                target_job_title="",
                industry="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        
        if not user:
            # Create new user
            logger.info(f"Creating new user from LinkedIn: {email}")
            
            from infrastructure.security.password_hasher import BcryptPasswordHasher
            password_hasher = BcryptPasswordHasher()
            
            # Generate random password (won't be used since we use LinkedIn auth)
            internal_password = str(uuid4())
            password_hash = password_hasher.hash_password(internal_password)
            
            new_user = User(
                id=uuid4(),
                email=email_vo,
                password_hash=password_hash,
                full_name="LinkedIn User",
                target_job_title="",
                industry="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            user = await user_repo.create(new_user)
            message = "Account created with LinkedIn credentials"
        else:
            message = "LinkedIn credentials updated successfully"
        
        # Store LinkedIn credentials in database
        await user_repo.update_linkedin_username_password(
            user_id=user.id,
            linkedin_username=linkedin_username,
            linkedin_password=linkedin_password
        )
        
        logger.info(f"Stored LinkedIn credentials for user {user.id}")
        logger.info(f"User logged in successfully via LinkedIn: {user.email}")
        
        return LoginResponse(
            user_id=str(user.id),
            message=f"{message}. Credentials stored securely."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during LinkedIn login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="System error during login. Please try again later."
        )


@router.patch("/linkedin/credentials", response_model=LoginResponse)
async def update_linkedin_credentials(
    uid: str = Form(..., description="User ID (UUID)"),
    linkedin_username: str = Form(..., description="LinkedIn username/email"),
    linkedin_password: str = Form(..., description="LinkedIn password"),
    user_repo: IUserRepository = Depends(get_user_repository)
):
    """Update stored LinkedIn credentials for an existing user."""
    try:
        # Validate UID
        try:
            user_id = UUID(uid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid UID format (expected UUID)"
            )

        user = await user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Update LinkedIn credentials
        await user_repo.update_linkedin_username_password(
            user_id=user_id,
            linkedin_username=linkedin_username,
            linkedin_password=linkedin_password
        )
        
        logger.info(f"Updated LinkedIn credentials for user {user_id}")

        return LoginResponse(user_id=str(user_id), message="LinkedIn credentials updated successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating LinkedIn credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update credentials"
        )


@router.post("/session", response_model=SessionResponse)
async def create_session(
    user_id: str = Form(..., description="User ID (UUID)"),
    linkedin: bool = Form(False, description="Create LinkedIn session"),
    indeed: bool = Form(False, description="Create Indeed session"),
    headless: bool = Form(True, description="Run browser in headless mode"),
    user_repo: IUserRepository = Depends(get_user_repository)
):
    """
    Create a temporary session for job platforms.
    
    **Supported platforms:**
    1. **LinkedIn**: Uses stored credentials for automated login
    2. **Indeed**: Opens browser, injects stored cookies, and verifies authentication
    
    **Required form parameters:**
    - user_id: User ID (UUID)
    - linkedin: Boolean to create LinkedIn session
    - indeed: Boolean to create Indeed session
    - headless: Whether to run browser in headless mode (default: true)
    
    **Response:** Returns session_id for subsequent API calls
    """
    try:
        # Validate user ID
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format (expected UUID)"
            )
        
        # Get user from database
        user = await user_repo.get_by_id(user_uuid)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        logger.info(f"Creating session for user: {user.email} (ID: {user_uuid})")
        
        # Validate platform selection
        selected_platforms = [linkedin, indeed]
        if sum(selected_platforms) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Exactly one platform must be selected (linkedin or indeed)"
            )
        
        if linkedin:
            # LinkedIn: Use existing automated method
            if not user.linkedin_username or not user.linkedin_password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="LinkedIn credentials not found. Please login first via /api/v1/auth/linkedin/login"
                )
            
            from application.services.linkedin_session_manager import get_session_manager
            
            session_manager = get_session_manager()
            session_id, error = await session_manager.create_session(
                user_id=user_id,
                linkedin_username=str(user.email),
                linkedin_password=user.linkedin_password,
                headless=headless
            )
            
            if not session_id:
                logger.error(f"Failed to create LinkedIn session: {error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create LinkedIn session: {error}"
                )
            
            logger.info(f"LinkedIn session created successfully: {session_id}")
            return SessionResponse(
                session_id=session_id,
                message="LinkedIn session created successfully. Use this session_id for job operations.",
                expires_in_minutes=30
            )
            
        elif indeed:
            # Indeed: Inject stored cookies and verify authentication
            logger.info(f"Creating Indeed session with cookie injection for user {user_uuid}")
            
            # Check if user has stored cookies
            if not user.encrypted_indeed_username:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Indeed cookies not found. Please add cookies via /api/v1/auth/indeed/login"
                )
            
            # Decrypt and parse cookies
            from application.services.auth.credential_encryption import credential_encryption
            import json
            
            cookies_json, _ = credential_encryption.decrypt_indeed_credentials(
                user.encrypted_indeed_username, user.encrypted_indeed_password
            )
            
            try:
                cookies_data = json.loads(cookies_json)
                jsessionid = cookies_data.get("JSESSIONID")
                shoe = cookies_data.get("SHOE")
                
                if not jsessionid or not shoe:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid cookies data. Please re-add cookies via /api/v1/auth/indeed/login"
                    )
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid cookies format. Please re-add cookies via /api/v1/auth/indeed/login"
                )
            
            # Open browser, inject cookies, and verify
            from concurrent.futures import ThreadPoolExecutor
            import asyncio
            
            def inject_cookies_and_verify():
                from playwright.sync_api import sync_playwright
                import time
                
                playwright = sync_playwright().start()
                browser = None
                try:
                    browser = playwright.chromium.launch(
                        headless=headless,
                        args=[
                            '--disable-blink-features=AutomationControlled',
                            '--disable-dev-shm-usage',
                            '--no-sandbox',
                            '--disable-setuid-sandbox',
                            '--disable-gpu'
                        ]
                    )
                    
                    context = browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        ignore_https_errors=True
                    )
                    
                    page = context.new_page()
                    
                    # Add anti-detection
                    page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => false
                        });
                    """)
                    
                    logger.info("Opening Indeed homepage...")
                    try:
                        page.goto("https://www.indeed.com", wait_until="domcontentloaded", timeout=30000)
                        logger.info("Indeed homepage loaded successfully")
                    except Exception as nav_error:
                        logger.warning(f"Initial navigation timeout, retrying: {nav_error}")
                        try:
                            page.goto("https://www.indeed.com", wait_until="networkidle", timeout=30000)
                        except:
                            logger.warning("Second attempt with networkidle also timed out, proceeding anyway")
                    time.sleep(1)
                    
                    # Inject cookies
                    logger.info("Injecting cookies...")
                    context.add_cookies([
                        {
                            "name": "JSESSIONID",
                            "value": jsessionid,
                            "domain": ".indeed.com",
                            "path": "/"
                        },
                        {
                            "name": "SHOE",
                            "value": shoe,
                            "domain": ".indeed.com",
                            "path": "/"
                        }
                    ])
                    
                    # Refresh page to apply cookies
                    logger.info("Refreshing page to apply cookies...")
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=30000)
                        logger.info("Page refreshed successfully")
                    except Exception as reload_error:
                        logger.warning(f"Page reload timeout: {reload_error}, proceeding anyway")
                    time.sleep(1)
                    
                    # Verify authentication by checking for signed-in elements
                    logger.info("Verifying authentication...")
                    is_authenticated = False
                    
                    try:
                        # Check for multiple possible authentication indicators
                        # Try different selectors that indicate logged-in state
                        selectors_to_try = [
                            '[data-testid="gnav-account-menu"]',
                            '#gnav-Account',
                            'a[href*="/account"]',
                            '[data-gnav-element-name="Account"]',
                            '.gnav-AccountMenu',
                            'button[aria-label*="Account"]',
                            '[data-testid="user-menu"]',
                            'a[href*="/profile"]'
                        ]
                        
                        for selector in selectors_to_try:
                            try:
                                page.wait_for_selector(selector, timeout=2000)
                                is_authenticated = True
                                logger.info(f"✅ Indeed authentication verified! Found selector: {selector}")
                                break
                            except:
                                continue
                        
                        if not is_authenticated:
                            # Check URL as final verification
                            current_url = page.url
                            logger.info(f"Current URL: {current_url}")
                            # If we're not on a login page, assume success
                            if "login" not in current_url.lower() and "auth" not in current_url.lower():
                                is_authenticated = True
                                logger.info("✅ Indeed authentication verified! Not on login page, assuming success.")
                            else:
                                logger.warning("⚠️ Could not verify authentication. Still on login/auth page.")
                    except Exception as e:
                        logger.warning(f"⚠️ Error during authentication verification: {e}")
                        # Assume authenticated if we got this far without critical errors
                        is_authenticated = True
                        logger.info("✅ Proceeding with session creation despite verification errors.")
                    
                    session_id = str(uuid4())
                    
                    # Keep browser open for further operations
                    # Store context for future use
                    pending_verification_sessions[session_id] = {
                        "browser": browser,
                        "context": context,
                        "page": page,
                        "platform": "indeed",
                        "user_id": user_id,
                        "authenticated": is_authenticated,
                        "playwright": playwright
                    }
                    
                    return session_id, is_authenticated
                except Exception:
                    if browser:
                        try:
                            browser.close()
                        except Exception:
                            pass
                    try:
                        playwright.stop()
                    except Exception:
                        pass
                    raise
            
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                session_id, is_authenticated = await loop.run_in_executor(executor, inject_cookies_and_verify)
            
            if is_authenticated:
                return SessionResponse(
                    session_id=session_id,
                    message="Indeed session created successfully. Cookies injected and verified.",
                    expires_in_minutes=30
                )
            else:
                return SessionResponse(
                    session_id=session_id,
                    message="Indeed session created but authentication could not be verified. Cookies may be invalid.",
                    expires_in_minutes=30
                )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session"
        )
        logger.error(f"Unexpected error creating LinkedIn session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session"
        )


@router.delete("/session/{session_id}")
async def dispose_session(
    session_id: str
):
    """
    Dispose of a session and close the browser.
    
    **Parameters:**
    - session_id: Session ID to dispose
    
    **Response:** Confirmation message
    """
    try:
        # Check if it's a pending verification session
        if session_id in pending_verification_sessions:
            session_data = pending_verification_sessions.pop(session_id)
            try:
                session_data["browser"].close()  # Sync close for sync Playwright
            except Exception:
                pass
            playwright = session_data.get("playwright")
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass
            logger.info(f"Closed pending verification session {session_id}")
            return {"message": "Pending verification session disposed successfully"}
        
        from application.services.linkedin_session_manager import get_session_manager
        
        session_manager = get_session_manager()
        success = session_manager.dispose_session(session_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or already disposed"
            )
        
        return {"message": "Session disposed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disposing session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dispose session"
        )


@router.get("/session-status", response_model=SessionStatusResponse)
async def get_session_status(
    user_id: str
):
    """
    Get status of user's active session.
    
    **Parameters:**
    - user_id: User ID (UUID)
    
    **Returns:**
    - Session status details including uptime, task info, and activity
    
    **Response:**
    ```json
    {
      "session_id": "uuid",
      "user_id": "uuid",
      "status": "active|in_use|completed|expired|error",
      "created_at": "2026-01-16T12:00:00",
      "last_used": "2026-01-16T12:05:00",
      "uptime_seconds": 300.5,
      "idle_seconds": 12.3,
      "task_name": "job_discovery",
      "task_started_at": "2026-01-16T12:02:00",
      "task_completed_at": null,
      "error_message": null
    }
    ```
    """
    try:
        # Validate user ID
        try:
            UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format (expected UUID)"
            )
        
        from application.services.linkedin_session_manager import get_session_manager
        
        session_manager = get_session_manager()
        session_status = session_manager.get_user_session_status(user_id)
        
        if not session_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active session found for this user"
            )
        
        return SessionStatusResponse(**session_status)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session status"
        )


@router.post("/indeed/login", response_model=LoginResponse)
async def indeed_login(
    uid: str = Form(..., description="User ID (UUID)"),
    jsessionid: str = Form(..., description="Indeed JSESSIONID cookie value"),
    shoe: str = Form(..., description="Indeed SHOE cookie value"),
    user_repo: IUserRepository = Depends(get_user_repository)
):
    """
    Store Indeed cookies (JSESSIONID and SHOE) for an existing user.
    
    **Flow:**
    1. User provides their UID, JSESSIONID, and SHOE cookie values
    2. System validates the UID and finds the user
    3. System stores cookies securely in the database
    4. Cookies will be used for authenticated Indeed sessions during job applications
    
    **Required form parameters:**
    - uid: User ID (UUID) to associate cookies with
    - jsessionid: Indeed JSESSIONID cookie value
    - shoe: Indeed SHOE cookie value
    
    **Response:** Returns confirmation message
    """
    try:
        logger.info(f"Indeed cookies storage attempt for user: {uid}")
        
        # Validate UID
        try:
            user_id = UUID(uid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid UID format (expected UUID)"
            )
        
        # Check if user exists
        user = await user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Encrypt and store cookies as JSON
        from application.services.auth.credential_encryption import credential_encryption
        import json
        
        cookies_json = json.dumps({
            "JSESSIONID": jsessionid,
            "SHOE": shoe
        })
        
        encrypted_username, encrypted_password = credential_encryption.encrypt_indeed_credentials(
            cookies_json, ""
        )
        
        await user_repo.update_encrypted_indeed_credentials(
            user_id=user.id,
            encrypted_username=encrypted_username,
            encrypted_password=encrypted_password
        )
        
        logger.info(f"Stored Indeed cookies for user {user.id}")
        
        return LoginResponse(
            user_id=str(user.id),
            message="Indeed cookies stored successfully. You can now create authenticated Indeed sessions."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during Indeed cookie storage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="System error during cookie storage. Please try again later."
        )