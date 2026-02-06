#!/usr/bin/env python3
"""
Scrape New Companies Script
Scrapes only the companies added by the import script.
"""
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
logger = logging.getLogger("NewCompanyScraper")

async def run_targeted_scrape():
    db = get_db()
    
    # Initialize scrapers
    scrapers = {
        'greenhouse': GreenhouseScraper(),
        'lever': LeverScraper(),
        'workday': WorkdayScraper()
    }
    
    # Find companies added by import_script (newly added)
    # We can also filter by date if needed, but added_by is cleaner if unique to this batch
    query = {'metadata.added_by': 'import_script'}
    companies = list(db.companies.find(query))
    
    if not companies:
        logger.warning("No new companies found (added_by='import_script').")
        return

    logger.info(f"🚀 Starting scrape for {len(companies)} newly imported companies...")
    
    # Use semaphore
    semaphore = asyncio.Semaphore(10) # Higher concurrency for this batch
    
    tasks = [scrape_company(company, scrapers, db, semaphore) for company in companies]
    
    results = await asyncio.gather(*tasks)
    
    total_new_jobs = sum(results)
    logger.info(f"🏁 Scrape completed. Imported {total_new_jobs} new jobs from {len(companies)} companies.")
    close_db()

if __name__ == "__main__":
    asyncio.run(run_targeted_scrape())
