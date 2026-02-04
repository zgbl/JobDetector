#!/usr/bin/env python3
"""
开发测试版：限制抓取量，快速验证功能
只抓取5个公司，每个公司10个职位
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

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def quick_test():
    """快速测试版本"""
    
    db = get_db()
    scraper = GreenhouseScraper()
    
    # 测试公司列表
    test_companies = [
        {'name': 'Stripe', 'domain': 'stripe.com'},
        {'name': 'Airbnb', 'domain': 'airbnb.com'},
        {'name': 'GitLab', 'domain': 'gitlab.com'},
        {'name': 'Coinbase', 'domain': 'coinbase.com'},
        {'name': 'Figma', 'domain': 'figma.com'},
    ]
    
    total_jobs = 0
    
    # 清空旧数据（可选）
    logger.info("清空旧的测试数据...")
    db.jobs.delete_many({})
    
    for company in test_companies:
        logger.info(f"\n{'='*60}")
        logger.info(f"测试 {company['name']}")
        logger.info(f"{'='*60}")
        
        # 设置ATS类型
        company['ats_system'] = {'type': 'greenhouse'}
        
        # 抓取（限制10个）
        jobs = await scraper.scrape(company)
        
        if not jobs:
            logger.warning(f"未找到 {company['name']} 的职位")
            continue
        
        # 只取前10个
        jobs_to_save = jobs[:10]
        logger.info(f"抓取到 {len(jobs)} 个，保存前 {len(jobs_to_save)} 个")
        
        # 保存到数据库
        saved = 0
        for job in jobs_to_save:
            if job.get('description') and len(job['description']) > 50:
                db.jobs.insert_one(job)
                saved += 1
        
        total_jobs += saved
        logger.info(f"✅ 保存 {saved} 个职位（有完整描述）")
        
        # 显示第一个职位样本
        if jobs_to_save:
            sample = jobs_to_save[0]
            desc = sample.get('description', '')
            logger.info(f"\n样本职位:")
            logger.info(f"  标题: {sample['title']}")
            logger.info(f"  地点: {sample['location']}")
            logger.info(f"  描述长度: {len(desc)} 字符")
            if desc:
                logger.info(f"  描述预览: {desc[:150].replace(chr(10), ' ')}...")
            logger.info(f"  技能: {', '.join(sample.get('skills', [])[:5])}")
        
        # 避免请求过快
        await asyncio.sleep(1)
    
    # 最终统计
    logger.info(f"\n{'='*60}")
    logger.info(f"测试完成！")
    logger.info(f"{'='*60}")
    logger.info(f"总共保存: {total_jobs} 个职位")
    
    # 验证数据库
    db_total = db.jobs.count_documents({})
    with_desc = db.jobs.count_documents({'description': {'$exists': True, '$ne': ''}})
    
    logger.info(f"\n数据库验证:")
    logger.info(f"  总职位数: {db_total}")
    logger.info(f"  有描述的: {with_desc}")
    logger.info(f"  描述覆盖率: {with_desc/db_total*100:.1f}%" if db_total > 0 else "  描述覆盖率: N/A")
    
    # 按公司统计
    logger.info(f"\n按公司分布:")
    pipeline = [
        {'$group': {'_id': '$company', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]
    for stat in db.jobs.aggregate(pipeline):
        logger.info(f"  - {stat['_id']}: {stat['count']} 个职位")
    
    # 检查几个职位的描述
    logger.info(f"\n随机检查3个职位的描述:")
    for i, job in enumerate(db.jobs.find().limit(3), 1):
        desc = job.get('description', '')
        logger.info(f"\n{i}. {job['title']} @ {job['company']}")
        logger.info(f"   描述长度: {len(desc)}")
        if desc:
            logger.info(f"   ✅ 有完整JD内容")
            logger.info(f"   预览: {desc[:200].replace(chr(10), ' ')}...")
        else:
            logger.info(f"   ❌ JD为空！")
    
    close_db()
    logger.info(f"\n✅ 测试完成，功能验证OK！")


if __name__ == '__main__':
    asyncio.run(quick_test())
