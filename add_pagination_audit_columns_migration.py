"""
Migration: Add Pagination & Audit Trail Columns to job_listings

Purpose:
- Add page_number column to track which page job was found on
- Add scraped_at column to track when job was scraped
- Create indexes for efficient filtering by page and timestamp
- Enable pagination auditing and performance analysis

This script is idempotent - safe to run multiple times.
"""

import asyncio
from sqlalchemy import text
from core.database import AsyncSessionLocal


async def add_pagination_columns():
    """Add pagination and audit trail columns to job_listings table"""
    
    async_session = AsyncSessionLocal()
    try:
        print("Adding pagination & audit trail columns to job_listings table...")
        
        # Add columns if they don't exist
        alter_table_query = text("""
            ALTER TABLE job_listings
            ADD COLUMN IF NOT EXISTS page_number INTEGER,
            ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMP WITH TIME ZONE;
        """)
        
        await async_session.execute(alter_table_query)
        await async_session.commit()
        print("✅ Columns added successfully")
        
        # Create indexes for efficient querying
        print("Creating indexes for pagination audit...")
        
        # Index on page_number
        page_index_query = text("""
            CREATE INDEX IF NOT EXISTS idx_job_listings_page_number 
            ON job_listings(page_number);
        """)
        await async_session.execute(page_index_query)
        print("✅ Index on page_number created")
        
        # Index on scraped_at
        scraped_index_query = text("""
            CREATE INDEX IF NOT EXISTS idx_job_listings_scraped_at 
            ON job_listings(scraped_at DESC);
        """)
        await async_session.execute(scraped_index_query)
        print("✅ Index on scraped_at created")
        
        # Composite index for pagination analysis
        composite_index_query = text("""
            CREATE INDEX IF NOT EXISTS idx_job_listings_page_scraped 
            ON job_listings(page_number, scraped_at DESC);
        """)
        await async_session.execute(composite_index_query)
        print("✅ Composite index on (page_number, scraped_at) created")
        
        await async_session.commit()
        return True
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        await async_session.rollback()
        return False
        
    finally:
        await async_session.close()


async def verify_columns():
    """Verify that columns were created successfully"""
    
    async_session = AsyncSessionLocal()
    try:
        check_columns_query = text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'job_listings'
            AND column_name IN ('page_number', 'scraped_at')
            ORDER BY column_name;
        """)
        
        result = await async_session.execute(check_columns_query)
        columns = result.fetchall()
        
        if columns:
            print("\n✓ Columns Created:")
            for col_name, data_type, is_nullable in columns:
                nullable = "nullable" if is_nullable == "YES" else "NOT NULL"
                print(f"  • {col_name}: {data_type} ({nullable})")
        else:
            print("⚠ Warning: Columns may not have been created properly")
        
        # Check indexes
        check_indexes_query = text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'job_listings'
            AND indexname LIKE '%page%' OR indexname LIKE '%scraped%'
            ORDER BY indexname;
        """)
        
        result = await async_session.execute(check_indexes_query)
        indexes = result.fetchall()
        
        if indexes:
            print("\n✓ Indexes Created:")
            for idx_name, idx_def in indexes:
                print(f"  • {idx_name}")
        
    except Exception as e:
        print(f"⚠ Warning: Could not verify columns: {e}")
        
    finally:
        await async_session.close()


async def show_statistics():
    """Show pagination statistics"""
    
    async_session = AsyncSessionLocal()
    try:
        stats_query = text("""
            SELECT
                COUNT(*) as total_jobs,
                COUNT(DISTINCT page_number) as pages_found,
                MIN(page_number) as first_page,
                MAX(page_number) as last_page,
                COUNT(CASE WHEN scraped_at IS NOT NULL THEN 1 END) as jobs_with_timestamp
            FROM job_listings
            WHERE page_number IS NOT NULL OR scraped_at IS NOT NULL;
        """)
        
        result = await async_session.execute(stats_query)
        stats = result.fetchone()
        
        if stats:
            total, pages, first_page, last_page, with_timestamp = stats
            print("\n✓ Pagination Statistics:")
            print(f"  • Total jobs with pagination data: {total}")
            print(f"  • Pages found: {pages}")
            print(f"  • Page range: {first_page}-{last_page}")
            print(f"  • Jobs with timestamp: {with_timestamp}")
        
    except Exception as e:
        print(f"⚠ Warning: Could not retrieve statistics: {e}")
        
    finally:
        await async_session.close()


async def main():
    """Run migration"""
    print("=" * 60)
    print("Migration: Add Pagination & Audit Trail Columns")
    print("=" * 60)
    print()
    
    success = await add_pagination_columns()
    
    if success:
        await verify_columns()
        await show_statistics()
        print()
        print("=" * 60)
        print("✅ Migration Complete - Pagination audit enabled")
        print("=" * 60)
        print()
        print("Benefits:")
        print("  • Track which page each job was found on")
        print("  • Record when each job was scraped")
        print("  • Analyze pagination patterns")
        print("  • Debug scraping issues with timestamps")
        print("  • Efficient queries with indexes")
    else:
        print()
        print("=" * 60)
        print("❌ Migration Failed")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
