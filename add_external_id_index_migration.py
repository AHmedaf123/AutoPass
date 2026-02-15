"""
Migration: Add Index on job_listings.external_id for O(1) Duplicate Detection

Purpose: 
- Add index on external_id column for efficient duplicate checking
- Enables O(1) lookups in _process_and_publish_job() method
- Replaces slow full-table scan with indexed query

This script is idempotent - safe to run multiple times.
"""

import asyncio
from sqlalchemy import text
from core.database import AsyncSessionLocal


async def add_external_id_index():
    """Add index on job_listings.external_id if it doesn't exist"""
    
    async_session = AsyncSessionLocal()
    try:
        # Create index (idempotent - IF NOT EXISTS)
        create_index_query = text("""
            CREATE INDEX IF NOT EXISTS idx_job_listings_external_id 
            ON job_listings(external_id);
        """)
        
        await async_session.execute(create_index_query)
        await async_session.commit()
        
        print("✅ Index created successfully on job_listings.external_id")
        
        # Verify index was created
        check_index_query = text("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'job_listings' 
            AND indexname = 'idx_job_listings_external_id';
        """)
        
        result = await async_session.execute(check_index_query)
        index_info = result.fetchone()
        
        if index_info:
            print(f"\n✓ Index Details:")
            print(f"  Name: {index_info[0]}")
            print(f"  Definition: {index_info[1]}")
        else:
            print("⚠ Warning: Index may not have been created properly")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating index: {e}")
        return False
        
    finally:
        await async_session.close()


async def verify_index_performance():
    """Verify that the index enables efficient lookups"""
    
    async_session = AsyncSessionLocal()
    try:
        # Check index usage stats
        check_stats_query = text("""
            SELECT 
                schemaname,
                tablename,
                indexname,
                idx_scan as index_scans,
                idx_tup_read as tuples_read,
                idx_tup_fetch as tuples_fetched
            FROM pg_stat_user_indexes
            WHERE tablename = 'job_listings'
            AND indexname = 'idx_job_listings_external_id';
        """)
        
        result = await async_session.execute(check_stats_query)
        stats = result.fetchone()
        
        if stats:
            print(f"\n✓ Index Performance Stats:")
            print(f"  Schema: {stats[0]}")
            print(f"  Table: {stats[1]}")
            print(f"  Index: {stats[2]}")
            print(f"  Index Scans: {stats[3]}")
            print(f"  Tuples Read: {stats[4]}")
            print(f"  Tuples Fetched: {stats[5]}")
        
    except Exception as e:
        print(f"⚠ Warning: Could not retrieve index stats: {e}")
        
    finally:
        await async_session.close()


async def main():
    """Run migration"""
    print("=" * 60)
    print("Migration: Add Index on job_listings.external_id")
    print("=" * 60)
    print()
    
    success = await add_external_id_index()
    
    if success:
        await verify_index_performance()
        print()
        print("=" * 60)
        print("✅ Migration Complete - Duplicate detection optimized")
        print("=" * 60)
        print()
        print("Benefits:")
        print("  • O(1) lookup time for exists_by_external_id()")
        print("  • No full-table scans during duplicate checking")
        print("  • Efficient resource usage during scraping")
        print("  • Better performance with large job listings table")
    else:
        print()
        print("=" * 60)
        print("❌ Migration Failed")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
