"""
Clean up duplicate user_jobs entries
Keep only the latest entry per user-job pair
"""
import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from sqlalchemy import text, delete
from core.database import AsyncSessionLocal
from infrastructure.persistence.models.user_job import UserJobModel


async def cleanup_duplicate_user_jobs():
    """Remove duplicate user_jobs, keeping only the latest per user-job pair"""
    
    async_session = AsyncSessionLocal()
    try:
        print("🔍 Finding duplicate user_jobs...")
        
        # Find duplicates: user-job pairs with more than one entry
        duplicates_query = text("""
            SELECT user_id, job_id, COUNT(*) as count
            FROM user_jobs
            GROUP BY user_id, job_id
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        """)
        
        result = await async_session.execute(duplicates_query)
        duplicates = result.fetchall()
        
        print(f"Found {len(duplicates)} duplicate user-job pairs")
        
        total_deleted = 0
        
        for user_id, job_id, count in duplicates:
            print(f"  Cleaning user {user_id}, job {job_id}: {count} entries")
            
            # Keep the latest (by created_at), delete others
            keep_query = text("""
                SELECT id FROM user_jobs
                WHERE user_id = :user_id AND job_id = :job_id
                ORDER BY created_at DESC
                LIMIT 1
            """)
            
            result = await async_session.execute(keep_query, {"user_id": user_id, "job_id": job_id})
            keep_id = result.scalar()
            
            # Delete all except the one to keep
            delete_stmt = delete(UserJobModel).where(
                (UserJobModel.user_id == user_id) & 
                (UserJobModel.job_id == job_id) & 
                (UserJobModel.id != keep_id)
            )
            
            result = await async_session.execute(delete_stmt)
            deleted = result.rowcount
            total_deleted += deleted
            
            print(f"    Kept {keep_id}, deleted {deleted} duplicates")
        
        await async_session.commit()
        print(f"\n✅ Cleanup complete! Deleted {total_deleted} duplicate entries")
        
        # Verify
        verify_query = text("""
            SELECT COUNT(*) FROM (
                SELECT user_id, job_id, COUNT(*)
                FROM user_jobs
                GROUP BY user_id, job_id
                HAVING COUNT(*) > 1
            ) as dupes
        """)
        
        result = await async_session.execute(verify_query)
        remaining_dupes = result.scalar()
        
        print(f"✓ Remaining duplicate pairs: {remaining_dupes} (should be 0)")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        await async_session.rollback()
    finally:
        await async_session.close()


if __name__ == "__main__":
    asyncio.run(cleanup_duplicate_user_jobs())