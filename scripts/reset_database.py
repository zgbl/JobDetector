#!/usr/bin/env python3
"""
Database Reset Script
WARNING: This will delete all data in the database!
"""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def reset_database():
    """删除所有collections"""
    db = get_db()
    
    # Get user confirmation
    response = input("⚠️  WARNING: This will delete ALL data! Type 'yes' to continue: ")
    
    if response.lower() != 'yes':
        logger.info("Reset cancelled")
        return
    
    collections = db.list_collection_names()
    
    for collection_name in collections:
        db[collection_name].drop()
        logger.info(f"✅ Dropped collection: {collection_name}")
    
    logger.info("🗑️  Database reset completed")


if __name__ == '__main__':
    try:
        reset_database()
    finally:
        close_db()
