#!/usr/bin/env python
"""
Clear Database Cooldowns - For Testing the Severity Taint Fix

This script clears cooldown_until timestamps for all users so you can 
test the severity-based taint system without waiting for the old cooldowns to expire.

Usage:
    python clear_cooldowns.py
"""

import asyncio
import sys
from datetime import datetime, timezone
from uuid import UUID

# Add backend to path
sys.path.insert(0, '/'.join(__file__.split('/')[:-1]))

from core.database import SessionLocal, engine, Base
from infrastructure.persistence.models.user import UserModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


async def clear_all_cooldowns():
    """Clear all user cooldowns from database"""
    
    # Get database URL from environment or .env
    from core.config import settings
    
    print("🔄 Connecting to database...")
    
    # Create async engine
    async_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=20,
        max_overflow=0,
    )
    
    AsyncSessionLocal = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with AsyncSessionLocal() as session:
        try:
            print("\n📊 Current cooldown status:")
            result = await session.execute(
                select(UserModel).where(UserModel.cooldown_until.isnot(None))
            )
            users_in_cooldown = result.scalars().all()
            
            if users_in_cooldown:
                print(f"   Found {len(users_in_cooldown)} user(s) in cooldown:")
                for user in users_in_cooldown:
                    remaining = user.cooldown_until - datetime.now(timezone.utc)
                    hours = remaining.total_seconds() / 3600
                    print(f"   - {user.email}: {hours:.1f}h remaining (reason: {user.last_session_outcome})")
            else:
                print("   ✅ No users in cooldown")
                return
            
            print("\n🧹 Clearing all cooldowns...")
            
            # Clear all cooldowns
            await session.execute(
                update(UserModel)
                .where(UserModel.cooldown_until.isnot(None))
                .values(
                    cooldown_until=None,
                    last_session_outcome=None
                )
            )
            
            await session.commit()
            
            print("   ✅ Cooldowns cleared!")
            
            # Verify
            result = await session.execute(
                select(UserModel).where(UserModel.cooldown_until.isnot(None))
            )
            remaining = result.scalars().all()
            print(f"\n✅ Verification: {len(remaining)} user(s) still in cooldown")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            await session.rollback()
            raise
        finally:
            await async_engine.dispose()


async def clear_specific_user(user_id: str):
    """Clear cooldown for a specific user"""
    
    from core.config import settings
    
    print(f"🔄 Connecting to database...")
    
    async_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=20,
        max_overflow=0,
    )
    
    AsyncSessionLocal = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with AsyncSessionLocal() as session:
        try:
            # Convert string to UUID
            try:
                user_uuid = UUID(user_id)
            except ValueError:
                print(f"❌ Invalid UUID: {user_id}")
                return
            
            print(f"\n📊 Checking user: {user_uuid}")
            result = await session.execute(
                select(UserModel).where(UserModel.id == user_uuid)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                print(f"❌ User not found: {user_uuid}")
                return
            
            print(f"   Email: {user.email}")
            
            if user.cooldown_until:
                remaining = user.cooldown_until - datetime.now(timezone.utc)
                hours = remaining.total_seconds() / 3600
                print(f"   Cooldown: {hours:.1f}h remaining")
                print(f"   Reason: {user.last_session_outcome}")
                
                print(f"\n🧹 Clearing cooldown for {user.email}...")
                user.cooldown_until = None
                user.last_session_outcome = None
                await session.commit()
                print("   ✅ Cooldown cleared!")
            else:
                print("   ✅ No cooldown active")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            await session.rollback()
            raise
        finally:
            await async_engine.dispose()


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════════╗
║         Clear Database Cooldowns - Test Severity Fix           ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    if len(sys.argv) > 1:
        # Clear specific user
        user_id = sys.argv[1]
        asyncio.run(clear_specific_user(user_id))
    else:
        # Clear all
        asyncio.run(clear_all_cooldowns())
    
    print("\n✅ Done!\n")
