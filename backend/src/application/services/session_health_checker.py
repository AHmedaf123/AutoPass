"""
Session Health Checker - Detect unhealthy sessions mid-task
Detects: 429 rate limiting, expired sessions, LinkedIn checkpoints
"""
import json
from typing import Optional, Dict, List
from datetime import datetime, timezone
from enum import Enum
from loguru import logger


class HealthIssueType(str, Enum):
    """Types of health issues that can be detected"""
    HTTP_429_ERROR = "429_error"  # Rate limited by LinkedIn
    EXPIRED_SESSION = "expired_session"  # Session cookies expired
    LINKEDIN_CHECKPOINT = "linkedin_checkpoint"  # LinkedIn checkpoint/verification required
    INVALID_CREDENTIALS = "invalid_credentials"  # Login failed or invalid
    ACCOUNT_RESTRICTED = "account_restricted"  # Account restricted/suspended


class SessionHealthChecker:
    """Detects and tracks session health issues during task execution"""
    
    def __init__(self):
        """Initialize health checker with error detection patterns"""
        self.health_issues: Dict[str, HealthIssueType] = {}
    
    def check_for_429_error(self, error_message: str, error_type: str) -> Optional[HealthIssueType]:
        """Detect HTTP 429 (Too Many Requests) rate limiting error
        
        Returns:
            HealthIssueType.HTTP_429_ERROR if detected, None otherwise
        """
        if not error_message or not error_type:
            return None
        
        # Check for 429 in error message
        if "429" in error_message:
            logger.warning(f"⚠️  HTTP 429 Rate Limiting detected: {error_message}")
            return HealthIssueType.HTTP_429_ERROR
        
        # Check for HTTP 429 error type
        if "429" in error_type or "rate" in error_type.lower() or "too_many_requests" in error_type.lower():
            logger.warning(f"⚠️  HTTP 429 Rate Limiting detected: {error_type}")
            return HealthIssueType.HTTP_429_ERROR
        
        # Check for LinkedIn-specific rate limit messages
        rate_limit_indicators = [
            "rate limit",
            "too many requests",
            "retry later",
            "temporarily blocked",
            "throttl",
            "429"
        ]
        
        error_lower = error_message.lower()
        if any(indicator in error_lower for indicator in rate_limit_indicators):
            logger.warning(f"⚠️  Rate limiting detected: {error_message}")
            return HealthIssueType.HTTP_429_ERROR
        
        return None
    
    def check_for_expired_session(self, error_message: str, error_type: str) -> Optional[HealthIssueType]:
        """Detect expired or invalid session tokens
        
        Returns:
            HealthIssueType.EXPIRED_SESSION if detected, None otherwise
        """
        if not error_message or not error_type:
            return None
        
        # Session expiration indicators
        expiration_indicators = [
            "session expired",
            "session invalid",
            "login required",
            "not logged in",
            "authentication failed",
            "unauthorized",
            "invalid session",
            "session ended",
            "cookie expired",
            "li_at",  # LinkedIn session cookie
            "jsessionid",  # Session ID cookie
            "401",  # Unauthorized HTTP status
            "403",  # Forbidden HTTP status
        ]
        
        error_lower = error_message.lower()
        type_lower = error_type.lower()
        
        if any(indicator in error_lower for indicator in expiration_indicators):
            logger.warning(f"⚠️  Expired/Invalid session detected: {error_message}")
            return HealthIssueType.EXPIRED_SESSION
        
        if any(indicator in type_lower for indicator in expiration_indicators):
            logger.warning(f"⚠️  Expired/Invalid session detected: {error_type}")
            return HealthIssueType.EXPIRED_SESSION
        
        return None
    
    def check_for_linkedin_checkpoint(self, error_message: str, error_type: str) -> Optional[HealthIssueType]:
        """Detect LinkedIn verification/checkpoint challenges mid-task
        
        Returns:
            HealthIssueType.LINKEDIN_CHECKPOINT if detected, None otherwise
        """
        if not error_message or not error_type:
            return None
        
        # LinkedIn checkpoint indicators
        checkpoint_indicators = [
            "checkpoint",
            "verify",
            "verification",
            "confirm",
            "unusual activity",
            "unusual sign-in",
            "confirm identity",
            "security check",
            "challenge",
            "captcha",
            "verify account",
            "sign in again",
            "suspicious activity",
        ]
        
        error_lower = error_message.lower()
        type_lower = error_type.lower()
        
        if any(indicator in error_lower for indicator in checkpoint_indicators):
            logger.warning(f"⚠️  LinkedIn checkpoint/verification detected: {error_message}")
            return HealthIssueType.LINKEDIN_CHECKPOINT
        
        if any(indicator in type_lower for indicator in checkpoint_indicators):
            logger.warning(f"⚠️  LinkedIn checkpoint/verification detected: {error_type}")
            return HealthIssueType.LINKEDIN_CHECKPOINT
        
        return None
    
    def check_health(self, error_message: str, error_type: str) -> Optional[HealthIssueType]:
        """Perform comprehensive health check on error
        
        Checks in order of severity/commonality:
        1. HTTP 429 rate limiting
        2. Expired sessions
        3. LinkedIn checkpoints
        
        Args:
            error_message: The error message from exception
            error_type: The error type/class name
        
        Returns:
            HealthIssueType if issue detected, None otherwise
        """
        # Check in priority order
        result = self.check_for_429_error(error_message, error_type)
        if result:
            return result
        
        result = self.check_for_expired_session(error_message, error_type)
        if result:
            return result
        
        result = self.check_for_linkedin_checkpoint(error_message, error_type)
        if result:
            return result
        
        return None
    
    def should_mark_session_tainted(self, error_message: str, error_type: str) -> bool:
        """Determine if session should be marked as TAINTED based on error
        
        Sessions are marked tainted when:
        - HTTP 429 rate limiting detected (affects future requests)
        - Expired session detected (session is no longer valid)
        - LinkedIn checkpoint triggered (manual verification required)
        
        Args:
            error_message: The error message
            error_type: The error type
        
        Returns:
            True if session should be marked TAINTED, False otherwise
        """
        issue = self.check_health(error_message, error_type)
        return issue is not None
    
    def get_cooldown_duration_seconds(self, issue_type: HealthIssueType) -> int:
        """Get recommended cooldown duration for health issue
        
        Cooldown recommendations:
        - 429: 3600s (1 hour) - wait for rate limit reset
        - Expired: 300s (5 mins) - allow time for re-login
        - Checkpoint: 1800s (30 mins) - wait for manual resolution
        
        Args:
            issue_type: The type of health issue
        
        Returns:
            Cooldown duration in seconds
        """
        cooldown_map = {
            HealthIssueType.HTTP_429_ERROR: 3600,  # 1 hour for 429
            HealthIssueType.EXPIRED_SESSION: 300,  # 5 minutes for expired
            HealthIssueType.LINKEDIN_CHECKPOINT: 1800,  # 30 minutes for checkpoint
            HealthIssueType.INVALID_CREDENTIALS: 600,  # 10 minutes for invalid creds
            HealthIssueType.ACCOUNT_RESTRICTED: 7200,  # 2 hours for restricted
        }
        return cooldown_map.get(issue_type, 600)  # Default 10 mins
    
    def get_issue_description(self, issue_type: HealthIssueType) -> str:
        """Get human-readable description of health issue
        
        Args:
            issue_type: The type of health issue
        
        Returns:
            Human-readable description
        """
        descriptions = {
            HealthIssueType.HTTP_429_ERROR: "Rate limited by LinkedIn - too many requests",
            HealthIssueType.EXPIRED_SESSION: "Session expired or invalid credentials",
            HealthIssueType.LINKEDIN_CHECKPOINT: "LinkedIn checkpoint/verification required",
            HealthIssueType.INVALID_CREDENTIALS: "Invalid login credentials",
            HealthIssueType.ACCOUNT_RESTRICTED: "Account restricted or suspended",
        }
        return descriptions.get(issue_type, "Unknown health issue")


def get_session_health_checker() -> SessionHealthChecker:
    """Factory function to get session health checker instance"""
    return SessionHealthChecker()
