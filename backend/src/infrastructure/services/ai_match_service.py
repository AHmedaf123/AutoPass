"""
AIMatchService Implementation
Calculates AI-powered job match scores using sentence embeddings
"""
from typing import List, Dict
from uuid import UUID
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from application.services.ai_match import IAIMatchService
from domain.entities import JobListing
from domain.value_objects import MatchScore
from core.logging_config import logger
from core.config import settings


class AIMatchService(IAIMatchService):
    """AI match service implementation using sentence transformers"""
    
    def __init__(self):
        """Initialize AI match service and load model"""
        model_name = getattr(settings, 'AI_MODEL_NAME', 'sentence-transformers/all-MiniLM-L6-v2')
        logger.info(f"Loading sentence transformer model: {model_name}")
        
        try:
            self.model = SentenceTransformer(model_name)
            logger.info("Sentence transformer model loaded successfully")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise RuntimeError(f"Failed to load AI model: {str(e)}")
        
        # Cache for resume embeddings
        self._resume_embedding_cache: Dict[UUID, np.ndarray] = {}
    
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
        try:
            # Create job text representation
            job_text = self._create_job_text(job)
            
            # Generate embeddings
            resume_embedding = self.model.encode(resume_text, convert_to_numpy=True)
            job_embedding = self.model.encode(job_text, convert_to_numpy=True)
            
            # Calculate cosine similarity
            similarity = cosine_similarity(
                resume_embedding.reshape(1, -1),
                job_embedding.reshape(1, -1)
            )[0][0]
            
            # Convert to 0-100 scale
            # Cosine similarity is between -1 and 1, typically 0 to 1 for text
            # We'll map 0->0 and 1->100
            score = float(max(0, min(100, similarity * 100)))
            
            logger.debug(f"Calculated match score: {score:.2f} for job {job.id}")
            
            return MatchScore(value=score)
        
        except Exception as e:
            logger.error(f"Error calculating match score: {e}")
            # Return neutral score on error
            return MatchScore(value=50.0)
    
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
        try:
            if not jobs:
                return {}
            
            # Generate resume embedding once
            resume_embedding = self.model.encode(resume_text, convert_to_numpy=True)
            
            # Generate job texts and embeddings in batch
            job_texts = [self._create_job_text(job) for job in jobs]
            job_embeddings = self.model.encode(job_texts, convert_to_numpy=True, show_progress_bar=False)
            
            # Calculate cosine similarities
            similarities = cosine_similarity(
                resume_embedding.reshape(1, -1),
                job_embeddings
            )[0]
            
            # Convert to MatchScore objects
            scores = {}
            for job, similarity in zip(jobs, similarities):
                score = float(max(0, min(100, similarity * 100)))
                scores[job.id] = MatchScore(value=score)
            
            logger.info(f"Batch calculated {len(scores)} match scores")
            return scores
        
        except Exception as e:
            logger.error(f"Error in batch score calculation: {e}")
            # Return neutral scores for all jobs on error
            return {job.id: MatchScore(value=50.0) for job in jobs}
    
    def _create_job_text(self, job: JobListing) -> str:
        """
        Create concatenated text representation of job for embedding
        
        Args:
            job: Job entity
            
        Returns:
            Combined text from job fields
        """
        # Combine relevant fields
        parts = [
            f"Job Title: {job.title}",
            f"Company: {job.company}",
            f"Location: {job.location}",
        ]
        
        # Safely access fields that might be missing in JobListing vs Job
        industry = getattr(job, 'industry', None)
        if industry:
            parts.append(f"Industry: {industry}")
            
        emp_type = getattr(job, 'employment_type', None)
        if emp_type:
             parts.append(f"Employment Type: {emp_type}")
             
        exp_level = getattr(job, 'experience_level', None)
        if exp_level:
            parts.append(f"Experience Level: {exp_level}")
        
        # Add subfields if available
        subfields = getattr(job, 'subfields', None)
        if subfields:
            subfields_text = ", ".join(subfields)
            parts.append(f"Subfields: {subfields_text}")
        
        # Add description (truncate if too long)
        if job.description:
             description = job.description[:1000] if len(job.description) > 1000 else job.description
             parts.append(f"Description: {description}")
        
        # Add skills if available
        skills = getattr(job, 'skills_required', None)
        if skills:
            skills_text = ", ".join(skills[:10])  # Limit to 10 skills
            parts.append(f"Required Skills: {skills_text}")
        
        # Add work type if available
        if job.work_type:
            # work_type might be an Enum or None. In JobListing it's Optional[WorkType]
            try:
                wt = job.work_type.value
                parts.append(f"Work Type: {wt}")
            except AttributeError:
                pass # Or just str(job.work_type)
        
        return " ".join(parts)
    
    def cache_resume_embedding(self, user_id: UUID, resume_text: str) -> None:
        """
        Cache resume embedding for faster repeated calculations
        
        Args:
            user_id: User ID
            resume_text: Resume text to embed
        """
        try:
            embedding = self.model.encode(resume_text, convert_to_numpy=True)
            self._resume_embedding_cache[user_id] = embedding
            logger.debug(f"Cached resume embedding for user {user_id}")
        except Exception as e:
            logger.error(f"Error caching resume embedding: {e}")
    
    def get_cached_resume_embedding(self, user_id: UUID) -> np.ndarray:
        """Get cached resume embedding if available"""
        return self._resume_embedding_cache.get(user_id)
