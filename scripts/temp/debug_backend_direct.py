import sys
import os
from datetime import datetime

# Add project root to python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

print(f"Project root: {project_root}")

try:
    from api.auth_utils import get_password_hash, create_access_token
    from src.database.connection import get_db
    
    print("Imports successful")
    
    # Print DB Connection Info
    import os
    from dotenv import load_dotenv
    load_dotenv()
    uri = os.getenv('MONGODB_URI', 'NOT_SET')
    masked_uri = uri.replace(uri.split('@')[0], '***') if '@' in uri else '***'
    db_name = os.getenv('MONGODB_DATABASE', 'jobdetector')
    print(f"DEBUG: Using URI: {masked_uri}")
    print(f"DEBUG: Using DB Name: {db_name}")

    # Test Password Hashing
    try:
        print("Testing get_password_hash...")
        pwd = "testpassword"
        hashed = get_password_hash(pwd)
        print(f"Hash created: {hashed[:10]}...")
    except Exception as e:
        print(f"ERROR in get_password_hash: {e}")
        import traceback
        traceback.print_exc()

    # Test DB Connection
    try:
        print("Testing DB connection...")
        db = get_db()
        
        print("\n--- Collections in Database ---")
        collections = db.list_collection_names()
        print(f"Collections found: {collections}")
        
        for col_name in collections:
            count = db[col_name].count_documents({})
            print(f"- {col_name}: {count} documents")
            
        print("\n--- Content of 'users' collection ---")
        if 'users' in collections:
            for user in db.users.find():
                print(f"User: {user.get('email')} (ID: {user.get('_id')})")
        else:
            print("CRITICAL: 'users' collection NOT found in list!")

    except Exception as e:
        print(f"ERROR in DB access: {e}")
        import traceback
        traceback.print_exc()
        
except Exception as e:
    print(f"Import/Setup Error: {e}")
    import traceback
    traceback.print_exc()
