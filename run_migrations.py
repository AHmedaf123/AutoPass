"""
Run database migrations for Indeed and Glassdoor credentials
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_async_engine(DATABASE_URL)


async def run_migrations():
    """Run migrations to add encrypted credential columns"""
    async with engine.begin() as conn:
        
        print("🔄 Checking existing columns...")
        
        # Check existing columns
        check_query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='users';
        """
        result = await conn.execute(text(check_query))
        existing_columns = [row[0] for row in result]
        
        print(f"✅ Found {len(existing_columns)} columns in users table")
        
        # Add encrypted_indeed_username
        if 'encrypted_indeed_username' not in existing_columns:
            print("➕ Adding encrypted_indeed_username...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN encrypted_indeed_username TEXT;
            """))
        else:
            print("✓ encrypted_indeed_username already exists")
        
        # Add encrypted_indeed_password
        if 'encrypted_indeed_password' not in existing_columns:
            print("➕ Adding encrypted_indeed_password...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN encrypted_indeed_password TEXT;
            """))
        else:
            print("✓ encrypted_indeed_password already exists")
        
        # Add encrypted_glassdoor_username
        if 'encrypted_glassdoor_username' not in existing_columns:
            print("➕ Adding encrypted_glassdoor_username...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN encrypted_glassdoor_username TEXT;
            """))
        else:
            print("✓ encrypted_glassdoor_username already exists")
        
        # Add encrypted_glassdoor_password
        if 'encrypted_glassdoor_password' not in existing_columns:
            print("➕ Adding encrypted_glassdoor_password...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN encrypted_glassdoor_password TEXT;
            """))
        else:
            print("✓ encrypted_glassdoor_password already exists")
        
        # Add google_user_id
        if 'google_user_id' not in existing_columns:
            print("➕ Adding google_user_id...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN google_user_id VARCHAR(255);
            """))
        else:
            print("✓ google_user_id already exists")
        
        # Add google_access_token
        if 'google_access_token' not in existing_columns:
            print("➕ Adding google_access_token...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN google_access_token TEXT;
            """))
        else:
            print("✓ google_access_token already exists")
        
        # Add google_refresh_token
        if 'google_refresh_token' not in existing_columns:
            print("➕ Adding google_refresh_token...")
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN google_refresh_token TEXT;
            """))
        else:
            print("✓ google_refresh_token already exists")
        
        print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migrations())
