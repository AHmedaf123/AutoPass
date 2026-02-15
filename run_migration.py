"""
Manually run the session lifecycle migration
"""
import asyncio
from sqlalchemy import text
from core.database import engine


async def run_migration():
    """Add cooldown_until and last_session_outcome columns to users table"""
    async with engine.begin() as conn:
        # Check if columns already exist
        check_query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='users' 
        AND column_name IN ('cooldown_until', 'last_session_outcome');
        """
        result = await conn.execute(text(check_query))
        existing_columns = [row[0] for row in result]
        
        if 'cooldown_until' in existing_columns and 'last_session_outcome' in existing_columns:
            print("✅ Columns already exist. Migration not needed.")
            return
        
        # Add cooldown_until column
        if 'cooldown_until' not in existing_columns:
            print("Adding cooldown_until column...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN cooldown_until TIMESTAMP WITH TIME ZONE;
            """))
            print("✅ cooldown_until column added")
        
        # Add last_session_outcome column
        if 'last_session_outcome' not in existing_columns:
            print("Adding last_session_outcome column...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN last_session_outcome VARCHAR(50);
            """))
            print("✅ last_session_outcome column added")
        
        # Create indexes
        print("Creating indexes...")
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_users_cooldown_until 
                ON users(cooldown_until);
            """))
            print("✅ Index on cooldown_until created")
        except Exception as e:
            print(f"⚠️ Index on cooldown_until might already exist: {e}")
        
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_users_last_session_outcome 
                ON users(last_session_outcome);
            """))
            print("✅ Index on last_session_outcome created")
        except Exception as e:
            print(f"⚠️ Index on last_session_outcome might already exist: {e}")
        
        print("\n🎉 Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migration())
