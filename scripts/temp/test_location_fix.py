import asyncio
import logging
from src.database.connection import get_db
from src.scrapers.greenhouse import GreenhouseScraper
from src.services.language_filter import LanguageFilterService
from datetime import datetime

logging.basicConfig(level=logging.INFO)

async def test_location_fix():
    db = get_db()
    scraper = GreenhouseScraper()
    
    # Get Mercari
    company = db.companies.find_one({'name': 'Mercari'})
    if not company:
        print("Mercari not found in DB")
        return
        
    print(f"Scraping {company['name']}...")
    jobs = await scraper.scrape(company)
    
    if not jobs:
        print("No jobs found")
        return
        
    saved_count = 0
    for job in jobs:
        # Use combined text for IT check
        combined_text = f"{job['title']} {job['description']}"
        is_it, reason = LanguageFilterService.is_it_role(combined_text)
        
        if is_it:
            print(f"Found IT Job: {job['title']}")
            print(f"Location: {job['location']}")
            print(f"Company Location: {job.get('company_location')}")
            
            if job.get('company_location') == 'Japan':
                print("✅ SUCCESS: company_location is present")
            else:
                print("❌ FAILURE: company_location is missing")
                
            # Save to DB to test API filter
            db.jobs.update_one(
                {'job_id': job['job_id']},
                {'$set': job},
                upsert=True
            )
            print(f"Saved job {job['job_id']} to DB")
            saved_count += 1
            if saved_count >= 3: break
        else:
            print(f"Skipping non-IT job: {job['title']} ({reason})")

if __name__ == "__main__":
    asyncio.run(test_location_fix())
