"""
JobListing Repository Implementation
"""
from typing import Optional, List, Any
from uuid import UUID
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from core.logging_config import logger
from infrastructure.persistence.models.job_listing import JobListingModel
from domain.entities.job_listing import JobListing
from datetime import datetime

class JobListingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, entity: JobListing) -> JobListing:
        return await self.create(entity)

    async def create(self, entity: JobListing) -> JobListing:
        """
        Create a new job listing with comprehensive duplicate prevention.
        
        Checks for duplicates by:
        1. external_id (LinkedIn job ID)
        2. title + company + description (semantic duplicates)
        
        Returns existing job if duplicate found, otherwise creates new job.
        """
        # Check 1: Duplicate by external_id
        if entity.external_id:
            existing = await self.get_by_external_id(entity.external_id, entity.platform or "linkedin")
            if existing:
                logger.debug(f"Job already exists with external_id={entity.external_id}, returning existing job")
                # Update last_seen_at to track activity
                await self.update_last_seen(existing.id)
                return existing
        
        # Check 2: Duplicate by title + company + description
        content_duplicate = await self.find_duplicate_by_content(
            title=entity.title,
            company=entity.company,
            description=entity.description or "",
            platform=entity.platform or "linkedin"
        )
        if content_duplicate:
            logger.info(f"Semantic duplicate found: '{entity.title}' at '{entity.company}' already exists as job_id={content_duplicate.id}")
            # Update last_seen_at to track this duplicate sighting
            await self.update_last_seen(content_duplicate.id)
            return content_duplicate
        
        # No duplicates found, create new job
        model = self._to_model(entity)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_external_id(self, external_id: str, platform: str = "linkedin") -> Optional[JobListing]:
        result = await self.session.execute(
            select(JobListingModel)
            .where(
                and_(
                    JobListingModel.platform == platform,
                    JobListingModel.external_id == external_id
                )
            )
            .order_by(JobListingModel.created_at.desc())
        )
        # Be tolerant to duplicates, pick the latest
        model = result.scalars().first()
        return self._to_entity(model) if model else None

    async def get_by_id(self, job_id: UUID) -> Optional[JobListing]:
        """Get job by its ID"""
        result = await self.session.execute(
            select(JobListingModel).where(JobListingModel.id == job_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_platform_and_external_id(self, platform: str, external_id: str) -> Optional[JobListingModel]:
        """Get JobListingModel by platform and external_id (for deduplication)."""
        result = await self.session.execute(
            select(JobListingModel).where(
                and_(
                    JobListingModel.platform == platform,
                    JobListingModel.external_id == external_id
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def exists_by_external_id(self, external_id: str, platform: str = "linkedin") -> bool:
        """
        Check if job exists by external_id (O(1) database lookup via index).
        
        Uses indexed external_id column for efficient duplicate detection.
        Replaces in-memory set checking for database truth.
        
        Args:
            external_id: LinkedIn job ID
            platform: Job platform (default: "linkedin")
            
        Returns:
            True if job exists, False otherwise
        """
        result = await self.session.execute(
            select(JobListingModel.id).where(
                and_(
                    JobListingModel.external_id == external_id,
                    JobListingModel.platform == platform
                )
            )
        )
        return result.scalar_one_or_none() is not None
    
    async def exists_by_url(self, url: str, platform: str = "linkedin") -> bool:
        """
        Check if job exists by URL (normalized by removing query parameters).
        
        Args:
            url: Job URL
            platform: Job platform (default: "linkedin")
            
        Returns:
            True if job exists, False otherwise
        """
        # Normalize URL by removing query parameters
        from urllib.parse import urlparse
        parsed = urlparse(url)
        normalized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        result = await self.session.execute(
            select(JobListingModel.id).where(
                and_(
                    JobListingModel.url == normalized_url,
                    JobListingModel.platform == platform
                )
            )
        )
        return result.scalar_one_or_none() is not None
    
    async def find_duplicate_by_content(self, title: str, company: str, description: str, platform: str = "linkedin") -> Optional[JobListing]:
        """
        Find duplicate job by matching title, company, and description.
        
        This prevents semantic duplicates where the same job appears with different external_ids.
        Useful for catching jobs that are reposted or have multiple IDs.
        
        Args:
            title: Job title (exact match, case-insensitive)
            company: Company name (exact match, case-insensitive)
            description: Job description (exact match)
            platform: Job platform (default: "linkedin")
            
        Returns:
            Existing JobListing if found, None otherwise
        """
        if not title or not company:
            return None
            
        try:
            # Strip and normalize for comparison
            title = title.strip()
            company = company.strip()
            
            result = await self.session.execute(
                select(JobListingModel).where(
                    and_(
                        JobListingModel.platform == platform,
                        JobListingModel.title.ilike(title),
                        JobListingModel.company.ilike(company),
                        JobListingModel.description == description
                    )
                ).order_by(JobListingModel.created_at.desc())
            )
            model = result.scalars().first()
            return self._to_entity(model) if model else None
        except Exception as e:
            logger.warning(f"Error checking for content duplicate: {e}")
            return None
    
    async def get_all_external_ids_by_platform(self, platform: str) -> set:
        """Get all external IDs for a platform (for efficient duplicate detection)."""
        try:
            result = await self.session.execute(
                select(JobListingModel.external_id).where(
                    JobListingModel.platform == platform
                )
            )
            return {row[0] for row in result.fetchall() if row[0]}
        except Exception as e:
            logger.warning(f"Failed to get existing external IDs: {e}")
            return set()

    async def update_last_seen(self, job_id: UUID) -> None:
        result = await self.session.execute(
            select(JobListingModel).where(JobListingModel.id == job_id)
        )
        model = result.scalar_one_or_none()
        if model:
            model.last_seen_at = datetime.utcnow()
            await self.session.flush()

    async def find_matching_jobs(self, titles: List[str], locations: List[str], limit: int = 100) -> List[JobListing]:
        """Find jobs matching titles OR locations"""
        if not titles and not locations:
            return []
            
        conditions = []
        if titles:
            title_conditions = [JobListingModel.title.ilike(f"%{t}%") for t in titles]
            conditions.append(or_(*title_conditions))
        
        # Location logic is simple substring match for now
        if locations:
            loc_conditions = [JobListingModel.location.ilike(f"%{l}%") for l in locations]
            conditions.append(or_(*loc_conditions))
            
        query = select(JobListingModel).where(or_(*conditions)).order_by(JobListingModel.created_at.desc()).limit(limit)
        
        result = await self.session.execute(query)
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    def _to_model(self, entity: JobListing) -> JobListingModel:
        return JobListingModel(
            id=entity.id,
            external_id=entity.external_id,
            platform=entity.platform or "linkedin",
            title=entity.title,
            company=entity.company,
            location=entity.location,
            description=entity.description,
            url=entity.url,
            salary_min=entity.salary_range.min_salary if entity.salary_range else getattr(entity, "salary_min", None),
            salary_max=entity.salary_range.max_salary if entity.salary_range else getattr(entity, "salary_max", None),
            work_type=entity.work_type.value if entity.work_type else None,
            posted_date=entity.posted_date,
            page_number=entity.page_number,
            scraped_at=entity.scraped_at,
            created_at=entity.first_seen_at, # Map entity.first_seen_at -> model.created_at
            last_seen_at=entity.last_seen_at
        )

    def _to_entity(self, model: JobListingModel) -> JobListing:
        from domain.enums import WorkType
        
        return JobListing(
            id=model.id,
            external_id=model.external_id,
            platform=model.platform,
            title=model.title,
            company=model.company,
            location=model.location,
            description=model.description,
            url=model.url,
            salary_range=None,
            work_type=WorkType(model.work_type) if model.work_type else None,
            posted_date=model.posted_date,
            page_number=model.page_number,
            scraped_at=model.scraped_at,
            first_seen_at=model.created_at, # Map model.created_at -> entity.first_seen_at
            last_seen_at=model.last_seen_at
        )
