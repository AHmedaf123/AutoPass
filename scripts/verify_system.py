import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from core.config import settings
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def verify_system():
    print("Verifying system configuration...")
    
    # Check Settings
    print(f"[-] Environment: {settings.ENVIRONMENT}")
    print(f"[-] Database URL found: {'Yes' if settings.DATABASE_URL else 'No'}")
    print(f"[-] Fernet Key found: {'Yes' if settings.FERNET_KEY else 'No'}")
    
    # Check Database Connection
    try:
        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("[+] Database connection successful!")
    except Exception as e:
        print(f"[!] Database connection failed: {e}")
        return False
        
    print("[+] System is ready for startup.")
    return True

if __name__ == "__main__":
    try:
        if not asyncio.run(verify_system()):
            sys.exit(1)
    except Exception as e:
        print(f"[!] Verification script failed: {e}")
        sys.exit(1)
