import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db

def seed_collections():
    db = get_db()
    collections_data = [
        {
            "id": "bigtech",
            "name": "Big Tech",
            "icon": "fas fa-building",
            "color": "rgba(59, 130, 246, 0.2)",
            "text_color": "#3b82f6",
            "data": {
                "companies": ['Google', 'Meta', 'Amazon', 'Microsoft', 'Apple', 'Netflix', 'Uber', 'Airbnb', 'Tesla']
            }
        },
        {
            "id": "ai",
            "name": "AI Innovators",
            "icon": "fas fa-brain",
            "color": "rgba(139, 92, 246, 0.2)",
            "text_color": "#8b5cf6",
            "data": {
                "companies": ['OpenAI', 'Anthropic', 'Databricks', 'Scale AI', 'Hugging Face', 'Perplexity']
            }
        },
        {
            "id": "fintech",
            "name": "Fintech Leaders",
            "icon": "fas fa-chart-line",
            "color": "rgba(16, 185, 129, 0.2)",
            "text_color": "#10b981",
            "data": {
                "companies": ['Stripe', 'Block', 'Robinhood', 'Coinbase', 'Affirm', 'Plaid', 'Brex']
            }
        },
        {
            "id": "startup",
            "name": "High Growth Startups",
            "icon": "fas fa-rocket",
            "color": "rgba(245, 158, 11, 0.2)",
            "text_color": "#f59e0b",
            "data": {
                "companies": ['Notion', 'Figma', 'Canva', 'Rippling', 'Airtable', 'Deel', 'Ramp']
            }
        },
        {
            "id": "faang_swe",
            "name": "FAANG SWE",
            "icon": "fas fa-code",
            "color": "rgba(59, 130, 246, 0.2)",
            "text_color": "#3b82f6",
            "data": {
                "companies": ['Google', 'Meta', 'Amazon', 'Apple', 'Netflix'],
                "q": "Software Engineer"
            }
        },
        {
            "id": "japan",
            "name": "Japan IT",
            "icon": "fas fa-sun",
            "color": "rgba(239, 68, 68, 0.2)",
            "text_color": "#ef4444",
            "data": {
                "location": "Japan"
            }
        }
    ]

    print(f"Seeding {len(collections_data)} collections...")
    
    # Use id as the unique key
    for coll in collections_data:
        db.collections.update_one(
            {"id": coll["id"]},
            {"$set": coll},
            upsert=True
        )
    
    print("Seeding complete!")

if __name__ == "__main__":
    seed_collections()
