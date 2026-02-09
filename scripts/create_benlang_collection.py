#!/usr/bin/env python3
"""
Create Ben Lang collection in the database.
"""
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.index import get_db
from scripts.parse_benlang import BenLangParser


def create_benlang_collection():
    """Create Ben Lang collection in collections table"""
    db = get_db()
    
    # Parse companies from file
    file_path = Path(__file__).parent.parent / 'data' / 'ImportList' / 'BenLang.txt'
    parser = BenLangParser()
    companies = parser.parse_file(str(file_path))
    
    company_names = [c['name'] for c in companies]
    
    # Collection document matching frontend schema
    collection_doc = {
        'id': 'ben-lang-feb-2024',  # Frontend expects 'id', not 'slug'
        'name': "Ben Lang's $100M+ Raises",
        'description': '33 well-funded companies (raised $100M+) actively hiring',
        'icon': 'fas fa-money-bill-wave',  # FontAwesome icon
        'color': 'rgba(255, 215, 0, 0.2)',  # Gold background
        'text_color': '#ffd700',            # Gold text
        'data': {
            'companies': company_names
        },
        'metadata': {
            'source': 'LinkedIn',
            'author': 'Ben Lang',
            'post_url': 'https://www.linkedin.com/feed/update/urn:li:activity:7425206257516646400/',
            'date_posted': '2024-02-08',
            'type': 'curated_list',
            'funding_threshold': '$100M+'
        },
        'created_at': datetime.utcnow()
    }
    
    # Check if collection already exists (check both slug and id for migration)
    db.collections.delete_many({'slug': 'ben-lang-feb-2024'}) # Remove old schema
    
    existing = db.collections.find_one({'id': 'ben-lang-feb-2024'})
    
    if existing:
        print("Collection already exists. Updating...")
        db.collections.update_one(
            {'id': 'ben-lang-feb-2024'},
            {'$set': collection_doc}
        )
        print("✅ Updated existing collection")
    else:
        db.collections.insert_one(collection_doc)
        print("✅ Created new collection")
    
    # Display summary
    print(f"\n📊 Collection Summary:")
    print(f"   Name: {collection_doc['name']}")
    print(f"   Companies: {len(company_names)}")
    print(f"   Icon: {collection_doc['icon']}")
    print(f"   Author: {collection_doc['metadata']['author']}")
    print(f"   Source: {collection_doc['metadata']['post_url']}")
    
    return collection_doc


if __name__ == '__main__':
    create_benlang_collection()
