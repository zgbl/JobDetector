#!/usr/bin/env python3
"""
Test Greenhouse Scraper
测试Greenhouse采集器，抓取几家公司的职位
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_single_company(scraper, company_name: str, domain: str):
    """测试单个公司"""
    company = {
        'name': company_name,
        'domain': domain,
        'ats_system': {'type': 'greenhouse'}
    }
    
    logger.info(f"\n{'='*60}")
    logger.info(f"测试公司: {company_name}")
    logger.info(f"{'='*60}")
    
    jobs = await scraper.scrape(company)
    
    if jobs:
        logger.info(f"✅ 成功抓取 {len(jobs)} 个职位\n")
        
        # 显示前3个职位
        for i, job in enumerate(jobs[:3], 1):
            logger.info(f"{i}. {job['title']}")
            logger.info(f"   地点: {job['location']}")
            logger.info(f"   类型: {job['job_type']} / {job['remote_type']}")
            if job['skills']:
                logger.info(f"   技能: {', '.join(job['skills'][:5])}")
            logger.info(f"   链接: {job['source_url']}\n")
        
        return jobs
    else:
        logger.warning(f"⚠️  未找到职位\n")
        return []


async def save_jobs_to_db(jobs: list):
    """保存职位到数据库"""
    if not jobs:
        return
    
    db = get_db()
    
    saved_count = 0
    skipped_count = 0
    
    for job in jobs:
        # 检查是否已存在
        existing = db.jobs.find_one({'job_id': job['job_id']})
        
        if not existing:
            db.jobs.insert_one(job)
            saved_count += 1
        else:
            # 更新scraped_at
            db.jobs.update_one(
                {'job_id': job['job_id']},
                {'$set': {'scraped_at': job['scraped_at']}}
            )
            skipped_count += 1
    
    logger.info(f"💾 数据库: 新增 {saved_count} 个, 已存在 {skipped_count} 个")


async def main():
    """主函数"""
    logger.info("🚀 开始测试 Greenhouse 采集器\n")
    
    scraper = GreenhouseScraper()
    
    # 测试几家公司
    test_companies = [
        ('Airbnb', 'airbnb.com'),
        ('Stripe', 'stripe.com'),
        ('Netflix', 'netflix.com'),
    ]
    
    all_jobs = []
    
    for company_name, domain in test_companies:
        jobs = await test_single_company(scraper, company_name, domain)
        all_jobs.extend(jobs)
        
        # 避免请求过快
        await asyncio.sleep(2)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"测试总结")
    logger.info(f"{'='*60}")
    logger.info(f"测试公司数: {len(test_companies)}")
    logger.info(f"总共抓取: {len(all_jobs)} 个职位")
    
    if all_jobs:
        # 保存到数据库
        logger.info(f"\n正在保存到数据库...")
        await save_jobs_to_db(all_jobs)
        
        # 显示数据库统计
        db = get_db()
        total_in_db = db.jobs.count_documents({})
        logger.info(f"📊 数据库中职位总数: {total_in_db}")
        
        # 按公司分组统计
        pipeline = [
            {'$group': {'_id': '$company', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        stats = list(db.jobs.aggregate(pipeline))
        
        logger.info(f"\n按公司统计:")
        for stat in stats:
            logger.info(f"  - {stat['_id']}: {stat['count']} 个职位")
    
    logger.info(f"\n✅ 测试完成!")
    
    close_db()


if __name__ == '__main__':
    asyncio.run(main())
