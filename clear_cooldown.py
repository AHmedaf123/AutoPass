#!/usr/bin/env python3
"""
Clear user cooldown from LinkedIn session manager
Run this to bypass cooldown restrictions for testing
"""
import asyncio
import sys
from uuid import UUID

from application.services.linkedin_session_manager import get_session_manager
from core.logging_config import logger

async def clear_cooldown(user_id: str):
    """Clear cooldown for a user"""
    try:
        # Validate UUID
        try:
            UUID(user_id)
        except ValueError:
            logger.error(f"Invalid user_id format: {user_id}")
            return False
        
        session_manager = get_session_manager()
        
        # Check current cooldown status
        is_on_cooldown, cooldown_until = session_manager.is_user_on_cooldown(user_id)
        
        if is_on_cooldown:
            logger.info(f"User {user_id} is on cooldown until: {cooldown_until}")
            logger.info(f"Clearing cooldown...")
            
            # Clear from in-memory dict
            if user_id in session_manager.user_cooldowns:
                del session_manager.user_cooldowns[user_id]
                logger.info(f"✓ Cooldown cleared for user {user_id}")
                return True
        else:
            logger.info(f"User {user_id} is NOT on cooldown")
            return False
            
    except Exception as e:
        logger.error(f"Error clearing cooldown: {e}")
        return False

async def main():
    if len(sys.argv) < 2:
        print("Usage: python clear_cooldown.py <user_id>")
        print("Example: python clear_cooldown.py 550e8400-e29b-41d4-a716-446655440000")
        sys.exit(1)
    
    user_id = sys.argv[1]
    success = await clear_cooldown(user_id)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())
