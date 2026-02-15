"""
Job Filter Migration Script
Creates job_filters table for filter audit trail
"""
import asyncio
from sqlalchemy import text
from core.database import engine


async def create_job_filters_table():
    """Create job_filters table"""
    async with engine.begin() as conn:
        # Create job_filters table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS job_filters (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                filter_name VARCHAR(100) NOT NULL,
                filter_value VARCHAR(500) NOT NULL,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                task_id UUID,
                search_url VARCHAR(2000),
                job_title VARCHAR(255),
                verified VARCHAR(20) DEFAULT 'pending' NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            );
        """))
        
        # Create indexes
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_job_filters_user_id 
            ON job_filters(user_id);
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_job_filters_applied_at 
            ON job_filters(applied_at);
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_user_filter_applied 
            ON job_filters(user_id, filter_name, applied_at);
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_task_filters 
            ON job_filters(task_id, applied_at);
        """))
        
        print("✅ job_filters table created successfully")


async def main():
    """Run migration"""
    print("Creating job_filters table...")
    await create_job_filters_table()
    print("Migration complete!")


if __name__ == "__main__":
    asyncio.run(main())
