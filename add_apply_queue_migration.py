"""
Migration: Add ApplyQueue table for async task queue
Run this script to create the apply_queue table in your database
"""
import asyncio
from sqlalchemy import text

from core.database import get_db_session, engine
from core.logging_config import logger


async def create_apply_queue_table():
    """Create apply_queue table"""
    
    # SQL to create the table
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS apply_queue (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        job_url VARCHAR(1000),
        task_type VARCHAR(50) NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'pending',
        retries INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 3,
        current_step VARCHAR(255),
        progress_data TEXT,
        error_message TEXT,
        last_error_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP WITH TIME ZONE,
        completed_at TIMESTAMP WITH TIME ZONE
    );
    
    -- Create indexes for performance
    CREATE INDEX IF NOT EXISTS idx_apply_queue_user_id ON apply_queue(user_id);
    CREATE INDEX IF NOT EXISTS idx_apply_queue_task_type ON apply_queue(task_type);
    CREATE INDEX IF NOT EXISTS idx_apply_queue_status ON apply_queue(status);
    CREATE INDEX IF NOT EXISTS idx_apply_queue_created_at ON apply_queue(created_at);
    
    -- Create trigger to update updated_at timestamp
    CREATE OR REPLACE FUNCTION update_apply_queue_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    
    DROP TRIGGER IF EXISTS trigger_update_apply_queue_updated_at ON apply_queue;
    CREATE TRIGGER trigger_update_apply_queue_updated_at
        BEFORE UPDATE ON apply_queue
        FOR EACH ROW
        EXECUTE FUNCTION update_apply_queue_updated_at();
    """
    
    try:
        async with engine.begin() as conn:
            # Execute the SQL
            await conn.execute(text(create_table_sql))
            logger.info("✅ Successfully created apply_queue table and indexes")
            
    except Exception as e:
        logger.error(f"❌ Failed to create apply_queue table: {e}")
        raise


async def verify_table():
    """Verify the table was created successfully"""
    try:
        async with get_db_session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM apply_queue"))
            count = result.scalar()
            logger.info(f"✅ Table verification successful. Current row count: {count}")
            
    except Exception as e:
        logger.error(f"❌ Table verification failed: {e}")
        raise


async def main():
    """Main migration function"""
    logger.info("🚀 Starting migration: Add ApplyQueue table")
    
    try:
        # Create table
        await create_apply_queue_table()
        
        # Verify table
        await verify_table()
        
        logger.info("✅ Migration completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
