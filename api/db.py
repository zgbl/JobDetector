
import os
import pymongo
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

# Load env vars from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

def get_db():
    """Get MongoDB database connection"""
    # Use environment variable or default local URI
    mongo_uri = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/')
    db_name = os.environ.get('MONGODB_DATABASE', 'job_detector')
    client = MongoClient(mongo_uri)
    return client[db_name]
