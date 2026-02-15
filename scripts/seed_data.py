"""
Seed Data Script
Populates database with test data for local development
"""
import asyncio
from uuid import uuid4
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import settings
from infrastructure.persistence.models.user import UserModel
from infrastructure.persistence.models.user_preferences import UserPreferencesModel
from infrastructure.persistence.models.job import JobModel
from domain.enums import Industry, WorkType, ApplicationStatus
from core.security import get_password_hash


async def seed_database():
    """Seed database with test data"""
    
    # Create async engine
    db_url = getattr(settings, 'DATABASE_URL', 'postgresql+asyncpg://admin:postgres@localhost:5432/jobapplier')
    engine = create_async_engine(db_url, echo=True)
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Create test users
        user1_id = uuid4()
        user1 = UserModel(
            id=user1_id,
            email="test@example.com",
            password_hash=get_password_hash("password123"),
            full_name="Test User",
            current_job_title="Software Developer",
            target_job_title="Senior Software Engineer",
            industry=Industry.TECHNOLOGY_IT.value,
            salary_expectation=120000,
            preferences_set=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        user2_id = uuid4()
        user2 = UserModel(
            id=user2_id,
            email="nurse@example.com",
            password_hash=get_password_hash("password123"),
            full_name="Healthcare Professional",
            current_job_title="Registered Nurse",
            target_job_title="Nurse Practitioner",
            industry=Industry.HEALTHCARE.value,
            salary_expectation=90000,
            preferences_set=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        session.add_all([user1, user2])
        
        # Create preferences for user1
        prefs1 = UserPreferencesModel(
            id=uuid4(),
            user_id=user1_id,
            job_titles=["Software Engineer", "Backend Developer", "Full Stack Developer"],
            locations=["San Francisco", "Remote", "New York"],
            work_types=[WorkType.REMOTE.value, WorkType.HYBRID.value],
            industries=[Industry.TECHNOLOGY_IT.value],
            subfields=[
                "Software Developers, Quality Assurance Analysts, and Testers",
                "Database Administrators and Architects",
                "Computer Systems Analysts"
            ],
            min_salary=120000,
            max_salary=180000,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Create preferences for user2
        prefs2 = UserPreferencesModel(
            id=uuid4(),
            user_id=user2_id,
            job_titles=["Registered Nurse", "Nurse Practitioner"],
            locations=["Boston", "New York", "Remote"],
            work_types=[WorkType.ONSITE.value, WorkType.HYBRID.value],
            industries=[Industry.HEALTHCARE.value],
            subfields=[
                "Registered Nurses",
                "Physician Assistants",
                "Physical Therapists"
            ],
            min_salary=80000,
            max_salary=120000,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        session.add_all([prefs1, prefs2])
        
        # Create test jobs for user1
        jobs_user1 = [
            JobModel(
                id=uuid4(),
                user_id=user1_id,
                title="Senior Software Engineer",
                company="Tech Corp",
                location="San Francisco, CA",
                description="We are seeking a Senior Software Engineer to join our platform team...",
                employment_type="full-time",
                experience_level="senior",
                industry=Industry.TECHNOLOGY_IT.value,
                subfields=["Software Developers, Quality Assurance Analysts, and Testers"],
                salary_min=150000,
                salary_max=200000,
                skills_required=["Python", "FastAPI", "PostgreSQL", "AWS", "Docker"],
                linkedin_url="https://linkedin.com/jobs/view/123456",
                work_type=WorkType.REMOTE.value,
                apply_status=None,
                created_at=datetime.utcnow()
            ),
            JobModel(
                id=uuid4(),
                user_id=user1_id,
                title="Backend Developer",
                company="Startup Inc",
                location="Remote",
                description="Join our growing team as a Backend Developer...",
                employment_type="full-time",
                experience_level="mid",
                industry=Industry.TECHNOLOGY_IT.value,
                subfields=["Software Developers, Quality Assurance Analysts, and Testers"],
                salary_min=120000,
                salary_max=160000,
                skills_required=["Python", "Django", "PostgreSQL", "Redis"],
                linkedin_url="https://linkedin.com/jobs/view/123457",
                work_type=WorkType.REMOTE.value,
                apply_status=ApplicationStatus.APPLIED.value,
                created_at=datetime.utcnow()
            ),
            JobModel(
                id=uuid4(),
                user_id=user1_id,
                title="Full Stack Engineer",
                company="Enterprise Co",
                location="New York, NY",
                description="Looking for a Full Stack Engineer with React and Node.js experience...",
                employment_type="full-time",
                experience_level="mid",
                industry=Industry.TECHNOLOGY_IT.value,
                subfields=["Software Developers, Quality Assurance Analysts, and Testers"],
                salary_min=130000,
                salary_max=170000,
                skills_required=["React", "Node.js", "TypeScript", "MongoDB"],
                linkedin_url="https://linkedin.com/jobs/view/123458",
                work_type=WorkType.HYBRID.value,
                apply_status=ApplicationStatus.PENDING.value,
                created_at=datetime.utcnow()
            )
        ]
        
        # Create test jobs for user2
        jobs_user2 = [
            JobModel(
                id=uuid4(),
                user_id=user2_id,
                title="Registered Nurse - ICU",
                company="General Hospital",
                location="Boston, MA",
                description="ICU Registered Nurse position available...",
                employment_type="full-time",
                experience_level="mid",
                industry=Industry.HEALTHCARE.value,
                subfields=["Registered Nurses"],
                salary_min=85000,
                salary_max=110000,
                skills_required=["Critical Care", "Patient Assessment", "EMR Systems"],
                linkedin_url="https://linkedin.com/jobs/view/223456",
                work_type=WorkType.ONSITE.value,
                apply_status=ApplicationStatus.APPLIED.value,
                created_at=datetime.utcnow()
            ),
            JobModel(
                id=uuid4(),
                user_id=user2_id,
                title="Nurse Practitioner",
                company="Community Health Center",
                location="New York, NY",
                description="Seeking experienced Nurse Practitioner for primary care...",
                employment_type="full-time",
                experience_level="senior",
                industry=Industry.HEALTHCARE.value,
                subfields=["Physician Assistants", "Registered Nurses"],
                salary_min=100000,
                salary_max=130000,
                skills_required=["Primary Care", "Patient Management", "Prescribing"],
                linkedin_url="https://linkedin.com/jobs/view/223457",
                work_type=WorkType.HYBRID.value,
                apply_status=None,
                created_at=datetime.utcnow()
            )
        ]
        
        session.add_all(jobs_user1 + jobs_user2)
        
        # Commit all
        await session.commit()
        
        print("✅ Database seeded successfully!")
        print(f"  - Created 2 users (test@example.com, nurse@example.com)")
        print(f"  - Created 2 preference sets with BLS subfields")
        print(f"  - Created 5 jobs with various statuses")
        print("\nTest credentials:")
        print("  Email: test@example.com | Password: password123")
        print("  Email: nurse@example.com | Password: password123")


if __name__ == "__main__":
    asyncio.run(seed_database())
