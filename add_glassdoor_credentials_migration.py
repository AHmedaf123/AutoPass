"""
Manually run the Glassdoor credentials migration
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

import asyncio
from sqlalchemy import text
from core.database import engine


async def run_migration():
    """Add glassdoor_username and glassdoor_password columns to users table"""
    async with engine.begin() as conn:
        # Check if columns already exist
        check_query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='users'
        AND column_name IN ('glassdoor_username', 'glassdoor_password');
        """
        result = await conn.execute(text(check_query))
        existing_columns = [row[0] for row in result]

        if 'glassdoor_username' in existing_columns and 'glassdoor_password' in existing_columns:
            print("✅ Glassdoor columns already exist. Migration not needed.")
            return

        # Add glassdoor_username column
        if 'glassdoor_username' not in existing_columns:
            print("Adding glassdoor_username column...")
            await conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN glassdoor_username VARCHAR(255);
            """))
            print("✅ glassdoor_username column added")

        # Add glassdoor_password column
        if 'glassdoor_password' not in existing_columns:
            print("Adding glassdoor_password column...")
            await conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN glassdoor_password VARCHAR(255);
            """))
            print("✅ glassdoor_password column added")

        print("\n🎉 Glassdoor credentials migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migration())