import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Add backend to path
sys.path.append(os.getcwd())

from core.config import settings

async def create_database():
    # Use default postgres DB to connect and create target DB
    # Extract connection info from settings.DATABASE_URL
    # Assuming standard format: postgresql+asyncpg://user:pass@host:port/dbname
    
    db_url = settings.DATABASE_URL
    # Replace dbname with postgres for initial connection
    base_url = db_url.rsplit('/', 1)[0] + '/postgres'
    target_db = db_url.rsplit('/', 1)[1]
    
    print(f"Connecting to {base_url} to create {target_db}...")
    
    engine = create_async_engine(base_url, isolation_level="AUTOCOMMIT")
    
    try:
        async with engine.connect() as conn:
            # Check if DB exists
            result = await conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname = '{target_db}'"))
            if result.scalar():
                print(f"Database {target_db} already exists.")
            else:
                print(f"Creating database {target_db}...")
                await conn.execute(text(f"CREATE DATABASE {target_db}"))
                print(f"Database {target_db} created successfully!")
    except Exception as e:
        print(f"Error creating database: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_database())
