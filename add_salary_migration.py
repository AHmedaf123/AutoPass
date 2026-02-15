"""
Manually add salary columns to users and job_preferences tables
"""
import asyncio
from sqlalchemy import text
from core.database import engine


async def run_migration():
    """Add current_salary and desired_salary columns"""
    async with engine.begin() as conn:
        # Check if columns already exist in users table
        check_query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='users' 
        AND column_name IN ('current_salary', 'desired_salary');
        """
        result = await conn.execute(text(check_query))
        existing_users_columns = [row[0] for row in result]
        
        # Check if columns exist in job_preferences table
        check_prefs_query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='job_preferences' 
        AND column_name IN ('current_salary', 'desired_salary');
        """
        result = await conn.execute(text(check_prefs_query))
        existing_prefs_columns = [row[0] for row in result]
        
        # Add columns to users table
        if 'current_salary' not in existing_users_columns:
            print("Adding current_salary column to users table...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN current_salary INTEGER NULL
            """))
        else:
            print("✅ current_salary column already exists in users table")
        
        if 'desired_salary' not in existing_users_columns:
            print("Adding desired_salary column to users table...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN desired_salary INTEGER NULL
            """))
        else:
            print("✅ desired_salary column already exists in users table")
        
        # Add columns to job_preferences table
        if 'current_salary' not in existing_prefs_columns:
            print("Adding current_salary column to job_preferences table...")
            await conn.execute(text("""
                ALTER TABLE job_preferences 
                ADD COLUMN current_salary INTEGER NULL
            """))
        else:
            print("✅ current_salary column already exists in job_preferences table")
        
        if 'desired_salary' not in existing_prefs_columns:
            print("Adding desired_salary column to job_preferences table...")
            await conn.execute(text("""
                ALTER TABLE job_preferences 
                ADD COLUMN desired_salary INTEGER NULL
            """))
        else:
            print("✅ desired_salary column already exists in job_preferences table")
        
        print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migration())
