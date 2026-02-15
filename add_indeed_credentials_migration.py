"""
Manually run the Indeed credentials migration
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

import asyncio
from sqlalchemy import text
from core.database import engine


async def run_migration():
    """Add indeed_username and indeed_password columns to users table"""
    async with engine.begin() as conn:
        # Check if columns already exist
        check_query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='users'
        AND column_name IN ('indeed_username', 'indeed_password');
        """
        result = await conn.execute(text(check_query))
        existing_columns = [row[0] for row in result]

        if 'indeed_username' in existing_columns and 'indeed_password' in existing_columns:
            print("✅ Indeed columns already exist. Migration not needed.")
            return

        # Add indeed_username column
        if 'indeed_username' not in existing_columns:
            print("Adding indeed_username column...")
            await conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN indeed_username VARCHAR(255);
            """))
            print("✅ indeed_username column added")

        # Add indeed_password column
        if 'indeed_password' not in existing_columns:
            print("Adding indeed_password column...")
            await conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN indeed_password VARCHAR(255);
            """))
            print("✅ indeed_password column added")

        print("\n🎉 Indeed credentials migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migration())