import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

# Setup paths and env
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

def inspect_collections():
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DATABASE", "JobDetector")
    
    if not uri:
        print("Error: MONGODB_URI not found")
        return

    client = MongoClient(uri)
    db = client[db_name]
    
    collections = list(db.collections.find({}, {"_id": 0}))
    print("--- Current Collections ---")
    for c in collections:
        print(f"ID: {c.get('id')}")
        print(f"Name: {c.get('name')}")
        print(f"Data: {c.get('data')}")
        print("-" * 20)

if __name__ == "__main__":
    inspect_collections()
