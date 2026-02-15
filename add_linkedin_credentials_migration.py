"""
Add linkedin_username and linkedin_password columns to users table
"""
import asyncio
from sqlalchemy import text
from core.database import engine


async def run_migration():
    """Add linkedin_username and linkedin_password columns to users table"""
    async with engine.begin() as conn:
        # Check if columns already exist
        check_query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='users' 
        AND column_name IN ('linkedin_username', 'linkedin_password');
        """
        result = await conn.execute(text(check_query))
        existing_columns = [row[0] for row in result]
        
        if 'linkedin_username' in existing_columns and 'linkedin_password' in existing_columns:
            print("✅ Columns already exist. Migration not needed.")
            return
        
        # Add linkedin_username column
        if 'linkedin_username' not in existing_columns:
            print("Adding linkedin_username column...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN linkedin_username VARCHAR(255);
            """))
            print("✅ linkedin_username column added")
        
        # Add linkedin_password column
        if 'linkedin_password' not in existing_columns:
            print("Adding linkedin_password column...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN linkedin_password VARCHAR(255);
            """))
            print("✅ linkedin_password column added")
        
        print("✅ Migration completed successfully!")


if __name__ == "__main__":
    print("🔄 Starting migration: Add linkedin_username and linkedin_password columns...")
    asyncio.run(run_migration())
    print("✅ Migration script finished.")
