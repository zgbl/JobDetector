#!/usr/bin/env python3
"""
Import Ben Lang companies into JobDetector.
Discovers career sites, ATS systems, and imports companies.
"""
import sys
import os
from pathlib import Path
from typing import List, Dict, Optional
import re
from datetime import datetime
import asyncio
# from api.db import get_db # Moved below

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.db import get_db

from scripts.parse_benlang import BenLangParser
from src.services.ats_discovery import ATSDiscoveryService
from api.db import get_db


class BenLangImporter:
    """Import Ben Lang companies with ATS discovery"""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.ats_discovery = ATSDiscoveryService()
        self.db = get_db() if not dry_run else None
        
    def find_career_site(self, company_name: str) -> Optional[Dict]:
        """
        Find company career site using Google search patterns.
        
        Args:
            company_name: Normalized company name
            
        Returns:
            Dict with domain, career_url if found
        """
        # Common career page patterns
        common_patterns = [
            f"{company_name.lower().replace(' ', '')}.com/careers",
            f"{company_name.lower().replace(' ', '')}.com/jobs",
            f"careers.{company_name.lower().replace(' ', '')}.com",
            f"{company_name.lower().replace(' ', '')}.io/careers",
            f"{company_name.lower().replace(' ', '')}.ai/careers",
        ]
        
        # Try common domain patterns first
        for pattern in common_patterns:
            # Extract domain
            if '/' in pattern:
                domain = pattern.split('/')[0]
                return {
                    'domain': domain,
                    'career_url': f'https://{pattern}',
                    'source': 'pattern_match'
                }
        
        return None
    
    def check_existing_company(self, company_name: str) -> Optional[Dict]:
        """Check if company already exists in database"""
        if self.dry_run or self.db is None:
            return None
            
        # Try exact match
        existing = self.db.companies.find_one({'name': company_name})
        if existing:
            return existing
            
        # Try case-insensitive match
        existing = self.db.companies.find_one({
            'name': {'$regex': f'^{re.escape(company_name)}$', '$options': 'i'}
        })
        
        return existing
    
    async def import_company_async(self, company_data: Dict, semaphore: asyncio.Semaphore) -> Dict:
        """
        Import a single company with ATS discovery (Async).
        """
        async with semaphore:
            company_name = company_data['name']
            
            # Check if already exists (Sync DB call - okay for now or use ThreadPool if strict)
            existing = self.check_existing_company(company_name)
            if existing:
                return {
                    'name': company_name,
                    'status': 'exists',
                    'domain': existing.get('domain'),
                    'ats_type': existing.get('ats_type')
                }
            
            # Find career site (Sync logic but fast/CPU bound)
            career_info = self.find_career_site(company_name)
            if not career_info:
                return {
                    'name': company_name,
                    'status': 'no_career_site',
                    'error': 'Could not determine career site'
                }
            
            domain = career_info['domain']
            
            # Discover ATS (Async)
            ats_type = None
            board_identifier = None
            
            if not self.dry_run:
                try:
                    result = await self.ats_discovery.discover_ats(domain)
                    if result and len(result) == 2:
                        # discover_ats returns (ats_url, ats_type)
                        ats_url_found, ats_type_found = result
                        board_identifier = ats_url_found # Store URL in identifier or use as fallback
                        ats_type = ats_type_found
                except Exception as e:
                    print(f"   ⚠️  ATS discovery failed for {company_name}: {e}")
            
            # Prepare company document
            company_doc = {
                'name': company_name,
                'domain': domain,
                'ats_type': ats_type or 'unknown',
                'board_identifier': board_identifier,
                'metadata': {
                    'size': 'startup',
                    'industry': company_data.get('description', ''),
                    'location': company_data.get('location', ''),
                    'source': 'benlang',
                    'raw_name': company_data.get('raw_name', company_name)
                },
                'stats': {
                    'active_jobs': 0,
                    'total_jobs_found': 0
                }
            }
            
            # Insert into database
            if not self.dry_run and self.db is not None:
                try:
                    self.db.companies.insert_one(company_doc)
                except Exception as e:
                    return {
                        'name': company_name,
                        'status': 'error',
                        'error': str(e)
                    }
            
            return {
                'name': company_name,
                'status': 'imported',
                'domain': domain,
                'ats_type': ats_type or 'unknown',
                'career_url': career_info.get('career_url')
            }
    
    async def import_all_async(self, companies: List[Dict]) -> Dict:
        """
        Import all companies async.
        """
        results = {
            'total': len(companies),
            'imported': 0,
            'exists': 0,
            'failed': 0,
            'companies': []
        }
        
        semaphore = asyncio.Semaphore(5) # Reduce to 5 for better stability
        tasks = []
        
        for i, c in enumerate(companies):
             tasks.append(self.import_company_with_timeout(c, semaphore, i+1, len(companies)))
        
        import_results = await asyncio.gather(*tasks)
        
        for result in import_results:
            results['companies'].append(result)
            
            if result['status'] == 'imported':
                results['imported'] += 1
                # print(f"✅ Imported: {result['name']} -> {result.get('domain')} ({result.get('ats_type')})") # Already printing in wrapper
            elif result['status'] == 'exists':
                results['exists'] += 1
            elif result['status'] == 'no_career_site':
                results['failed'] += 1
            else:
                results['failed'] += 1
        
        return results

    async def import_company_with_timeout(self, company_data, semaphore, index, total):
        async with semaphore:
            print(f"[{index}/{total}] Processing: {company_data['name']}...")
            try:
                # Enforce 45s hard timeout per company
                return await asyncio.wait_for(self.import_company_internal(company_data), timeout=45.0)
            except asyncio.TimeoutError:
                print(f"❌ Timeout: {company_data['name']} took too long")
                return {
                    'name': company_data['name'],
                    'status': 'timeout',
                    'error': 'Operation timed out'
                }
            except Exception as e:
                print(f"❌ Error: {company_data['name']} - {e}")
                return {
                    'name': company_data['name'],
                    'status': 'error',
                    'error': str(e)
                }

    async def import_company_internal(self, company_data: Dict) -> Dict:
        """
        Internal logic for importing a single company.
        """
        company_name = company_data['name']
        
        # Check if already exists
        existing = self.check_existing_company(company_name)
        if existing:
            # print(f"ℹ️  Skipping {company_name} (Exists)")
            return {
                'name': company_name,
                'status': 'exists',
                'domain': existing.get('domain'),
                'ats_type': existing.get('ats_type')
            }
        
        # Find career site
        career_info = self.find_career_site(company_name)
        if not career_info:
            print(f"⚠️  No career site pattern for {company_name}")
            return {
                'name': company_name,
                'status': 'no_career_site',
                'error': 'Could not determine career site'
            }
        
        domain = career_info['domain']
        
        # Discover ATS
        ats_type = None
        board_identifier = None
        
        if not self.dry_run:
            try:
                result = await self.ats_discovery.discover_ats(domain)
                if result and len(result) == 2:
                    # discover_ats returns (ats_type, identifier_or_url)
                    ats_type, board_identifier = result
                    if ats_type:
                        print(f"✅ Discovered {company_name}: {ats_type} -> {board_identifier}")
            except Exception as e:
                print(f"⚠️  ATS discovery failed for {company_name}: {e}")
        
        # Prepare company document
        company_doc = {
            'name': company_name,
            'domain': domain,
            'ats_type': ats_type or 'unknown',
            'board_identifier': board_identifier,
            'metadata': {
                'size': 'startup',
                'industry': company_data.get('description', ''),
                'location': company_data.get('location', ''),
                'source': 'benlang',
                'raw_name': company_data.get('raw_name', company_name)
            },
            'stats': {
                'active_jobs': 0,
                'total_jobs_found': 0
            }
        }
        
        # Insert into database
        if not self.dry_run and self.db is not None:
            try:
                self.db.companies.insert_one(company_doc)
            except Exception as e:
                return {
                    'name': company_name,
                    'status': 'error',
                    'error': str(e)
                }
        
        return {
            'name': company_name,
            'status': 'imported',
            'domain': domain,
            'ats_type': ats_type or 'unknown',
            'career_url': career_info.get('career_url')
        }


def main():
    """Main execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Import Ben Lang companies')
    parser.add_argument('--file', default='BenLang.txt', help='Input file name')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no DB writes)')
    args = parser.parse_args()
    
    # Parse companies
    file_path = Path(__file__).parent.parent / 'data' / 'ImportList' / args.file
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return 1
    
    print(f"📋 Parsing companies from {args.file}...")
    benlang_parser = BenLangParser()
    companies = benlang_parser.parse_file(str(file_path))
    # Reverse the order so new companies (at the bottom of the file) are processed first
    companies.reverse()
    
    # For quick testing/verification, let's process only the first 20 (newest)
    # companies = companies[:20] 
    # Just uncomment above line if needed, but I'll update the print to reflect
    print(f"✅ Found {len(companies)} companies (Processing newest first)\n")
    
    import asyncio
    
    # Import
    print(f"{'🔍' if args.dry_run else '📥'} {'DRY RUN - ' if args.dry_run else ''}Importing companies...\n")
    importer = BenLangImporter(dry_run=args.dry_run)
    # results = importer.import_all(companies)
    results = asyncio.run(importer.import_all_async(companies))
    
    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"Total companies: {results['total']}")
    print(f"✅ Imported: {results['imported']}")
    print(f"ℹ️  Already exists: {results['exists']}")
    print(f"❌ Failed: {results['failed']}")
    print(f"Success rate: {(results['imported'] / results['total'] * 100):.1f}%")

    # Update Collection
    if not args.dry_run:
        db = get_db()
        valid_companies = [r['name'] for r in results['companies'] if r['status'] in ('imported', 'exists')]
        
        if valid_companies:
            print(f"\n📚 Updating 'ben-lang-feb-2024' collection with {len(valid_companies)} companies...")
            db.collections.update_one(
                {'id': 'ben-lang-feb-2024'},
                {'$set': {
                    'name': "Ben Lang's List",
                    'data.companies': valid_companies, 
                    'updated_at': datetime.utcnow(),
                    'count': len(valid_companies)
                }},
                upsert=True
            )
            print("✅ Collection updated")
    
    # Generate CSV Report
    report_path = Path(__file__).parent.parent / 'data' / 'ImportList' / 'benlang_import_report.csv'
    import csv
    with open(report_path, 'w', newline='') as csvfile:
        fieldnames = ['company', 'status', 'ats_type', 'career_url', 'error']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for r in results['companies']:
            writer.writerow({
                'company': r['name'],
                'status': r['status'],
                'ats_type': r.get('ats_type', ''),
                'career_url': r.get('career_url', ''),
                'error': r.get('error', '')
            })
    print(f"\n📝 Report generated: {report_path}")

    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No changes made to database")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
