import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

# Setup paths and env
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

def add_collection():
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DATABASE", "JobDetector")
    
    if not uri:
        print("Error: MONGODB_URI not found")
        return

    client = MongoClient(uri)
    db = client[db_name]
    
    # Collection Data
    ai_collection = {
        "id": "ai-engineering",
        "name": "AI & ML",
        "icon": "fas fa-brain",
        "color": "var(--gradient-accent)",  # Using CSS variable or hex if needed? Favorites uses dynamic style. 
        # Favorites.html uses: style="background: ${c.color}; color: ${c.text_color};"
        # Let's use a nice purple/blue gradient hex or standard color
        "color": "linear-gradient(135deg, #a855f7 0%, #d946ef 100%)",
        "text_color": "#ffffff",
        "data": {
            "category": "AI"
        }
    }

    # Upsert based on id
    result = db.collections.update_one(
        {"id": ai_collection["id"]},
        {"$set": ai_collection},
        upsert=True
    )
    
    print(f"Collection 'AI & ML' upserted. Modified: {result.modified_count}, Upserted: {result.upserted_id}")

if __name__ == "__main__":
    add_collection()
