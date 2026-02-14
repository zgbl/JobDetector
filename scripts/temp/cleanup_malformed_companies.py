import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

# Setup paths and env
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

def cleanup_malformed():
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DATABASE", "JobDetector")
    
    if not uri:
        print("Error: MONGODB_URI not found")
        return

    client = MongoClient(uri)
    db = client[db_name]
    
    # List of known malformed/failed companies mentioned by user
    # These were "imported" but have bad data, preventing re-import.
    targets = [
        "Upscale AI", 
        "Decagon", 
        "Upwind Security", 
        "Baseten", 
        "Defense Unicorns", 
        "Oxide Computer",
        "Knostic",
        "Warp" # Add any others if needed
    ]
    
    print(f"--- Cleaning up {len(targets)} companies for re-import ---")
    
    deleted_count = 0
    for name in targets:
        result = db.companies.delete_one({"name": name})
        if result.deleted_count > 0:
            print(f"✅ Deleted: {name}")
            deleted_count += 1
        else:
            print(f"⚠️  Not found (already clean): {name}")
            
    print(f"\nTotal deleted: {deleted_count}")
    print("Now run import_benlang.py again!")

if __name__ == "__main__":
    cleanup_malformed()
