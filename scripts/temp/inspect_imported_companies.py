import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

# Setup paths and env
project_root = Path(__file__).parent.parent.parent # temp is inside scripts, so need 3 levels up
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

def inspect_companies():
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DATABASE", "JobDetector")
    
    if not uri:
        print("Error: MONGODB_URI not found")
        return

    client = MongoClient(uri)
    db = client[db_name]
    
    # Check the last 5 added companies from BenLang list (based on text file order if possible, 
    # but here we just look for recent entries or specific names from user's log)
    
    # User mentioned: "Baseten", "Defense Unicorns", "Oxide Computer"
    target_names = ["Baseten", "Defense Unicorns", "Oxide Computer"]
    
    print(f"--- Inspecting {len(target_names)} companies from user report ---")
    for name in target_names:
        print(f"\nScanning: {name}")
        company = db.companies.find_one({"name": name})
        if company:
            print(f"  ID: {company.get('_id')}")
            print(f"  ATS Type: {company.get('ats_type')}")
            print(f"  Board ID: {company.get('board_identifier')}")
            print(f"  ATS URL: {company.get('ats_url')}") # Checking if my previous fix added this
            print(f"  Domain: {company.get('domain')}")
            print(f"  Metadata: {company.get('metadata')}")
        else:
            print("  [NOT FOUND IN DB]")

if __name__ == "__main__":
    inspect_companies()
