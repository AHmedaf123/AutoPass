"""
Delete all jobs associated with a specific user_id
"""
import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from uuid import UUID
from sqlalchemy import text, delete
from core.database import AsyncSessionLocal
from infrastructure.persistence.models.user_job import UserJobModel


async def delete_jobs_by_user_id(user_id: str):
    """Delete all jobs associated with a specific user_id"""
    
    async_session = AsyncSessionLocal()
    try:
        user_uuid = UUID(user_id)
        
        # First, count how many jobs will be deleted
        count_query = text("""
            SELECT COUNT(*) FROM user_jobs WHERE user_id = :user_id
        """)
        
        result = await async_session.execute(count_query, {"user_id": user_uuid})
        count = result.scalar()
        
        print(f"Found {count} job(s) associated with user_id: {user_id}")
        
        if count == 0:
            print("No jobs to delete.")
            return
        
        # Show sample of jobs to be deleted
        sample_query = text("""
            SELECT uj.id, uj.status, uj.created_at, jl.title, jl.company
            FROM user_jobs uj
            JOIN job_listings jl ON uj.job_id = jl.id
            WHERE uj.user_id = :user_id
            LIMIT 5
        """)
        
        result = await async_session.execute(sample_query, {"user_id": user_uuid})
        samples = result.fetchall()
        
        print("\nSample of jobs to be deleted:")
        for i, row in enumerate(samples, 1):
            print(f"  {i}. {row[3]} at {row[4]} (Status: {row[1]}, Created: {row[2]})")
        
        if count > 5:
            print(f"  ... and {count - 5} more")
        
        # Confirm deletion
        print(f"\n⚠️  Auto-confirming deletion of ALL {count} jobs for this user...")
        
        # Perform deletion using SQLAlchemy ORM
        delete_stmt = delete(UserJobModel).where(UserJobModel.user_id == user_uuid)
        await async_session.execute(delete_stmt)
        await async_session.commit()
        
        print(f"\n✅ Successfully deleted {count} job(s) for user_id: {user_id}")
        
        # Verify deletion
        verify_query = text("""
            SELECT COUNT(*) FROM user_jobs WHERE user_id = :user_id
        """)
        
        result = await async_session.execute(verify_query, {"user_id": user_uuid})
        remaining = result.scalar()
        
        print(f"✓ Verification: {remaining} job(s) remaining for this user (should be 0)")
        
    except ValueError as e:
        print(f"❌ Invalid UUID format: {user_id}")
        print(f"   Error: {e}")
    except Exception as e:
        await async_session.rollback()
        print(f"❌ Error deleting jobs: {e}")
        raise
    finally:
        await async_session.close()


async def main():
    """Run deletion for specified user_id"""
    user_id = "80ab4bc5-0d49-48e2-8786-a8f2e07056cb"
    
    print("=" * 70)
    print("DELETE USER JOBS UTILITY")
    print("=" * 70)
    print(f"\nTarget User ID: {user_id}")
    print("\nThis will delete all jobs from the 'user_jobs' table for this user.")
    print("Note: Job listings in 'job_listings' table will remain (shared across users).")
    print()
    
    await delete_jobs_by_user_id(user_id)
    
    print("\n" + "=" * 70)
    print("Operation complete.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
