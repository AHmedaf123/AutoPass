"""
AI Match Service Interface
Calculates AI-powered job match scores using embeddings
"""
from abc import ABC, abstractmethod
from typing import List, Dict
from uuid import UUID

from domain.entities import JobListing
from domain.value_objects import MatchScore


class IAIMatchService(ABC):
    """AI match service interface"""
    
    @abstractmethod
    async def calculate_match_score(
        self,
        resume_text: str,
        job: JobListing
    ) -> MatchScore:
        """
        Calculate match score between resume and job
        
        Uses sentence embeddings and cosine similarity
        
        Args:
            resume_text: Parsed resume text
            job: Job entity
            
        Returns:
            MatchScore (0-100)
        """
        pass
    
    @abstractmethod
    async def batch_calculate_scores(
        self,
        resume_text: str,
        jobs: List[JobListing]
    ) -> Dict[UUID, MatchScore]:
        """
        Calculate match scores for multiple jobs (optimized)
        
        Args:
            resume_text: Parsed resume text
            jobs: List of Job entities
            
        Returns:
            Dict mapping job_id to MatchScore
        """
        pass
