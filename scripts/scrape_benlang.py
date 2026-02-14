#!/usr/bin/env python3
"""
Scrape jobs specifically for Ben Lang collection companies.
"""
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.db import get_db
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.ashby import AshbyScraper
from src.scrapers.workable import WorkableScraper
# Remind: Workday scraper might handle some too but mostly we saw GH/Lever/Ashby/Workable

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BenLangScraper")

async def scrape_benlang_companies():
    db = get_db()
    
    # Get companies from collection
    collection = db.collections.find_one({'id': 'ben-lang-feb-2024'})
    if not collection:
        logger.error("Collection not found!")
        return
        
    company_names = collection['data']['companies']
    logger.info(f"Targets: {len(company_names)} companies from Ben Lang collection")
    
    # Initialize scrapers
    scrapers = {
        'greenhouse': GreenhouseScraper(),
        'lever': LeverScraper(),
        'ashby': AshbyScraper(),
        'workable': WorkableScraper()
    }
    
    semaphore = asyncio.Semaphore(5)  # Concurrency limit
    
    async def process_company(name):
        async with semaphore:
            company = db.companies.find_one({'name': name})
            if not company:
                logger.warning(f"Company {name} not found in DB")
                return
            
            # Correcting data mapping issue from import_benlang.py
            # The importer swapped fields:
            # - ats_type field holds the URL (e.g. https://...)
            # - board_identifier field holds the type (e.g. greenhouse)
            
            raw_ats_type = company.get('ats_type', '')
            raw_board_id = company.get('board_identifier', '')
            
            ats_type = None
            ats_url = None
            
            # Case 1: Import error (URL in ats_type)
            if raw_ats_type and raw_ats_type.startswith('http'):
                ats_url = raw_ats_type
                ats_type = raw_board_id  # The type is in board_identifier
            # Case 2: Correct data (e.g. manually fixed or old data)
            elif raw_ats_type and not raw_ats_type.startswith('http'):
                ats_type = raw_ats_type
                # Prefer explicit 'ats_url', fallback to 'board_identifier' if it looks like a URL
                ats_url = company.get('ats_url')
                if not ats_url and raw_board_id and raw_board_id.startswith('http'):
                    ats_url = raw_board_id
                
            if not ats_type or ats_type == 'unknown':
                logger.warning(f"Skip {name}: ATS type unknown (Raw: {raw_ats_type}, ID: {raw_board_id})")
                return
                
            scraper = scrapers.get(ats_type)
            if not scraper:
                logger.warning(f"Skip {name}: No scraper for type '{ats_type}'")
                return
                
            # Prepare company doc for the scraper
            # Scrapers need 'ats_url' or 'board_token'/'greenhouse_board_token'
            company_scan_doc = company.copy()
            if ats_url:
                company_scan_doc['ats_url'] = ats_url
            
            # Specialized token extraction helper for scrapers that might need it explicitly
            if ats_type == 'greenhouse' and ats_url:
                # https://boards.greenhouse.io/defenseunicorns -> defenseunicorns
                # https://boards.greenhouse.io/embed/job_board?for=defenseunicorns -> defenseunicorns
                try:
                    if 'for=' in ats_url:
                        company_scan_doc['board_token'] = ats_url.split('for=')[1].split('&')[0]
                    else:
                        parts = ats_url.strip('/').split('/')
                        company_scan_doc['board_token'] = parts[-1]
                except:
                     logger.warning(f"Could not parse GH token from {ats_url}")

            elif ats_type == 'lever' and ats_url:
                # https://jobs.lever.co/waabi -> waabi
                try:
                    parts = ats_url.strip('/').split('/')
                    # usually the last part, unless it has extra path
                    company_scan_doc['board_token'] = parts[-1]
                except:
                     logger.warning(f"Could not parse Lever token from {ats_url}")

            elif ats_type == 'ashby' and ats_url:
                # https://jobs.ashbyhq.com/company -> company
                try:
                    parts = ats_url.strip('/').split('/')
                    company_scan_doc['board_token'] = parts[-1]
                except:
                     logger.warning(f"Could not parse Ashby token from {ats_url}")

            try:
                logger.info(f"Scraping {name} ({ats_type})...")
                jobs = await scraper.scrape(company_scan_doc)
                logger.info(f"✅ {name}: Found {len(jobs)} jobs")
                
                if jobs:
                    # Save jobs
                    for job in jobs:
                        # Basic dedupe query
                        existing = db.jobs.find_one({
                            'company': name,
                            'title': job['title'],
                            'location': job['location']
                        })
                        if not existing:
                            job['created_at'] = datetime.utcnow()
                            job['is_active'] = True
                            job['company'] = name # Ensure name match
                            db.jobs.insert_one(job)
                    
                    # Update stats
                    db.companies.update_one(
                        {'_id': company['_id']},
                        {'$set': {'stats.active_jobs': len(jobs), 'last_scraped': datetime.utcnow()}}
                    )
            except Exception as e:
                logger.error(f"Error scraping {name}: {e}")

    tasks = [process_company(name) for name in company_names]
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(scrape_benlang_companies())
