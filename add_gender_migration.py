"""
Migration script to add gender column to users and job_preferences tables
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def run_migration():
    """Run the migration"""
    async with AsyncSessionLocal() as session:
        try:
            print("Starting migration: Adding gender column...")
            
            # Check if gender column exists in users table
            result = await session.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'users' AND column_name = 'gender'
                    )
                """)
            )
            gender_exists_users = result.scalar()
            
            if not gender_exists_users:
                print("Adding gender column to users table...")
                await session.execute(
                    text("""
                        ALTER TABLE users 
                        ADD COLUMN gender VARCHAR(20) NULL
                    """)
                )
                await session.execute(
                    text("""
                        COMMENT ON COLUMN users.gender IS 'Gender: Male, Female, Other'
                    """)
                )
                print("✅ Added gender column to users table")
            else:
                print("⚠️ gender column already exists in users table")
            
            # Check if gender column exists in job_preferences table
            result = await session.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'job_preferences' AND column_name = 'gender'
                    )
                """)
            )
            gender_exists_preferences = result.scalar()
            
            if not gender_exists_preferences:
                print("Adding gender column to job_preferences table...")
                await session.execute(
                    text("""
                        ALTER TABLE job_preferences 
                        ADD COLUMN gender VARCHAR(20) NULL
                    """)
                )
                await session.execute(
                    text("""
                        COMMENT ON COLUMN job_preferences.gender IS 'Gender: Male, Female, Other'
                    """)
                )
                print("✅ Added gender column to job_preferences table")
            else:
                print("⚠️ gender column already exists in job_preferences table")
            
            await session.commit()
            print("\n✅ Migration completed successfully!")
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_migration())
