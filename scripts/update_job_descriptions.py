#!/usr/bin/env python3
"""
简化版：更新Airbnb和Stripe的职位描述
"""
import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.scrapers.greenhouse import GreenhouseScraper
from src.database.connection import get_db, close_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def update_jobs():
    """更新Airbnb和Stripe的职位"""
    
    db = get_db()
    scraper = GreenhouseScraper()
    
    companies = [
        {'name': 'Airbnb', 'domain': 'airbnb.com', 'ats_system': {'type': 'greenhouse'}},
        {'name': 'Stripe', 'domain': 'stripe.com', 'ats_system': {'type': 'greenhouse'}},
    ]
    
    for company in companies:
        logger.info(f"\n{'='*60}")
        logger.info(f"更新 {company['name']}...")
        logger.info(f"{'='*60}")
        
        # 抓取
        jobs = await scraper.scrape(company)
        logger.info(f"抓取到 {len(jobs)} 个职位")
        
        updated = 0
        for job in jobs:
            if job.get('description') and len(job['description']) > 50:
                db.jobs.update_one(
                    {'job_id': job['job_id']},
                    {'$set': {
                        'description': job['description'],
                        'skills': job['skills']
                    }},
                    upsert=True
                )
                updated += 1
        
        logger.info(f"✅ 更新 {updated} 个职位")
        await asyncio.sleep(2)
    
    # 验证
    logger.info(f"\n{'='*60}")
    logger.info(f"验证数据库...")
    logger.info(f"{'='*60}")
    
    total = db.jobs.count_documents({})
    with_desc = db.jobs.count_documents({'description': {'$ne': ''}})
    
    logger.info(f"总职位: {total}")
    logger.info(f"有描述: {with_desc}")
    logger.info(f"覆盖率: {with_desc/total*100:.1f}%")
    
    # 样本
    logger.info(f"\n样本（前3个）:")
    for i, job in enumerate(db.jobs.find().limit(3), 1):
        desc = job.get('description', '')
        logger.info(f"{i}. {job['title']}")
        logger.info(f"   描述长度: {len(desc)} 字符")
        if desc:
            logger.info(f"   预览: {desc[:100]}...")
    
    close_db()


if __name__ == '__main__':
    asyncio.run(update_jobs())
