import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Add backend to path
sys.path.append(os.getcwd())

from core.config import settings

async def list_databases():
    # Connect to default postgres database to list others
    # Expected format: postgresql+asyncpg://user:pass@host:port/dbname
    db_url = settings.DATABASE_URL
    base_url = db_url.rsplit('/', 1)[0] + '/postgres'
    
    print(f"Connecting to {base_url}...")
    
    try:
        engine = create_async_engine(base_url)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate = false;"))
            dbs = [row[0] for row in result.fetchall()]
            
            print("\nAvailable Databases:")
            for db in dbs:
                print(f" - {db}")
                
            if 'jobapplier' in dbs:
                print("\n[+] 'jobapplier' database found!")
            else:
                print("\n[-] 'jobapplier' database NOT found.")
                
    except Exception as e:
        print(f"\n[!] Connection failed: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(list_databases())
