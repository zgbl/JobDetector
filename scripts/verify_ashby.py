import sys
import os
import asyncio
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.scrapers.ashby import AshbyScraper

logging.basicConfig(level=logging.INFO)

async def main():
    print("🚀 Verifying Ashby Scraper...")
    scraper = AshbyScraper()
    
    # Test Case: Anthropic
    company = {
        "name": "Anthropic",
        "ats_url": "https://jobs.ashbyhq.com/anthropic"
    }
    
    print(f"Testing with: {company['name']} -> {company['ats_url']}")
    
    jobs = await scraper.scrape(company)
    
    print(f"\n✅ Found {len(jobs)} jobs!")
    
    if jobs:
        print("\n--- Sample Job ---")
        job = jobs[0]
        print(f"Title: {job['title']}")
        print(f"Location: {job['location']}")
        print(f"URL: {job['source_url']}")
        print(f"Type: {job['job_type']}")
        print(f"Date: {job['posted_date']}")
        print(f"Salary: {job['salary']}")
        print("-" * 20)
        
        # Verify content presence
        if len(job.get('description', '')) > 100:
            print("✅ Description is present and > 100 chars")
        else:
            print("⚠️ Description seems short or empty")

if __name__ == "__main__":
    asyncio.run(main())
