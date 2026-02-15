#!/usr/bin/env python
"""
Clear Database Cooldowns - Direct SQL Query

This script clears cooldown_until timestamps for all users so you can 
test the severity-based taint system without waiting for old cooldowns to expire.

Usage:
    python clear_cooldowns_direct.py
"""

import os
import sys
from datetime import datetime, timezone

# Load environment
from dotenv import load_dotenv
load_dotenv()

import psycopg2
from psycopg2.extras import DictCursor


def get_db_connection():
    """Get PostgreSQL connection from DATABASE_URL"""
    db_url = os.getenv("DATABASE_URL", "")
    
    if not db_url:
        print("❌ DATABASE_URL not found in .env")
        return None
    
    # Parse PostgreSQL URL
    # Format: postgresql://user:password@host:port/database
    try:
        # Remove postgresql:// prefix
        db_url_clean = db_url.replace("postgresql://", "").replace("postgresql+asyncpg://", "")
        
        # Parse components
        if "@" in db_url_clean:
            creds, host_db = db_url_clean.split("@")
            user, password = creds.split(":")
        else:
            user = "postgres"
            password = ""
            host_db = db_url_clean
        
        if "/" in host_db:
            host_port, database = host_db.split("/")
        else:
            host_port = host_db
            database = "auto_applier"
        
        if ":" in host_port:
            host, port = host_port.split(":")
            port = int(port)
        else:
            host = host_port
            port = 5432
        
        print(f"🔄 Connecting to {host}:{port}/{database}...")
        
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        return conn
    
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None


def clear_all_cooldowns():
    """Clear all user cooldowns"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # Check current cooldowns
            print("\n📊 Current cooldown status:")
            cur.execute("""
                SELECT id, email, cooldown_until, last_session_outcome
                FROM users
                WHERE cooldown_until IS NOT NULL
                AND cooldown_until > NOW() AT TIME ZONE 'UTC'
                ORDER BY cooldown_until DESC
            """)
            
            users = cur.fetchall()
            
            if users:
                print(f"   Found {len(users)} user(s) in cooldown:")
                for user in users:
                    remaining = (user['cooldown_until'] - datetime.now(timezone.utc)).total_seconds() / 3600
                    print(f"   - {user['email']}: {remaining:.1f}h remaining (reason: {user['last_session_outcome']})")
            else:
                print("   ✅ No users in cooldown")
                conn.close()
                return True
            
            # Clear all cooldowns
            print("\n🧹 Clearing all cooldowns...")
            cur.execute("""
                UPDATE users
                SET cooldown_until = NULL, last_session_outcome = NULL
                WHERE cooldown_until IS NOT NULL
            """)
            
            rows_updated = cur.rowcount
            conn.commit()
            
            print(f"   ✅ Cleared {rows_updated} user(s)")
            
            # Verify
            print("\n✅ Verification:")
            cur.execute("""
                SELECT COUNT(*) as count
                FROM users
                WHERE cooldown_until IS NOT NULL
                AND cooldown_until > NOW() AT TIME ZONE 'UTC'
            """)
            remaining_count = cur.fetchone()['count']
            print(f"   {remaining_count} user(s) still in cooldown")
            
            return True
    
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        return False
    
    finally:
        conn.close()


def clear_specific_user(user_id: str):
    """Clear cooldown for a specific user"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # Check user
            print(f"\n📊 Checking user: {user_id}")
            cur.execute("""
                SELECT id, email, cooldown_until, last_session_outcome
                FROM users
                WHERE id = %s
            """, (user_id,))
            
            user = cur.fetchone()
            
            if not user:
                print(f"❌ User not found: {user_id}")
                conn.close()
                return False
            
            print(f"   Email: {user['email']}")
            
            if user['cooldown_until'] and user['cooldown_until'] > datetime.now(timezone.utc):
                remaining = (user['cooldown_until'] - datetime.now(timezone.utc)).total_seconds() / 3600
                print(f"   Cooldown: {remaining:.1f}h remaining")
                print(f"   Reason: {user['last_session_outcome']}")
                
                # Clear cooldown
                print(f"\n🧹 Clearing cooldown for {user['email']}...")
                cur.execute("""
                    UPDATE users
                    SET cooldown_until = NULL, last_session_outcome = NULL
                    WHERE id = %s
                """, (user_id,))
                
                conn.commit()
                print("   ✅ Cooldown cleared!")
            else:
                print("   ✅ No active cooldown")
            
            return True
    
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        return False
    
    finally:
        conn.close()


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════════╗
║         Clear Database Cooldowns - Test Severity Fix           ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    if len(sys.argv) > 1:
        # Clear specific user
        user_id = sys.argv[1]
        success = clear_specific_user(user_id)
    else:
        # Clear all
        success = clear_all_cooldowns()
    
    print("\n" + ("✅ Done!\n" if success else "❌ Failed!\n"))
    sys.exit(0 if success else 1)
