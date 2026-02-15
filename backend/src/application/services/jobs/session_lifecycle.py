"""
Session lifecycle utilities for LinkedIn automation sessions.
Keeps runtime sessions disposable and fail-fast:
- Caps number of apply attempts per session.
- Tracks taint on any anti-bot/429 signal.
- Provides cooldown guidance for the API layer.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class SessionContext:
    """Immutable session context for a single browser session."""

    user_agent: str
    viewport: Tuple[int, int]
    accept_language: str
    proxy: Optional[str] = None
    max_applies: int = 5
    human_scroll_depth_range: Tuple[float, float] = (0.35, 0.9)
    dwell_seconds_range: Tuple[int, int] = (15, 45)


# Severity levels for different taint reasons
# CRITICAL: These trigger cooldowns to prevent account restrictions
CRITICAL_TAINTS = {
    "captcha_detected",
    "security_challenge",
    "account_restricted",
    "http_429",
    "shadow_throttle_detected",
    "login_verification_failed",
    "navigation_error",
    "runtime_exception"
}

# MINOR: These are logged but don't block users (transient issues)
MINOR_WARNINGS = {
    "dom_load_slow",
    "empty_job_content",
    "missing_easy_apply",
    "easy_apply_error"
}

@dataclass
class SessionLifecycleManager:
    """Tracks session lifetime, taint state, and apply caps."""

    max_applies: int = 5
    cooldown_hours_range: Tuple[float, float] = (0.25, 0.5)  # 15-30 minutes
    context: Optional[SessionContext] = None
    applies_started: int = 0
    started_at: float = field(default_factory=time.time)
    tainted: bool = False
    taint_reason: Optional[str] = None
    critical_taint: bool = False  # Only critical taints trigger cooldowns

    def start(self, context: SessionContext) -> None:
        self.context = context
        self.started_at = time.time()
        self.applies_started = 0
        self.tainted = False
        self.taint_reason = None
        self.critical_taint = False

    def record_apply_attempt(self) -> bool:
        """Increment apply counter; returns False if cap exceeded."""
        self.applies_started += 1
        return self.applies_started <= (self.context.max_applies if self.context else self.max_applies)

    def mark_tainted(self, reason: str, critical: bool = False) -> None:
        """Mark session as tainted.
        
        Args:
            reason: The reason for tainting
            critical: If True or reason is in CRITICAL_TAINTS, apply cooldown.
                     Minor warnings don't block future applications.
        """
        self.tainted = True
        self.taint_reason = reason
        # Auto-detect critical taints or use explicit flag
        if critical or reason in CRITICAL_TAINTS:
            self.critical_taint = True

    def should_end_session(self) -> bool:
        cap = self.context.max_applies if self.context else self.max_applies
        # Only end session on critical taints, not minor warnings
        return self.critical_taint or self.applies_started >= cap

    def session_metadata(self) -> Dict[str, object]:
        """Return metadata for API layer persistence."""
        # Only apply cooldown for critical taints
        cooldown_hours = self._cooldown_hours() if self.critical_taint else 0
        return {
            "session_tainted": self.tainted,
            "critical_taint": self.critical_taint,
            "taint_reason": self.taint_reason,
            "applies_started": self.applies_started,
            "cooldown_hours": cooldown_hours,
        }

    def _cooldown_hours(self) -> float:
        low, high = self.cooldown_hours_range
        return random.uniform(low, high)