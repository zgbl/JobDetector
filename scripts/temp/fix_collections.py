import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

# Setup paths and env
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

def fix_collections():
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DATABASE", "JobDetector")
    
    if not uri:
        print("Error: MONGODB_URI not found")
        return

    client = MongoClient(uri)
    db = client[db_name]
    
    # Fix Japan Collection - User says ID is "japan" and Name is "JapanIT"
    japan_collection = {
        "id": "japan",
        "name": "JapanIT",
        "icon": "fas fa-torii-gate",
        "color": "linear-gradient(135deg, #ff4d4d 0%, #f9cb28 100%)",
        "text_color": "#ffffff",
        "data": {
            "location": "Japan",
            "category": "Engineering"
        }
    }

    db.collections.update_one(
        {"id": "japan"},
        {"$set": japan_collection},
        upsert=True
    )
    print("Fixed 'JapanIT' collection (id='japan').")

    # Remove the duplicate "japan-tech" I created earlier if it exists
    db.collections.delete_one({"id": "japan-tech"})
    print("Cleaned up 'japan-tech' duplicate.")

if __name__ == "__main__":
    fix_collections()
