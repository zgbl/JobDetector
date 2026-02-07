#!/usr/bin/env python3
"""
Import Japanese companies from YAML and run ATS discovery.
"""
import os
import sys
import asyncio
import yaml
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
from src.services.ats_discovery import ATSDiscoveryService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JapanImporter")

async def main():
    db = get_db()
    discovery = ATSDiscoveryService()
    
    yaml_path = project_root / 'data' / 'companies_japan.yaml'
    if not yaml_path.exists():
        logger.error(f"File not found: {yaml_path}")
        return

    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
        companies = data.get('companies', [])

    logger.info(f"Loaded {len(companies)} Japanese companies. Starting discovery...")

    for comp_data in companies:
        name = comp_data['name']
        domain = comp_data['domain']
        
        # Check if already exists
        if db.companies.find_one({'name': name}):
            logger.info(f"Skipping {name} (already exists)")
            continue

        logger.info(f"🔍 Discovering ATS for {name} ({domain})...")
        ats_url, ats_type = await discovery.discover_ats(domain)
        
        if not ats_url and comp_data.get('ats_type'):
            # Fallback to provided ats_type if discovery fails but pattern guessing might work
            ats_type = comp_data['ats_type']
            # We don't have a reliable URL yet, but maybe guess it?
            # Or just store it as a monitor for now if no URL.
        
        company_record = {
            'name': name,
            'company_id': f"jp_{name.lower().replace(' ', '_')}",
            'domain': domain,
            'ats_url': ats_url,
            'ats_system': {'type': ats_type} if ats_type else None,
            'location': 'Japan',
            'is_active': True,
            'created_at': datetime.utcnow()
        }
        
        db.companies.insert_one(company_record)
        logger.info(f"✅ Imported {name} as Scraper (ATS: {ats_type})" if ats_url else f"⚠️ Imported {name} as Monitor stub")

    close_db()

if __name__ == "__main__":
    from datetime import datetime
    asyncio.run(main())
