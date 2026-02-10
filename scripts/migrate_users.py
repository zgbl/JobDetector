#!/usr/bin/env python3
"""
Migration script to add email verification fields to existing users
"""
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.db import get_db

def migrate_users():
    """Add is_verified field to existing users"""
    db = get_db()
    
    # Update all existing users to be verified (since they registered before this feature)
    result = db.users.update_many(
        {"is_verified": {"$exists": False}},  # Users without is_verified field
        {
            "$set": {
                "is_verified": True  # Mark existing users as verified
            }
        }
    )
    
    print(f"✅ Migration complete!")
    print(f"   Updated {result.modified_count} existing users")
    print(f"   All existing users are now marked as verified")
    
    # Show user count
    total_users = db.users.count_documents({})
    verified_users = db.users.count_documents({"is_verified": True})
    print(f"\n📊 User Statistics:")
    print(f"   Total users: {total_users}")
    print(f"   Verified users: {verified_users}")

if __name__ == "__main__":
    migrate_users()
