import sys
import asyncio
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
from scripts.prod_scraper import scrape_company
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.workday import WorkdayScraper

async def process_woven_request():
    db = get_db()
    
    # 1. Find the request
    req = db.company_requests.find_one({"name": "Woven by Toyota"})
    if not req:
        print("❌ Request not found!")
        return

    print(f"🚀 Processing Request: {req['name']} ({req['careers_url']})")

    # 2. Manual/Auto Discovery (Woven uses Workday)
    # In a real discovery, we'd crawl the page, but here we know it's Workday
    ats_type = "workday"
    ats_url = "https://toyota.wd3.myworkdayjobs.com/WovenCity" # Specific to Woven
    
    # 3. Create company record
    company_data = {
        "name": req["name"],
        "domain": "woven.toyota",
        "careers_url": req["careers_url"],
        "ats_url": ats_url,
        "ats_type": ats_type,
        "is_active": True,
        "schedule": {"frequency_hours": 24, "priority": 2},
        "stats": {"total_jobs_found": 0, "active_jobs": 0},
        "metadata": {
            "added_by": "request_processor_test",
            "added_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "from_request_id": str(req["_id"])
        }
    }
    
    # Check if exists
    existing = db.companies.find_one({"name": req["name"]})
    if not existing:
        db.companies.insert_one(company_data)
        print(f"✅ Company '{req['name']}' added to active monitoring.")
    else:
        print(f"ℹ️ Company '{req['name']}' already exists.")

    # 4. Update request status
    db.company_requests.update_one({"_id": req["_id"]}, {"$set": {"status": "approved"}})
    print("✅ Request status updated to 'approved'.")

    # 5. Try immediate scrape
    print(f"🔎 Attempting immediate scrape for {req['name']}...")
    scrapers = {
        'greenhouse': GreenhouseScraper(),
        'lever': LeverScraper(),
        'workday': WorkdayScraper()
    }
    
    company_record = db.companies.find_one({"name": req["name"]})
    semaphore = asyncio.Semaphore(1)
    new_jobs = await scrape_company(company_record, scrapers, db, semaphore)
    
    print(f"🏁 Process complete. Found {new_jobs} jobs for {req['name']}.")
    close_db()

if __name__ == "__main__":
    asyncio.run(process_woven_request())
