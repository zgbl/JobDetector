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

# Ensure logs directory exists
Path("logs").mkdir(exist_ok=True)

async def run_production_scrape():
    db = get_db()
    
    # Initialize scrapers
    scrapers = {
        'greenhouse': GreenhouseScraper(),
        'lever': LeverScraper()
    }
    
    # 1. Fetch all companies from DB
    companies = list(db.companies.find({}))
    if not companies:
        logger.warning("No companies found in database. Please run scripts/import_companies.py first.")
        return

    logger.info(f"🚀 Starting production scrape for {len(companies)} companies...")
    
    total_new_jobs = 0
    
    for company in companies:
        # Determine ATS type
        ats_type = None
        ats_info = company.get('ats_system', {})
        if isinstance(ats_info, dict):
            ats_type = ats_info.get('type')
        
        # If not specified, we can try to skip or auto-detect later
        if not ats_type:
            logger.warning(f"Skipping {company['name']}: No ATS type defined.")
            continue
            
        scraper = scrapers.get(ats_type.lower())
        if not scraper:
            logger.warning(f"Skipping {company['name']}: Scraper for '{ats_type}' not implemented yet.")
            continue
            
        try:
            logger.info(f"Scraping {company['name']} using {ats_type}...")
            jobs = await scraper.scrape(company)
            
            if jobs:
                # Save/Update jobs in DB
                saved_count = 0
                for job in jobs:
                    # Upsert based on job_id
                    result = db.jobs.update_one(
                        {'job_id': job['job_id']},
                        {'$set': job},
                        upsert=True
                    )
                    if result.upserted_id or result.modified_count > 0:
                        saved_count += 1
                
                total_new_jobs += saved_count
                logger.info(f"✅ {company['name']}: Saved/Updated {saved_count} jobs.")
            else:
                logger.info(f"ℹ️ {company['name']}: No jobs found.")
                
        except Exception as e:
            logger.error(f"❌ Failed to scrape {company['name']}: {e}")
            
        # Rate limiting to be polite
        await asyncio.sleep(2)

    logger.info(f"🏁 Production scrape finished. Total updates: {total_new_jobs}")
    close_db()

if __name__ == "__main__":
    asyncio.run(run_production_scrape())
