#!/usr/bin/env python3
"""
Production Scraper Entry Point
Iterates through all companies in the database and runs the appropriate scraper.
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.workday import WorkdayScraper
from src.scrapers.ashby import AshbyScraper
from src.scrapers.workable import WorkableScraper
from src.services.language_filter import LanguageFilterService

# Ensure logs directory exists BEFORE logging configuration
Path("logs").mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/scraper_prod.log', encoding='utf-8')
    ]
)
logger = logging.getLogger("ProdScraper")

async def scrape_company(company, scrapers, db, semaphore):
    """抓取单个公司的职位"""
    async with semaphore:
        # Determine ATS type
        ats_type = None
        ats_url = company.get('ats_url')
        
        # 1. Try to detect from ATS URL
        if ats_url:
            if 'greenhouse.io' in ats_url:
                ats_type = 'greenhouse'
            elif 'lever.co' in ats_url:
                ats_type = 'lever'
            elif 'workday.com' in ats_url or 'myworkdayjobs.com' in ats_url:
                ats_type = 'workday'
            elif 'ashbyhq.com' in ats_url:
                ats_type = 'ashby'
            elif 'workable.com' in ats_url:
                ats_type = 'workable'
                
        # 2. Fallback to configured type
        if not ats_type:
            ats_info = company.get('ats_system', {})
            if isinstance(ats_info, dict):
                ats_type = ats_info.get('type')
        
        if not ats_type:
            logger.warning(f"跳过 {company['name']}: 未定义 ATS 类型且无法从 URL 识别")
            return 0
            
        scraper = scrapers.get(ats_type.lower())
        if not scraper:
            logger.warning(f"跳过 {company['name']}: 尚未实现 '{ats_type}' 的抓取器")
            return 0
            
        try:
            logger.info(f"正在抓取 {company['name']} (使用 {ats_type})...")
            jobs = await scraper.scrape(company)
            
            if jobs:
                # Save/Update jobs in DB
                saved_count = 0
                for job in jobs:
                    # 0. Content analysis (English-Only & IT-Only check)
                    job_text = job.get('description', '') + ' ' + job.get('title', '')
                    
                    # A. Category Check (IT Only)
                    is_it, it_reason = LanguageFilterService.is_it_role(job['title'], is_title=True) # Prioritize title for category
                    if not is_it:
                        # Fallback to description if title is ambiguous
                        is_it_desc, it_reason_desc = LanguageFilterService.is_it_role(job_text, is_title=False)
                        if not is_it_desc:
                            logger.info(f"🚫 {company['name']}: 职位 '{job['title']}' 非 IT 职位被过滤: {it_reason_desc}")
                            db.rejected_jobs.update_one(
                                {'content_hash': job['content_hash']},
                                {'$set': {'title': job['title'], 'company': job['company'], 'rejected_at': datetime.utcnow(), 'reason': f"Non-IT: {it_reason_desc}"}},
                                upsert=True
                            )
                            continue

                    # B. Language Check (English Only)
                    is_eng, eng_reason = LanguageFilterService.is_english_only(job_text)
                    if not is_eng:
                        logger.info(f"🚫 {company['name']}: 职位 '{job['title']}' 因要求日语被过滤: {eng_reason}")
                        db.rejected_jobs.update_one(
                            {'content_hash': job['content_hash']},
                            {'$set': {'title': job['title'], 'company': job['company'], 'rejected_at': datetime.utcnow(), 'reason': f"Language: {eng_reason}"}},
                            upsert=True
                        )
                        continue

                    # 0.5 Check if already rejected
                    if db.rejected_jobs.find_one({'content_hash': job['content_hash']}):
                        logger.debug(f"⏭️ {company['name']}: 跳过已知不符合要求的职位 '{job['title']}'")
                        continue

                    # 1. 查找现有职位
                    existing_job = db.jobs.find_one({'job_id': job['job_id']})
                    
                    if existing_job:
                        # 2. 如果存在，检查哈希值是否一致
                        if existing_job.get('content_hash') == job.get('content_hash'):
                            # 哈希一致，只更新 last_seen_at
                            db.jobs.update_one(
                                {'job_id': job['job_id']},
                                {'$set': {'last_seen_at': job['last_seen_at'], 'is_active': True}}
                            )
                        else:
                            # 哈希不一致，全量更新
                            db.jobs.update_one(
                                {'job_id': job['job_id']},
                                {'$set': job},
                                upsert=True
                            )
                            saved_count += 1
                    else:
                        # 3. 如果不存在，直接插入
                        db.jobs.insert_one(job)
                        saved_count += 1
                
                logger.info(f"✅ {company['name']}: 处理完成。新增/更新: {saved_count}，跳过: {len(jobs) - saved_count}")
                return saved_count
            else:
                logger.info(f"ℹ️ {company['name']}: 未找到职位")
                return 0
                
        except Exception as e:
            logger.error(f"❌ 抓取 {company['name']} 失败: {e}")
            return 0

async def run_production_scrape():
    db = get_db()
    
    # Initialize scrapers
    scrapers = {
        'greenhouse': GreenhouseScraper(),
        'lever': LeverScraper(),
        'workday': WorkdayScraper(),
        'ashby': AshbyScraper(),
        'workable': WorkableScraper(),
    }
    
    # 1. Fetch all companies from DB
    companies = list(db.companies.find({}))
    if not companies:
        logger.warning("数据库中没有公司信息。请先运行 scripts/import_companies.py")
        return

    logger.info(f"🚀 开始为 {len(companies)} 家公司进行生产抓取...")
    
    # 使用信号量限制并发数，避免被封禁
    semaphore = asyncio.Semaphore(5)
    
    # 创建所有抓取任务
    tasks = [scrape_company(company, scrapers, db, semaphore) for company in companies]
    
    # 并行运行
    results = await asyncio.gather(*tasks)
    
    total_new_jobs = sum(results)

    logger.info(f"🏁 生产抓取完成。总计更新/新增: {total_new_jobs} 个职位")
    close_db()

if __name__ == "__main__":
    asyncio.run(run_production_scrape())
