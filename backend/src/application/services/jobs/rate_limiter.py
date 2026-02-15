"""
Rate Limiter Module
Handles rate limiting, backoff, and rate limit detection for HTTP requests
"""
import time
from typing import Optional, Dict, Tuple
from loguru import logger


class RateLimiter:
    """
    Centralized rate limiting for API requests.
    Tracks request history, enforces minimum delays, and handles rate limit responses.
    """
    
    def __init__(
        self,
        min_delay_seconds: float = 60.0,
        jitter_range: Tuple[float, float] = (0, 10),
        max_requests_per_session: int = 20,
        initial_backoff_seconds: float = 2.0,
        max_backoff_seconds: float = 300.0,
        backoff_multiplier: float = 2.0
    ):
        """
        Initialize rate limiter.
        
        Args:
            min_delay_seconds: Minimum delay between requests
            jitter_range: Random jitter to add to delays (min, max) in seconds
            max_requests_per_session: Maximum requests allowed per session
            initial_backoff_seconds: Starting delay for exponential backoff
            max_backoff_seconds: Maximum delay for exponential backoff
            backoff_multiplier: Multiplier for exponential backoff (e.g., 2 = double each time)
        """
        self.min_delay_seconds = min_delay_seconds
        self.jitter_range = jitter_range
        self.max_requests_per_session = max_requests_per_session
        self.initial_backoff_seconds = initial_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.backoff_multiplier = backoff_multiplier
        
        # Tracking
        self.last_request_time = 0
        self.request_count = 0
        self.consecutive_rate_limits = 0
        self.last_retry_after = 0
    
    def check_rate_limit(self) -> None:
        """
        Enforce rate limiting before making a request.
        Blocks until minimum delay has passed.
        """
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        # Check session limit
        if self.request_count >= self.max_requests_per_session:
            logger.warning(
                f"⚠️  Session rate limit exceeded ({self.request_count}/{self.max_requests_per_session})"
            )
            raise Exception(
                f"Rate limit exceeded - too many requests in session "
                f"({self.request_count}/{self.max_requests_per_session})"
            )
        
        # Check minimum delay + jitter
        import random
        jitter = random.uniform(self.jitter_range[0], self.jitter_range[1])
        required_delay = self.min_delay_seconds + jitter
        
        if time_since_last < required_delay:
            sleep_time = required_delay - time_since_last
            logger.info(
                f"⏱️  Rate limiting: sleeping {sleep_time:.2f}s "
                f"(delay: {self.min_delay_seconds}s + jitter: {jitter:.2f}s)"
            )
            time.sleep(sleep_time)
        
        # Update tracking
        self.last_request_time = time.time()
        self.request_count += 1
        self.consecutive_rate_limits = 0  # Reset on successful request
    
    def handle_rate_limit_response(self, response_headers: Dict[str, str]) -> float:
        """
        Handle rate limit response from server.
        Extracts wait time from headers and enforces it.
        
        Args:
            response_headers: Response headers from failed request
            
        Returns:
            Wait time in seconds before retry
            
        Raises:
            Exception: If rate limit threshold exceeded
        """
        self.consecutive_rate_limits += 1
        logger.warning(f"⚠️  Rate limit detected (consecutive: {self.consecutive_rate_limits})")
        
        # Check circuit breaker (3 consecutive rate limits = give up)
        if self.consecutive_rate_limits >= 3:
            logger.error(
                f"❌ Rate limit circuit breaker triggered "
                f"({self.consecutive_rate_limits} consecutive rate limits)"
            )
            raise Exception(
                f"Rate limit circuit breaker triggered after "
                f"{self.consecutive_rate_limits} consecutive rate limits. "
                "Please try again in 1 hour."
            )
        
        # Check for Retry-After header (most authoritative)
        retry_after = response_headers.get('Retry-After')
        if retry_after:
            try:
                # Could be seconds (integer) or HTTP date
                wait_seconds = float(retry_after)
            except ValueError:
                # Assume it's an HTTP date, use default
                wait_seconds = self._backoff_seconds(self.consecutive_rate_limits - 1)
        else:
            # Use exponential backoff if no Retry-After header
            wait_seconds = self._backoff_seconds(self.consecutive_rate_limits - 1)
        
        # Cap at max backoff
        wait_seconds = min(wait_seconds, self.max_backoff_seconds)
        
        logger.warning(
            f"Rate limit response: waiting {wait_seconds:.0f}s before retry "
            f"(attempt {self.consecutive_rate_limits}/3)"
        )
        
        # Store for tracking
        self.last_retry_after = wait_seconds
        
        return wait_seconds
    
    def _backoff_seconds(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay.
        
        Args:
            attempt: Attempt number (0-indexed)
            
        Returns:
            Delay in seconds
        """
        # Exponential backoff: initial * (multiplier ^ attempt)
        delay = self.initial_backoff_seconds * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_backoff_seconds)
    
    def reset(self) -> None:
        """Reset rate limiter for new session"""
        logger.info("🔄 Resetting rate limiter for new session")
        self.last_request_time = 0
        self.request_count = 0
        self.consecutive_rate_limits = 0
        self.last_retry_after = 0
    
    def get_stats(self) -> Dict[str, any]:
        """Get current rate limiter statistics"""
        return {
            'request_count': self.request_count,
            'consecutive_rate_limits': self.consecutive_rate_limits,
            'last_retry_after': self.last_retry_after,
            'time_since_last_request': time.time() - self.last_request_time
        }
