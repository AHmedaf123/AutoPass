"""
Add unique constraint on user_jobs (user_id, job_id)
"""
import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from sqlalchemy import text
from core.database import engine


async def add_unique_constraint():
    """Add unique constraint on user_jobs table for (user_id, job_id)"""
    async with engine.begin() as conn:
        try:
            # Check if constraint already exists
            check_query = """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'user_jobs'
            AND constraint_type = 'UNIQUE'
            AND constraint_name = 'uq_user_jobs_user_id_job_id';
            """
            result = await conn.execute(text(check_query))
            existing = result.fetchone()
            
            if existing:
                print("✅ Unique constraint already exists.")
                return
            
            # First, clean up any remaining duplicates (just in case)
            print("🧹 Cleaning up any remaining duplicates...")
            cleanup_query = """
            DELETE FROM user_jobs
            WHERE id NOT IN (
                SELECT DISTINCT ON (user_id, job_id) id
                FROM user_jobs
                ORDER BY user_id, job_id, created_at DESC
            );
            """
            result = await conn.execute(text(cleanup_query))
            deleted = result.rowcount
            print(f"Deleted {deleted} duplicate entries")
            
            # Add unique constraint
            print("Adding unique constraint...")
            await conn.execute(text("""
                ALTER TABLE user_jobs
                ADD CONSTRAINT uq_user_jobs_user_id_job_id
                UNIQUE (user_id, job_id);
            """))
            
            print("✅ Unique constraint added successfully")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(add_unique_constraint())