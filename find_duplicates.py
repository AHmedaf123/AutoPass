"""
Find and Report Duplicate Jobs in Database
Identifies duplicates by:
1. external_id (should be impossible with unique constraint, but checks anyway)
2. title + company + description (semantic duplicates)
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func, and_
from infrastructure.persistence.models.job_listing import JobListingModel
from core.logging_config import logger
from collections import defaultdict

# Database URL
DB_URL = "postgresql+asyncpg://postgres:password@localhost:5432/linkedin_applier"

async def find_duplicates():
    """Find and report all duplicates in the database"""
    
    engine = create_async_engine(DB_URL, echo=False)
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        try:
            logger.info("\n" + "="*70)
            logger.info("DUPLICATE JOB DETECTION REPORT")
            logger.info("="*70)
            
            # Check 1: Duplicates by external_id
            logger.info("\n📊 Check 1: Duplicates by external_id")
            logger.info("-" * 70)
            
            result = await session.execute(
                select(
                    JobListingModel.external_id,
                    func.count(JobListingModel.id).label('count')
                )
                .where(JobListingModel.external_id.isnot(None))
                .group_by(JobListingModel.external_id)
                .having(func.count(JobListingModel.id) > 1)
                .order_by(func.count(JobListingModel.id).desc())
            )
            
            external_id_duplicates = result.fetchall()
            
            if external_id_duplicates:
                logger.warning(f"⚠️  Found {len(external_id_duplicates)} external_id duplicates (this should not happen!)")
                
                for external_id, count in external_id_duplicates[:10]:  # Show top 10
                    # Get details of these jobs
                    jobs_result = await session.execute(
                        select(JobListingModel)
                        .where(JobListingModel.external_id == external_id)
                        .order_by(JobListingModel.created_at)
                    )
                    jobs = jobs_result.scalars().all()
                    
                    logger.info(f"\n  external_id: {external_id} (appears {count} times)")
                    for idx, job in enumerate(jobs, 1):
                        logger.info(f"    [{idx}] Job ID: {job.id}")
                        logger.info(f"        Title: {job.title}")
                        logger.info(f"        Company: {job.company}")
                        logger.info(f"        Created: {job.created_at}")
            else:
                logger.info("✅ No external_id duplicates found!")
            
            # Check 2: Semantic duplicates (title + company)
            logger.info("\n📊 Check 2: Semantic Duplicates (Title + Company)")
            logger.info("-" * 70)
            
            # Get all jobs
            all_jobs_result = await session.execute(
                select(JobListingModel)
                .where(
                    and_(
                        JobListingModel.title.isnot(None),
                        JobListingModel.company.isnot(None),
                        JobListingModel.title != '',
                        JobListingModel.company != ''
                    )
                )
            )
            all_jobs = all_jobs_result.scalars().all()
            
            # Group by normalized title + company
            semantic_groups = defaultdict(list)
            for job in all_jobs:
                key = (
                    job.title.strip().lower(),
                    job.company.strip().lower()
                )
                semantic_groups[key].append(job)
            
            # Find groups with duplicates
            semantic_duplicates = {k: v for k, v in semantic_groups.items() if len(v) > 1}
            
            if semantic_duplicates:
                logger.warning(f"⚠️  Found {len(semantic_duplicates)} semantic duplicate groups")
                
                # Sort by count (most duplicates first)
                sorted_duplicates = sorted(semantic_duplicates.items(), key=lambda x: len(x[1]), reverse=True)
                
                for (title, company), jobs in sorted_duplicates[:10]:  # Show top 10
                    logger.info(f"\n  \"{title}\" at \"{company}\" (appears {len(jobs)} times)")
                    
                    for idx, job in enumerate(jobs, 1):
                        logger.info(f"    [{idx}] Job ID: {job.id}")
                        logger.info(f"        external_id: {job.external_id}")
                        logger.info(f"        Created: {job.created_at}")
                        logger.info(f"        Description length: {len(job.description or '')} chars")
                        
                        # Check if descriptions match
                        if idx > 1:
                            if job.description == jobs[0].description:
                                logger.info(f"        ⚠️  EXACT DUPLICATE (same description)")
                            else:
                                logger.info(f"        ℹ️  Different description (might be re-post)")
            else:
                logger.info("✅ No semantic duplicates found!")
            
            # Check 3: Jobs with missing titles or companies
            logger.info("\n📊 Check 3: Jobs with Missing Data")
            logger.info("-" * 70)
            
            missing_data_result = await session.execute(
                select(func.count(JobListingModel.id))
                .where(
                    or_(
                        JobListingModel.title.is_(None),
                        JobListingModel.title == '',
                        JobListingModel.company.is_(None),
                        JobListingModel.company == ''
                    )
                )
            )
            missing_count = missing_data_result.scalar()
            
            if missing_count > 0:
                logger.warning(f"⚠️  Found {missing_count} jobs with missing title or company")
                
                # Get examples
                examples_result = await session.execute(
                    select(JobListingModel)
                    .where(
                        or_(
                            JobListingModel.title.is_(None),
                            JobListingModel.title == '',
                            JobListingModel.company.is_(None),
                            JobListingModel.company == ''
                        )
                    )
                    .limit(5)
                )
                examples = examples_result.scalars().all()
                
                for job in examples:
                    logger.info(f"  Job ID: {job.id}")
                    logger.info(f"    Title: '{job.title}'")
                    logger.info(f"    Company: '{job.company}'")
                    logger.info(f"    external_id: {job.external_id}")
            else:
                logger.info("✅ All jobs have title and company!")
            
            # Summary
            logger.info("\n" + "="*70)
            logger.info("SUMMARY")
            logger.info("="*70)
            logger.info(f"Total jobs in database: {len(all_jobs)}")
            logger.info(f"External ID duplicates: {len(external_id_duplicates)}")
            logger.info(f"Semantic duplicates: {len(semantic_duplicates)}")
            logger.info(f"Jobs with missing data: {missing_count}")
            
            if len(external_id_duplicates) == 0 and len(semantic_duplicates) == 0:
                logger.info("\n✅ Database is clean! No duplicates found.")
            else:
                logger.info("\n⚠️  Duplicates detected. Consider cleaning them up.")
            
        except Exception as e:
            logger.error(f"❌ Error during duplicate detection: {e}")
            raise
        finally:
            await session.close()
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(find_duplicates())
