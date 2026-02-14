from src.database.connection import get_db
import re

def test_query():
    db = get_db()
    
    # 1. Direct match
    job = db.jobs.find_one({'company': 'Mercari'})
    if not job:
        print("Mercari job not found")
        return
    
    print(f"Job Location: {job.get('location')}")
    print(f"Job Company Location: {job.get('company_location')}")
    
    # 2. Test Regex match logic (simulating API)
    search_val = 'Japan|Tokyo|Osaka|Kyoto'
    
    # Try company_location regex
    query_cl = {'company_location': {'$regex': search_val, '$options': 'i'}}
    job_cl = db.jobs.find_one(query_cl)
    if job_cl:
        print(f"✅ FOUND via company_location regex: {job_cl['title']}")
    else:
        print("❌ NOT FOUND via company_location regex")
        
    # Try full $or query
    query_or = {'$or': [
        {'location': {'$regex': search_val, '$options': 'i'}},
        {'company_location': {'$regex': search_val, '$options': 'i'}}
    ]}
    job_or = db.jobs.find_one(query_or)
    if job_or:
        print(f"✅ FOUND via $or query: {job_or['title']}")
    else:
        print("❌ NOT FOUND via $or query")

if __name__ == "__main__":
    test_query()
