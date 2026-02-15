"""
Cost Tracker
Track API costs per application for budget management.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class APICall:
    """Record of a single API call"""
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    purpose: str  # "vision", "answer", "batch"
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class JobCostReport:
    """Cost report for a single job application"""
    job_id: str
    job_title: str
    company: str
    total_cost: float
    api_calls: int
    vision_calls: int
    success: bool
    start_time: datetime
    end_time: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0


class CostTracker:
    """
    Track API costs per application for budget management.
    
    Features:
    - Per-model cost tracking
    - Per-job cost reporting
    - Session-wide statistics
    - Budget alerts
    """
    
    # Cost per 1K tokens (as of 2024)
    COSTS_PER_1K_TOKENS = {
        # OpenRouter pricing
        "openai/gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "openai/gpt-4o": {"input": 0.005, "output": 0.015},
        "openai/gpt-4-vision-preview": {"input": 0.01, "output": 0.03},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4o": {"input": 0.005, "output": 0.015},
        # Defaults
        "default": {"input": 0.001, "output": 0.002}
    }
    
    def __init__(self, budget_per_job: float = 0.10, daily_budget: float = 10.0):
        """
        Initialize cost tracker.
        
        Args:
            budget_per_job: Alert if single job exceeds this cost
            daily_budget: Alert if daily spend exceeds this
        """
        self.budget_per_job = budget_per_job
        self.daily_budget = daily_budget
        
        # Current job tracking
        self._current_job_id: Optional[str] = None
        self._current_calls: List[APICall] = []
        self._current_start: Optional[datetime] = None
        
        # Session totals
        self._all_calls: List[APICall] = []
        self._job_reports: List[JobCostReport] = []
        self._session_start = datetime.utcnow()
    
    def start_job(self, job_id: str, job_title: str = "", company: str = "") -> None:
        """Start tracking a new job application"""
        self._current_job_id = job_id
        self._current_calls = []
        self._current_start = datetime.utcnow()
        self._current_title = job_title
        self._current_company = company
        
        logger.debug(f"Cost tracking started for job: {job_title} at {company}")
    
    def log_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        purpose: str = "answer"
    ) -> float:
        """
        Log an API call and return its cost.
        
        Args:
            model: Model name (e.g., "gpt-4o-mini")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            purpose: Purpose of call ("vision", "answer", "batch")
            
        Returns:
            Cost of this call
        """
        cost = self._calculate_cost(model, input_tokens, output_tokens)
        
        call = APICall(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            purpose=purpose
        )
        
        self._current_calls.append(call)
        self._all_calls.append(call)
        
        # Log with cost
        logger.info(
            f"API: {model} | {input_tokens}+{output_tokens} tokens | "
            f"${cost:.4f} | Job total: ${self.current_job_cost:.4f}"
        )
        
        # Budget warnings
        if self.current_job_cost > self.budget_per_job:
            logger.warning(
                f"⚠️ Job cost ${self.current_job_cost:.4f} exceeds budget ${self.budget_per_job:.2f}"
            )
        
        return cost
    
    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for an API call"""
        rates = self.COSTS_PER_1K_TOKENS.get(model, self.COSTS_PER_1K_TOKENS["default"])
        
        input_cost = (input_tokens / 1000) * rates["input"]
        output_cost = (output_tokens / 1000) * rates["output"]
        
        return input_cost + output_cost
    
    def finish_job(self, success: bool) -> JobCostReport:
        """
        Finish tracking current job and generate report.
        
        Args:
            success: Whether application was successful
            
        Returns:
            JobCostReport for this application
        """
        report = JobCostReport(
            job_id=self._current_job_id or "unknown",
            job_title=getattr(self, '_current_title', ''),
            company=getattr(self, '_current_company', ''),
            total_cost=self.current_job_cost,
            api_calls=len(self._current_calls),
            vision_calls=sum(1 for c in self._current_calls if c.purpose == "vision"),
            success=success,
            start_time=self._current_start or datetime.utcnow(),
            end_time=datetime.utcnow()
        )
        
        self._job_reports.append(report)
        
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(
            f"{status} | Cost: ${report.total_cost:.4f} | "
            f"API calls: {report.api_calls} | "
            f"Duration: {report.duration_seconds:.1f}s"
        )
        
        # Reset current job
        self._current_job_id = None
        self._current_calls = []
        self._current_start = None
        
        return report
    
    @property
    def current_job_cost(self) -> float:
        """Total cost for current job"""
        return sum(c.cost for c in self._current_calls)
    
    @property
    def session_cost(self) -> float:
        """Total cost for this session"""
        return sum(c.cost for c in self._all_calls)
    
    @property
    def daily_spend(self) -> float:
        """Total spend today"""
        today = datetime.utcnow().date()
        return sum(
            c.cost for c in self._all_calls
            if c.timestamp.date() == today
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        successful = [r for r in self._job_reports if r.success]
        failed = [r for r in self._job_reports if not r.success]
        
        return {
            "session": {
                "total_cost": self.session_cost,
                "jobs_attempted": len(self._job_reports),
                "jobs_successful": len(successful),
                "jobs_failed": len(failed),
                "success_rate": len(successful) / max(len(self._job_reports), 1),
                "api_calls": len(self._all_calls),
                "duration_minutes": (datetime.utcnow() - self._session_start).total_seconds() / 60
            },
            "costs": {
                "avg_cost_per_job": self.session_cost / max(len(self._job_reports), 1),
                "avg_cost_per_success": sum(r.total_cost for r in successful) / max(len(successful), 1),
                "daily_spend": self.daily_spend,
                "daily_budget": self.daily_budget,
                "budget_remaining": self.daily_budget - self.daily_spend
            },
            "efficiency": {
                "vision_calls": sum(1 for c in self._all_calls if c.purpose == "vision"),
                "batch_calls": sum(1 for c in self._all_calls if c.purpose == "batch"),
                "avg_tokens_per_call": sum(c.input_tokens + c.output_tokens for c in self._all_calls) / max(len(self._all_calls), 1)
            }
        }
    
    def print_summary(self) -> None:
        """Print formatted summary to logger"""
        stats = self.get_stats()
        
        logger.info("=" * 50)
        logger.info("COST TRACKING SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Jobs: {stats['session']['jobs_successful']}/{stats['session']['jobs_attempted']} successful")
        logger.info(f"Total Cost: ${stats['session']['total_cost']:.4f}")
        logger.info(f"Avg Cost/Job: ${stats['costs']['avg_cost_per_job']:.4f}")
        logger.info(f"Avg Cost/Success: ${stats['costs']['avg_cost_per_success']:.4f}")
        logger.info(f"Daily Spend: ${stats['costs']['daily_spend']:.4f} / ${stats['costs']['daily_budget']:.2f}")
        logger.info("=" * 50)


# Global instance
_global_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """Get global cost tracker"""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = CostTracker()
    return _global_tracker
