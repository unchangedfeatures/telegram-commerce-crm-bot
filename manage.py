#!/usr/bin/env python3
"""
Utility script for ParXpress management
Usage: python manage.py [command] [args]
"""

import asyncio
import sys
import os
from database.database import init_db, get_pool, close_pool
from dotenv import load_dotenv

load_dotenv()

async def init_database():
    """Initialize database"""
    print("🗄️  Initializing database...")
    await init_db()
    print("✅ Database initialized successfully")

async def check_database():
    """Check database connection"""
    print("🔍 Checking database connection...")
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT version()")
            print(f"✅ Database connected: {result[:50]}...")
        await close_pool()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)

async def create_admin(telegram_id: int, username: str):
    """Create admin user"""
    print(f"👤 Creating admin user {username} ({telegram_id})...")
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (telegram_id, username, role, is_subscribed, created_at)
                VALUES ($1, $2, 'admin', TRUE, NOW())
                ON CONFLICT (telegram_id) DO UPDATE
                SET role = 'admin'
            """, telegram_id, username)
        print(f"✅ Admin user created: @{username} ({telegram_id})")
        await close_pool()
    except Exception as e:
        print(f"❌ Failed to create admin: {e}")
        sys.exit(1)

async def list_admins():
    """List all admin users"""
    print("👥 List of admin users:")
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            admins = await conn.fetch("SELECT telegram_id, username FROM users WHERE role = 'admin'")
            if not admins:
                print("  No admins found")
            else:
                for admin in admins:
                    print(f"  - {admin['username']} ({admin['telegram_id']})")
        await close_pool()
    except Exception as e:
        print(f"❌ Failed to list admins: {e}")
        sys.exit(1)

async def check_env():
    """Check environment variables"""
    print("🔍 Checking environment variables...")
    required_vars = [
        "TOKEN",
        "ADMIN_ID",
        "CHAT_ID",
        "ORDERS_CHAT_ID",
        "USERNAME",
        "SUPPORT",
    ]
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        print(f"   Please check your .env file")
        sys.exit(1)
    else:
        print("✅ All required environment variables found")

async def main():
    if len(sys.argv) < 2:
        print("Usage: python manage.py [command] [args]")
        print("\nAvailable commands:")
        print("  init              Initialize database")
        print("  check-db          Check database connection")
        print("  check-env         Check environment variables")
        print("  create-admin      Create admin user (requires: telegram_id username)")
        print("  list-admins       List all admin users")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "init":
        await init_database()
    elif command == "check-db":
        await check_database()
    elif command == "check-env":
        await check_env()
    elif command == "create-admin":
        if len(sys.argv) < 4:
            print("Usage: python manage.py create-admin <telegram_id> <username>")
            sys.exit(1)
        await create_admin(int(sys.argv[2]), sys.argv[3])
    elif command == "list-admins":
        await list_admins()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
