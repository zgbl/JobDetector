#!/usr/bin/env python3
"""
测试单个职位的详细信息提取
"""
import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.scrapers.greenhouse import GreenhouseScraper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_single_job():
    """测试单个职位的详细信息"""
    scraper = GreenhouseScraper()
    
    company = {
        'name': 'Airbnb',
        'domain': 'airbnb.com',
        'ats_system': {'type': 'greenhouse'}
    }
    
    logger.info("测试：获取Airbnb的前3个职位详细信息...")
    jobs = await scraper.scrape(company)
    
    if jobs:
        # 只显示前3个
        for i, job in enumerate(jobs[:3], 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"职位 {i}: {job['title']}")
            logger.info(f"{'='*60}")
            logger.info(f"公司: {job['company']}")
            logger.info(f"地点: {job['location']}")
            logger.info(f"类型: {job['job_type']} / {job['remote_type']}")
            logger.info(f"URL: {job['source_url']}")
            
            # 检查描述
            desc = job.get('description', '')
            if desc:
                logger.info(f"✅ 描述长度: {len(desc)} 字符")
                logger.info(f"描述预览:\n{desc[:300]}...")
            else:
                logger.info(f"❌ 描述为空！")
            
            # 检查技能
            skills = job.get('skills', [])
            if skills:
                logger.info(f"✅ 技能: {', '.join(skills[:10])}")
            else:
                logger.info(f"⚠️  未提取到技能")
    else:
        logger.error("未获取到任何职位")


if __name__ == '__main__':
    asyncio.run(test_single_job())
