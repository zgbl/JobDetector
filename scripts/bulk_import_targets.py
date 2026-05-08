import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db

def bulk_import():
    db = get_db()
    
    target_companies = [
        # --- Greenhouse Systems (Easy to scrape) ---
        {"name": "Two Sigma", "domain": "twosigma.com", "careers_url": "https://boards.greenhouse.io/twosigma", "ats_type": "greenhouse", "tags": ["Finance", "Quant", "Tier 1"]},
        {"name": "Jane Street", "domain": "janestreet.com", "careers_url": "https://boards.greenhouse.io/janestreet", "ats_type": "greenhouse", "tags": ["Finance", "Quant", "Tier 1"]},
        {"name": "Citadel", "domain": "citadel.com", "careers_url": "https://boards.greenhouse.io/citadel", "ats_type": "greenhouse", "tags": ["Finance", "Quant", "Tier 1"]},
        {"name": "Renaissance Technologies", "domain": "rentech.com", "careers_url": "https://boards.greenhouse.io/rt", "ats_type": "greenhouse", "tags": ["Finance", "Quant"]},
        {"name": "Hugging Face", "domain": "huggingface.co", "careers_url": "https://boards.greenhouse.io/huggingface", "ats_type": "greenhouse", "tags": ["AI", "Open Source", "Tier 1"]},
        {"name": "Scale AI", "domain": "scale.com", "careers_url": "https://boards.greenhouse.io/scaleai", "ats_type": "greenhouse", "tags": ["AI", "Data", "Tier 1"]},
        {"name": "Perplexity AI", "domain": "perplexity.ai", "careers_url": "https://boards.greenhouse.io/perplexity", "ats_type": "greenhouse", "tags": ["AI", "Search", "Tier 1"]},
        
        # --- Lever Systems (Easy to scrape) ---
        {"name": "Mistral AI", "domain": "mistral.ai", "careers_url": "https://jobs.lever.co/mistral", "ats_type": "lever", "tags": ["AI", "LLM", "Tier 1"]},
        {"name": "Cohere", "domain": "cohere.com", "careers_url": "https://jobs.lever.co/cohere", "ats_type": "lever", "tags": ["AI", "LLM", "Tier 1"]},
        {"name": "Groq", "domain": "groq.com", "careers_url": "https://jobs.lever.co/groq", "ats_type": "lever", "tags": ["AI", "Hardware/Cloud", "Tier 1"]},
        {"name": "Vercel", "domain": "vercel.com", "careers_url": "https://jobs.lever.co/vercel", "ats_type": "lever", "tags": ["Cloud", "Frontend/Platform", "Tier 1"]},
        
        # --- Workday / Other (Harder, using direct URLs) ---
        {"name": "BlackRock", "domain": "blackrock.com", "careers_url": "https://blackrock.wd1.myworkdayjobs.com/BlackRock_Professional", "ats_type": "workday", "tags": ["Finance", "Asset Management"]},
        {"name": "HSBC", "domain": "hsbc.com", "careers_url": "https://hsbc.wd3.myworkdayjobs.com/external", "ats_type": "workday", "tags": ["Finance", "Banking"]},
        {"name": "Barclays", "domain": "barclays.com", "careers_url": "https://barclays.wd3.myworkdayjobs.com/BarclaysExperience", "ats_type": "workday", "tags": ["Finance", "Banking"]},
    ]
    
    print(f"🚀 Starting bulk import of {len(target_companies)} target companies...")
    
    added_count = 0
    skipped_count = 0
    
    for comp in target_companies:
        # Check if already exists
        existing = db.companies.find_one({"name": {"$regex": f"^{comp['name']}$", "$options": "i"}})
        if existing:
            print(f"   🔵 Updating {comp['name']} (already exists)")
            db.companies.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "careers_url": comp["careers_url"],
                    "ats_url": comp["careers_url"],
                    "ats_type": comp.get("ats_type", "unknown")
                }}
            )
            skipped_count += 1
            continue
            
        new_company = {
            "name": comp["name"],
            "domain": comp["domain"],
            "careers_url": comp["careers_url"],
            "ats_url": comp["careers_url"], 
            "ats_type": comp.get("ats_type", "unknown"),
            "is_active": True,
            "schedule": {"frequency_hours": 24, "priority": 2},
            "stats": {"total_jobs_found": 0, "active_jobs": 0},
            "metadata": {
                "added_by": "bulk_target_import",
                "added_at": datetime.now(timezone.utc).replace(tzinfo=None),
                "verified": False,
                "tags": comp["tags"] + ["Personal Target"]
            }
        }
        
        db.companies.insert_one(new_company)
        print(f"   ✅ Added {comp['name']}")
        added_count += 1
        
    print(f"\n✨ Import Finished!")
    print(f"   Added: {added_count}")
    print(f"   Skipped: {skipped_count}")

if __name__ == "__main__":
    bulk_import()
