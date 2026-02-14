import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
import certifi

# Setup paths and env
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

def test_connection():
    uri = os.getenv("MONGODB_URI")
    print(f"URI found: {'Yes' if uri else 'No'}")
    
    try:
        print("Attempt 1: Standard Connection...")
        client = MongoClient(uri)
        client.admin.command('ping')
        print("✅ Standard Connection Success!")
    except Exception as e:
        print(f"❌ Standard Connection Failed: {e}")

    try:
        print("\nAttempt 2: Certifi Connection...")
        client = MongoClient(uri, tlsCAFile=certifi.where())
        client.admin.command('ping')
        print("✅ Certifi Connection Success!")
    except Exception as e:
        print(f"❌ Certifi Connection Failed: {e}")

if __name__ == "__main__":
    test_connection()
