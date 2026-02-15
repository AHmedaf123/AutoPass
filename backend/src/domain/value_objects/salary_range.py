"""
Salary Range Value Object
Immutable salary range with validation
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SalaryRange:
    """Salary range value object (annual USD)"""
    
    min_salary: int
    max_salary: Optional[int] = None
    
    def __post_init__(self):
        """Validate salary range"""
        if self.min_salary < 0:
            raise ValueError("Minimum salary cannot be negative")
        
        if self.max_salary is not None:
            if self.max_salary < 0:
                raise ValueError("Maximum salary cannot be negative")
            if self.max_salary < self.min_salary:
                raise ValueError("Maximum salary cannot be less than minimum salary")
    
    def contains(self, salary: int) -> bool:
        """Check if salary falls within range"""
        if self.max_salary is None:
            return salary >= self.min_salary
        return self.min_salary <= salary <= self.max_salary
    
    def __str__(self) -> str:
        if self.max_salary:
            return f"${self.min_salary:,} - ${self.max_salary:,}"
        return f"${self.min_salary:,}+"
