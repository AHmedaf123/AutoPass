import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Add backend to path
sys.path.append(os.getcwd())

from core.config import settings

async def check_port(port):
    # Construct URL with new port
    # Current: postgresql+asyncpg://postgres:itechgemini@localhost:5432/jobapplier
    original_url = settings.DATABASE_URL
    base_part = original_url.split('@')[0]
    # Reconstruct: protocol://user:pass + @localhost: + port + /dbname
    # Assuming the structure matches our .env
    
    # Simpler replace specific to our knowing localhost:5432 is in there
    if "localhost:5432" in original_url:
        target_url = original_url.replace("localhost:5432", f"localhost:{port}")
    else:
        print(f"Could not parse URL for port substitution: {original_url}")
        return False

    print(f"Checking port {port}...")
    
    try:
        engine = create_async_engine(target_url)
        async with engine.connect() as conn:
            # Try to select from a table or just check connection to the specific DB
            # If the DB exists, connection succeeds. 
            # If auth fails or db missing, it raises error.
            await conn.execute(text("SELECT 1"))
            print(f"[+] FOUND 'jobapplier' on port {port}!")
            return True
            
    except Exception as e:
        # print(f"[-] Port {port} failed: {e}")
        pass
    finally:
        await engine.dispose()
    
    return False

async def find_db():
    # Common ports for secondary postgres instances
    ports = [5433, 5434, 5435, 5436]
    
    for port in ports:
        if await check_port(port):
            print(f"\nSUCCESS: The PostgreSQL 18 instance with 'jobapplier' is likely on port {port}.")
            print(f"Please update your .env file to use port {port}.")
            return

    print("\n[-] Could not find 'jobapplier' on common ports (5433-5436).")
    print("Please check your PostgreSQL 18 configuration for the correct port number.")

if __name__ == "__main__":
    asyncio.run(find_db())
