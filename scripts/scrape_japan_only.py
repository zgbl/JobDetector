import asyncio
import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
from scripts.prod_scraper import scrape_company
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.workday import WorkdayScraper
from src.scrapers.ashby import AshbyScraper
from src.scrapers.workable import WorkableScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JapanScraper")

async def main():
    db = get_db()
    
    # Initialize scrapers
    scrapers = {
        'greenhouse': GreenhouseScraper(),
        'lever': LeverScraper(),
        'workday': WorkdayScraper(),
        'ashby': AshbyScraper(),
        'workable': WorkableScraper()
    }
    
    # Get all Japanese companies with an ATS URL
    companies = list(db.companies.find({
        'location': 'Japan',
        'ats_url': {'$ne': None}
    }))
    
    logger.info(f"Found {len(companies)} Japanese companies with verified ATS URLs")
    
    semaphore = asyncio.Semaphore(5)
    tasks = [scrape_company(c, scrapers, db, semaphore) for c in companies]
    
    results = await asyncio.gather(*tasks)
    total_jobs = sum(results)
    
    logger.info(f"Successfully scraped {total_jobs} jobs from {len(companies)} Japanese companies")
    
    # Also find jobs for companies that might be mis-tagged but are definitely Japanese
    # (Actually we defined them in data/companies_japan.yaml, so they should be in DB)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        asyncio.run(close_db())
