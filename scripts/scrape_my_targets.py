#!/usr/bin/env python3
import sys
import asyncio
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.workday import WorkdayScraper
from scripts.prod_scraper import scrape_company

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TargetScraper")

async def run_targeted_scrape():
    db = get_db()
    
    # Initialize scrapers
    scrapers = {
        'greenhouse': GreenhouseScraper(),
        'lever': LeverScraper(),
        'workday': WorkdayScraper()
    }
    
    # Find companies added by bulk_target_import
    query = {'metadata.added_by': 'bulk_target_import'}
    companies = list(db.companies.find(query))
    
    if not companies:
        logger.warning("No companies found with added_by='bulk_target_import'. Checking 'Personal Target' tag...")
        query = {'metadata.tags': 'Personal Target'}
        companies = list(db.companies.find(query))

    if not companies:
        logger.error("No target companies found to scrape.")
        return

    logger.info(f"🚀 Starting targeted scrape for {len(companies)} companies...")
    
    semaphore = asyncio.Semaphore(5)
    tasks = [scrape_company(company, scrapers, db, semaphore) for company in companies]
    
    results = await asyncio.gather(*tasks)
    
    total_new_jobs = sum(results)
    logger.info(f"🏁 Targeted scrape completed. Found {total_new_jobs} new jobs.")
    close_db()

if __name__ == "__main__":
    asyncio.run(run_targeted_scrape())
