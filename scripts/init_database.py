#!/usr/bin/env python3
"""
Database Initialization Script
Creates collections and indexes for JobDetector
"""
import sys
import os
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_collections():
    """创建所有需要的集合"""
    db = get_db()
    
    collections = [
        'companies',
        'jobs',
        'user_preferences',
        'job_matches',
        'scraper_logs'
    ]
    
    existing_collections = db.list_collection_names()
    
    for collection_name in collections:
        if collection_name not in existing_collections:
            db.create_collection(collection_name)
            logger.info(f"✅ Created collection: {collection_name}")
        else:
            logger.info(f"ℹ️  Collection already exists: {collection_name}")


def create_indexes():
    """创建索引以优化查询性能"""
    db = get_db()
    
    logger.info("Creating indexes...")
    
    # Companies collection indexes
    db.companies.create_index('domain', unique=True)
    db.companies.create_index('name')
    db.companies.create_index('is_active')
    db.companies.create_index([('metadata.tags', 1)])
    logger.info("✅ Created indexes for 'companies' collection")
    
    # Jobs collection indexes
    db.jobs.create_index('job_id', unique=True)
    db.jobs.create_index('source_url', unique=True)
    db.jobs.create_index([('scraped_at', -1)])
    db.jobs.create_index('company')
    db.jobs.create_index('location')
    db.jobs.create_index('skills')
    db.jobs.create_index([('posted_date', -1)])
    db.jobs.create_index([('is_active', 1), ('scraped_at', -1)])
    logger.info("✅ Created indexes for 'jobs' collection")
    
    # Job matches collection indexes
    db.job_matches.create_index('job_id')
    db.job_matches.create_index([('matched_at', -1)])
    db.job_matches.create_index([('is_notified', 1)])
    logger.info("✅ Created indexes for 'job_matches' collection")
    
    # Scraper logs collection indexes
    db.scraper_logs.create_index([('started_at', -1)])
    db.scraper_logs.create_index('source')
    db.scraper_logs.create_index('status')
    logger.info("✅ Created indexes for 'scraper_logs' collection")


def initialize_user_preferences():
    """初始化默认用户偏好（单用户模式）"""
    db = get_db()
    
    # Check if preferences already exist
    existing = db.user_preferences.find_one({})
    
    if not existing:
        default_preferences = {
            'user_email': os.getenv('EMAIL_USERNAME', 'your_email@gmail.com'),
            'keywords': ['python', 'backend', 'software engineer'],
            'exclude_keywords': ['junior', 'intern'],
            'locations': ['Remote', 'San Francisco', 'New York'],
            'min_salary': 100000,
            'job_types': ['Full-time', 'Contract'],
            'required_skills': ['Python'],
            'preferred_skills': ['AWS', 'Docker', 'Kubernetes'],
            'min_match_score': 60,
            'notification_enabled': True,
        }
        
        db.user_preferences.insert_one(default_preferences)
        logger.info("✅ Created default user preferences")
    else:
        logger.info("ℹ️  User preferences already exist")


def verify_database():
    """验证数据库设置"""
    db = get_db()
    
    logger.info("\n" + "="*50)
    logger.info("Database Verification")
    logger.info("="*50)
    
    # List all collections
    collections = db.list_collection_names()
    logger.info(f"Collections ({len(collections)}): {', '.join(collections)}")
    
    # Count documents in each collection
    for collection_name in collections:
        count = db[collection_name].count_documents({})
        logger.info(f"  - {collection_name}: {count} documents")
    
    # List indexes for each collection
    logger.info("\nIndexes:")
    for collection_name in ['companies', 'jobs', 'job_matches', 'scraper_logs']:
        if collection_name in collections:
            indexes = db[collection_name].list_indexes()
            index_names = [idx['name'] for idx in indexes]
            logger.info(f"  - {collection_name}: {', '.join(index_names)}")
    
    logger.info("="*50)
    logger.info("✅ Database initialization completed successfully!\n")


def main():
    """主函数"""
    try:
        logger.info("🚀 Starting database initialization...")
        
        # Step 1: Create collections
        logger.info("\n📦 Step 1: Creating collections...")
        create_collections()
        
        # Step 2: Create indexes
        logger.info("\n📊 Step 2: Creating indexes...")
        create_indexes()
        
        # Step 3: Initialize default data
        logger.info("\n⚙️  Step 3: Initializing default data...")
        initialize_user_preferences()
        
        # Step 4: Verify
        verify_database()
        
        logger.info("🎉 Database is ready to use!")
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        close_db()


if __name__ == '__main__':
    main()
