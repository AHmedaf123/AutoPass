"""
MatchScore Value Object
Type-safe AI match score with validation (0-100)
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MatchScore:
    """AI match score value object - immutable"""
    
    value: float
    
    def __post_init__(self):
        """Validate match score range"""
        if not isinstance(self.value, (int, float)):
            raise TypeError("Match score must be a number")
        
        if not 0 <= self.value <= 100:
            raise ValueError("Match score must be between 0 and 100")
    
    def is_good_match(self, threshold: float = 70.0) -> bool:
        """Check if score meets threshold for good match"""
        return self.value >= threshold
    
    def __float__(self) -> float:
        """Allow conversion to float"""
        return float(self.value)
    
    def __str__(self) -> str:
        return f"{self.value:.1f}%"
    
    def __repr__(self) -> str:
        return f"MatchScore({self.value})"
