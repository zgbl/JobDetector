#!/usr/bin/env python3
"""
Company Re-verification Script
Bulks audit companies with 0 jobs and attempts to discover their ATS system.
"""
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
from src.services.ats_discovery import ATSDiscoveryService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReverifyCompanies")

async def reverify_companies(limit=None, force=False):
    db = get_db()
    discovery_service = ATSDiscoveryService()
    
    # Query: Companies with 0 jobs, or custom/unknown ATS, or those that have never been scraped
    query = {
        '$or': [
            {'stats.active_jobs': 0},
            {'ats_system.type': 'unknown'},
            {'ats_system.type': 'custom'},
            {'ats_system.type': 'workable', 'stats.active_jobs': 0}
        ]
    }
    
    # If not force, only check active ones. If force, check everything.
    if not force:
        query['is_active'] = True

    companies = list(db.companies.find(query))
    if limit:
        companies = companies[:limit]
        
    logger.info(f"🕵️  Found {len(companies)} candidates for re-verification.")
    
    fixed_count = 0
    checked_count = 0
    
    for company in companies:
        checked_count += 1
        name = company.get('name')
        domain = company.get('domain')
        
        logger.info(f"[{checked_count}/{len(companies)}] Checking {name} ({domain})...")
        
        try:
            ats_url, ats_type = await discovery_service.discover_ats(domain)
            
            if ats_type and ats_url:
                # Update the company in DB
                update_data = {
                    'ats_url': ats_url,
                    'ats_system.type': ats_type,
                    'ats_system.confidence': 1.0,
                    'ats_system.detected_at': datetime.utcnow(),
                    'is_active': True  # Ensure it is active
                }
                
                db.companies.update_one(
                    {'_id': company['_id']},
                    {'$set': update_data}
                )
                
                # If it was custom but now found a standard one, it's a "fix"
                if company.get('ats_system', {}).get('type') != ats_type:
                    logger.info(f"✅ FIXED {name}: {company.get('ats_system', {}).get('type')} -> {ats_type}")
                    fixed_count += 1
                else:
                    logger.info(f"ℹ️  Re-confirmed {name} as {ats_type}")
            else:
                logger.warning(f"❌ Could not find ATS for {name}")
                # If it was a problematic Workable/Custom entry with 0 jobs, reset it to unknown
                if company.get('ats_system', {}).get('type') in ['workable', 'custom', 'unknown']:
                    db.companies.update_one(
                        {'_id': company['_id']},
                        {'$set': {'ats_system.type': 'unknown', 'ats_url': None, 'is_active': False}}
                    )
                    logger.info(f"🧹 RESET {name} to unknown/inactive due to discovery failure.")
                
        except Exception as e:
            logger.error(f"Error checking {name}: {e}")
            
    logger.info("\n" + "="*60)
    logger.info(f"🏁 Audit Complete")
    logger.info(f"Total Checked: {checked_count}")
    logger.info(f"Total Fixed: {fixed_count}")
    logger.info("="*60)
    
    close_db()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Re-verify silent companies in the database.")
    parser.add_argument("--limit", type=int, help="Limit the number of companies to check.")
    parser.add_argument("--force", action="store_true", help="Include inactive companies in the audit.")
    args = parser.parse_args()
    
    asyncio.run(reverify_companies(limit=args.limit, force=args.force))
