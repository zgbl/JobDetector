import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
import certifi

# Setup paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

def create_indexes():
    mongo_uri = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/')
    db_name = os.environ.get('MONGODB_DATABASE', 'job_detector')
    
    print(f"Connecting to {db_name}...")
    client = MongoClient(mongo_uri, tlsCAFile=certifi.where())
    db = client[db_name]
    
    print("Creating indexes for 'jobs' collection...")
    # Jobs indexes
    db.jobs.create_index([("is_active", ASCENDING)])
    db.jobs.create_index([("posted_date", DESCENDING)])
    db.jobs.create_index([("company", ASCENDING)])
    db.jobs.create_index([("location", ASCENDING)])
    db.jobs.create_index([("category", ASCENDING)]) # If you use category field
    
    # Text search support (optional but helpful for regex performance)
    # However, MongoDB text search is different from regex. 
    # For regex performance on Large collections, we might need specific field indexes.
    
    # Compound indexes for common queries
    db.jobs.create_index([("is_active", ASCENDING), ("posted_date", DESCENDING)])
    db.jobs.create_index([("is_active", ASCENDING), ("company", ASCENDING)])
    
    print("Creating indexes for 'visitor_logs' collection...")
    db.visitor_logs.create_index([("timestamp", DESCENDING)])
    db.visitor_logs.create_index([("ip_address", ASCENDING)])
    
    print("✅ Indexes created successfully!")

if __name__ == "__main__":
    create_indexes()
