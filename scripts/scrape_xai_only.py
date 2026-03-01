import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
from src.scrapers.greenhouse import GreenhouseScraper
from scripts.prod_scraper import scrape_company

async def scrape_xai():
    db = get_db()
    company = db.companies.find_one({'name': 'xAI'})
    if not company:
        print("xAI not found in database")
        return
    
    print(f"Scraping {company['name']} using Greenhouse...")
    scrapers = {'greenhouse': GreenhouseScraper()}
    semaphore = asyncio.Semaphore(1)
    
    count = await scrape_company(company, scrapers, db, semaphore)
    print(f"Imported {count} jobs for xAI")
    close_db()

if __name__ == "__main__":
    asyncio.run(scrape_xai())
