#!/usr/bin/env python3
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db

def verify_sizes():
    db = get_db()
    
    # Check count by size
    pipeline = [
        {'$group': {
            '_id': '$metadata.size',
            'count': {'$sum': 1}
        }},
        {'$sort': {'count': -1}}
    ]
    
    stats = list(db.companies.aggregate(pipeline))
    
    print("\nCompany Count by Size:")
    print("=" * 30)
    for stat in stats:
        size = stat['_id'] or "Not Set"
        count = stat['count']
        print(f"{size:20}: {count}")
    
    # Sample companies for each size
    for stat in stats:
        size = stat['_id']
        if not size: continue
        
        print(f"\nSample {size} Companies:")
        samples = db.companies.find({'metadata.size': size}).limit(3)
        for s in samples:
            print(f"  - {s['name']} ({s['domain']})")
    
    close_db()

if __name__ == "__main__":
    verify_sizes()
