
import os
import sys
from pathlib import Path
from collections import Counter

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from api.db import get_db

def check_benlang_ats_stats():
    db = get_db()
    
    # Get Ben Lang collection
    collection = db.collections.find_one({'id': 'ben-lang-feb-2024'})
    if not collection:
        print("Collection not found")
        return
        
    company_names = collection['data']['companies']
    print(f"Total Companies in Collection: {len(company_names)}")
    
    # Get company details
    companies = list(db.companies.find({'name': {'$in': company_names}}))
    
    ats_counts = Counter(c.get('ats_type', 'unknown') for c in companies)
    
    print("\nATS Distribution:")
    for ats, count in ats_counts.most_common():
        print(f"  {ats}: {count}")
        
    # Check jobs
    total_jobs = sum(c.get('stats', {}).get('active_jobs', 0) for c in companies)
    print(f"\nTotal Active Jobs in Collection: {total_jobs}")

if __name__ == "__main__":
    check_benlang_ats_stats()
