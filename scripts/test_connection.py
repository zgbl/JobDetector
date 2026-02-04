#!/usr/bin/env python3
"""
Test script for database connection and basic operations
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_connection():
    """测试数据库连接"""
    try:
        db = get_db()
        logger.info("✅ Database connection successful")
        
        # Test a simple operation
        collections = db.list_collection_names()
        logger.info(f"📋 Collections: {collections}")
        
        # Count documents
        if 'companies' in collections:
            count = db.companies.count_documents({})
            logger.info(f"📊 Companies in database: {count}")
            
            if count > 0:
                # Show first company
                first_company = db.companies.find_one({})
                logger.info(f"📌 Sample company: {first_company.get('name')} ({first_company.get('domain')})")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False
    
    finally:
        close_db()


if __name__ == '__main__':
    success = test_connection()
    sys.exit(0 if success else 1)
