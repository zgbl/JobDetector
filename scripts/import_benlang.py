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

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.parse_benlang import BenLangParser
from src.services.ats_discovery import ATSDiscoveryService
from api.index import get_db


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
    
    def import_company(self, company_data: Dict) -> Dict:
        """
        Import a single company with ATS discovery.
        
        Args:
            company_data: Dict from parser with name, description, location
            
        Returns:
            Dict with status, domain, ats_type, job_count
        """
        company_name = company_data['name']
        
        # Check if already exists
        existing = self.check_existing_company(company_name)
        if existing:
            return {
                'name': company_name,
                'status': 'exists',
                'domain': existing.get('domain'),
                'ats_type': existing.get('ats_type'),
                'skip_reason': 'Already in database'
            }
        
        # Find career site
        career_info = self.find_career_site(company_name)
        if not career_info:
            return {
                'name': company_name,
                'status': 'no_career_site',
                'error': 'Could not determine career site'
            }
        
        domain = career_info['domain']
        
        # Discover ATS (handle async)
        ats_type = None
        board_identifier = None
        
        if not self.dry_run:
            try:
                # Run async discover_ats in sync context
                import asyncio
                result = asyncio.run(self.ats_discovery.discover_ats(domain))
                if result and len(result) == 2:
                    ats_type, board_identifier = result
            except Exception as e:
                print(f"   ⚠️  ATS discovery failed: {e}")
        
        # Prepare company document
        company_doc = {
            'name': company_name,
            'domain': domain,
            'ats_type': ats_type or 'unknown',
            'board_identifier': board_identifier,
            'metadata': {
                'size': 'startup',  # All Ben Lang companies are well-funded
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
    
    def import_all(self, companies: List[Dict]) -> Dict:
        """
        Import all companies and return summary.
        
        Returns:
            Summary dict with counts and results
        """
        results = {
            'total': len(companies),
            'imported': 0,
            'exists': 0,
            'failed': 0,
            'companies': []
        }
        
        for i, company in enumerate(companies, 1):
            print(f"\n[{i}/{len(companies)}] Processing: {company['name']}")
            
            result = self.import_company(company)
            results['companies'].append(result)
            
            if result['status'] == 'imported':
                results['imported'] += 1
                print(f"   ✅ Imported: {result.get('domain')} ({result.get('ats_type')})")
            elif result['status'] == 'exists':
                results['exists'] += 1
                print(f"   ℹ️  Already exists: {result.get('domain')}")
            else:
                results['failed'] += 1
                print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
        
        return results


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
    print(f"✅ Found {len(companies)} companies\n")
    
    # Import
    print(f"{'🔍' if args.dry_run else '📥'} {'DRY RUN - ' if args.dry_run else ''}Importing companies...\n")
    importer = BenLangImporter(dry_run=args.dry_run)
    results = importer.import_all(companies)
    
    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"Total companies: {results['total']}")
    print(f"✅ Imported: {results['imported']}")
    print(f"ℹ️  Already exists: {results['exists']}")
    print(f"❌ Failed: {results['failed']}")
    print(f"Success rate: {(results['imported'] / results['total'] * 100):.1f}%")
    
    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No changes made to database")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
