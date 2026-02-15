"""
Email Value Object
Immutable email with validation
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Email:
    """Email value object with validation"""
    
    value: str
    
    def __post_init__(self):
        """Validate email format"""
        if not self.is_valid(self.value):
            raise ValueError(f"Invalid email format: {self.value}")
    
    @staticmethod
    def is_valid(email: str) -> bool:
        """Validate email using regex"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def __str__(self) -> str:
        return self.value
    
    def __repr__(self) -> str:
        return f"Email({self.value})"
