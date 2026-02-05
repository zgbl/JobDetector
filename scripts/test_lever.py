#!/usr/bin/env python3
import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.scrapers.lever import LeverScraper
from src.database.connection import get_db, close_db
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_lever():
    scraper = LeverScraper()
    db = get_db()
    
    # Test companies
    lever_companies = [
        {'name': 'Palantir', 'domain': 'palantir.com'},
        {'name': 'Zoox', 'domain': 'zoox.com'},
        {'name': 'Notarize', 'domain': 'notarize.com'},
        {'name': 'Exploding Kittens', 'domain': 'explodingkittens.com'},
    ]
    
    for company in lever_companies:
        logger.info(f"\nTesting {company['name']} (Lever)...")
        jobs = await scraper.scrape(company)
        
        if jobs:
            logger.info(f"✅ Found {len(jobs)} jobs for {company['name']}")
            sample = jobs[0]
            logger.info(f"Sample Job: {sample['title']}")
            logger.info(f"Location: {sample['location']}")
            logger.info(f"Description Length: {len(sample.get('description', ''))}")
            logger.info(f"Skills: {', '.join(sample.get('skills', []))}")
            
            # Optional: Save to DB
            # db.jobs.insert_many(jobs[:5])
        else:
            logger.warning(f"❌ No jobs found for {company['name']}. Token might be different.")

    close_db()

if __name__ == "__main__":
    asyncio.run(test_lever())
