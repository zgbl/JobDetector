#!/usr/bin/env python3
"""
Sync company job counts from jobs collection to companies collection.
Updates the stats.active_jobs field for each company.
"""
from api.db import get_db

def sync_company_job_counts():
    db = get_db()
    
    print("🔄 Starting company job count sync...")
    
    # Get all companies
    companies = list(db.companies.find())
    total = len(companies)
    updated = 0
    
    for idx, company in enumerate(companies, 1):
        company_name = company['name']
        
        # Count active jobs for this company
        job_count = db.jobs.count_documents({
            'company': company_name,
            'is_active': True
        })
        
        # Update the company's stats
        result = db.companies.update_one(
            {'_id': company['_id']},
            {'$set': {'stats.active_jobs': job_count}}
        )
        
        if result.modified_count > 0:
            updated += 1
            if job_count > 0:
                print(f"✅ [{idx}/{total}] {company_name}: {job_count} jobs")
        else:
            if job_count > 0:
                print(f"ℹ️  [{idx}/{total}] {company_name}: {job_count} jobs (already up-to-date)")
    
    print(f"\n✅ Sync completed!")
    print(f"   Total companies: {total}")
    print(f"   Updated: {updated}")
    
    # Show summary
    with_jobs = db.companies.count_documents({'stats.active_jobs': {'$gt': 0}})
    without_jobs = db.companies.count_documents({'stats.active_jobs': 0})
    
    print(f"\n📊 Summary:")
    print(f"   Companies with jobs: {with_jobs}")
    print(f"   Companies without jobs (silent): {without_jobs}")

if __name__ == '__main__':
    sync_company_job_counts()
