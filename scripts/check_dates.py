#!/usr/bin/env python3
"""
Test script to check if jobs have posted_date in database
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db

db = get_db()

# Get sample of jobs
jobs = list(db.jobs.find().limit(10))

print(f"\n=== Checking {len(jobs)} jobs for posted_date ===\n")

jobs_with_date = 0
jobs_without_date = 0

for job in jobs:
    has_date = job.get('posted_date') is not None
    if has_date:
        jobs_with_date += 1
        print(f"✅ {job['title'][:50]:50} | {job['posted_date']}")
    else:
        jobs_without_date += 1
        print(f"❌ {job['title'][:50]:50} | NO DATE")

print(f"\n=== Summary ===")
print(f"Jobs with date: {jobs_with_date}")
print(f"Jobs without date: {jobs_without_date}")
