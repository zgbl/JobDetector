#!/usr/bin/env python3
"""
Company Import Script
Imports companies from YAML file into MongoDB
"""
import sys
import os
import yaml
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
from src.database.models import Company, ATSSystem, CompanyMetadata, Schedule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_companies_from_yaml(yaml_file: str) -> list:
    """
    从YAML文件加载公司列表
    
    Args:
        yaml_file: YAML文件路径
        
    Returns:
        公司数据列表
    """
    try:
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data.get('companies', [])
    except FileNotFoundError:
        logger.error(f"File not found: {yaml_file}")
        return []
    except yaml.YAMLError as e:
        logger.error(f"YAML parsing error: {e}")
        return []


def create_company_object(company_data: dict) -> Company:
    """
    从字典数据创建Company对象
    
    Args:
        company_data: 公司数据字典
        
    Returns:
        Company对象
    """
    # Create ATS system info
    ats_type = company_data.get('ats_type', 'custom')
    ats_system = ATSSystem(type=ats_type)
    
    # Create metadata
    metadata = CompanyMetadata(
        industry=company_data.get('industry'),
        size=company_data.get('size'),
        headquarters=company_data.get('headquarters'),
        tags=company_data.get('tags', []),
        added_by='import_script',
        added_at=datetime.utcnow()
    )
    
    # Create schedule (default: every 12 hours, priority 1)
    schedule = Schedule(
        frequency_hours=12,
        priority=1
    )
    
    # Create company object
    company = Company(
        name=company_data['name'],
        domain=company_data['domain'],
        ats_system=ats_system,
        metadata=metadata,
        schedule=schedule,
        is_active=True
    )
    
    return company


def import_companies(yaml_file: str, update_existing: bool = False):
    """
    导入公司到数据库
    
    Args:
        yaml_file: YAML文件路径
        update_existing: 是否更新已存在的公司
    """
    db = get_db()
    companies_data = load_companies_from_yaml(yaml_file)
    
    if not companies_data:
        logger.warning("No companies found in YAML file")
        return
    
    logger.info(f"Found {len(companies_data)} companies in YAML file")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    update_count = 0
    
    for idx, company_data in enumerate(companies_data, 1):
        try:
            name = company_data.get('name')
            domain = company_data.get('domain')
            
            if not name or not domain:
                logger.warning(f"[{idx}/{len(companies_data)}] Missing name or domain, skipping")
                skip_count += 1
                continue
            
            # Check if company already exists
            existing = db.companies.find_one({'domain': domain})
            
            if existing:
                if update_existing:
                    # Update existing company
                    company = create_company_object(company_data)
                    db.companies.update_one(
                        {'domain': domain},
                        {'$set': company.to_dict()}
                    )
                    logger.info(f"[{idx}/{len(companies_data)}] ✅ Updated: {name}")
                    update_count += 1
                else:
                    logger.info(f"[{idx}/{len(companies_data)}] ⏭️  Already exists: {name} (skipped)")
                    skip_count += 1
            else:
                # Insert new company
                company = create_company_object(company_data)
                db.companies.insert_one(company.to_dict())
                logger.info(f"[{idx}/{len(companies_data)}] ✅ Imported: {name}")
                success_count += 1
                
        except Exception as e:
            logger.error(f"[{idx}/{len(companies_data)}] ❌ Error importing {company_data.get('name', 'unknown')}: {e}")
            error_count += 1
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("Import Summary")
    logger.info("="*60)
    logger.info(f"Total companies in file: {len(companies_data)}")
    logger.info(f"✅ Successfully imported: {success_count}")
    logger.info(f"🔄 Updated: {update_count}")
    logger.info(f"⏭️  Skipped (already exists): {skip_count}")
    logger.info(f"❌ Errors: {error_count}")
    logger.info("="*60)
    
    # Verification
    total_in_db = db.companies.count_documents({})
    logger.info(f"\n📊 Total companies in database: {total_in_db}")
    
    # Show sample companies
    logger.info("\n📋 Sample companies in database:")
    sample_companies = db.companies.find().limit(5)
    for company in sample_companies:
        logger.info(f"  - {company['name']} ({company['domain']}) - ATS: {company.get('ats_system', {}).get('type', 'unknown')}")


def show_statistics():
    """显示数据库统计信息"""
    db = get_db()
    
    total = db.companies.count_documents({})
    active = db.companies.count_documents({'is_active': True})
    
    # Group by ATS type
    pipeline = [
        {'$group': {
            '_id': '$ats_system.type',
            'count': {'$sum': 1}
        }},
        {'$sort': {'count': -1}}
    ]
    
    ats_stats = list(db.companies.aggregate(pipeline))
    
    logger.info("\n" + "="*60)
    logger.info("Company Statistics")
    logger.info("="*60)
    logger.info(f"Total companies: {total}")
    logger.info(f"Active companies: {active}")
    logger.info(f"\nBy ATS System:")
    for stat in ats_stats:
        ats_type = stat['_id'] or 'unknown'
        count = stat['count']
        percentage = (count / total * 100) if total > 0 else 0
        logger.info(f"  - {ats_type}: {count} ({percentage:.1f}%)")
    logger.info("="*60)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Import companies from YAML file')
    parser.add_argument(
        '--file',
        default='data/companies_initial.yaml',
        help='YAML file path (default: data/companies_initial.yaml)'
    )
    parser.add_argument(
        '--update',
        action='store_true',
        help='Update existing companies'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show statistics only (no import)'
    )
    
    args = parser.parse_args()
    
    try:
        if args.stats:
            # Show statistics only
            show_statistics()
        else:
            # Import companies
            yaml_file = Path(project_root) / args.file
            
            if not yaml_file.exists():
                logger.error(f"File not found: {yaml_file}")
                sys.exit(1)
            
            logger.info(f"🚀 Starting company import from: {yaml_file}")
            import_companies(str(yaml_file), update_existing=args.update)
            
            # Show statistics
            show_statistics()
        
        logger.info("\n✅ Import completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        close_db()


if __name__ == '__main__':
    main()
