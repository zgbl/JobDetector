#!/usr/bin/env python3
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime
import re

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.ashby import AshbyScraper
from src.scrapers.workable import WorkableScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SmartImport")

async def discover_ats(company_name, domain):
    """
    尝试为新公司发现 ATS 系统
    """
    scrapers = {
        'greenhouse': GreenhouseScraper(),
        'lever': LeverScraper(),
        'ashby': AshbyScraper(),
        'workable': WorkableScraper()
    }
    
    # 构造基本的测试对象
    company_test = {
        'name': company_name,
        'domain': domain
    }
    
    # 1. 尝试 Greenhouse
    token = await scrapers['greenhouse']._get_board_token(company_test)
    if token:
        return 'greenhouse', f"https://boards.greenhouse.io/{token}"
        
    # 2. 尝试 Lever
    # Lever usually uses jobs.lever.co/token
    lever_token = domain.replace('.com', '').replace('.', '').replace('https://', '').replace('www', '')
    # Simple check for Lever can be added here
    return None, None

async def smart_import(company_list):
    db = get_db()
    
    new_companies = []
    skipped_count = 0
    
    logger.info(f"🔍 正在处理 {len(company_list)} 个目标公司...")
    
    for item in company_list:
        name = item.get('name')
        domain = item.get('domain')
        
        if not name or not domain:
            continue
            
        # 1. 查重 (Name or Domain)
        existing = db.companies.find_one({
            '$or': [
                {'name': {'$regex': f'^{re.escape(name)}$', '$options': 'i'}},
                {'domain': domain.lower()}
            ]
        })
        
        if existing:
            skipped_count += 1
            continue
            
        # 2. 发现 ATS
        ats_type, ats_url = await discover_ats(name, domain)
        
        company_doc = {
            'name': name,
            'domain': domain.lower(),
            'ats_url': ats_url,
            'is_active': True,
            'ats_system': {
                'type': ats_type or 'custom',
                'detected_at': datetime.utcnow(),
                'api_endpoint': None,
                'confidence': 1.0 if ats_type else 0.5
            },
            'schedule': {
                'frequency_hours': 12,
                'last_scraped_at': None,
                'next_scrape_at': None,
                'priority': 2
            },
            'stats': {
                'total_jobs_found': 0,
                'active_jobs': 0,
                'avg_new_jobs_per_week': 0.0,
                'scrape_success_rate': 1.0,
                'last_error': None
            },
            'metadata': {
                'industry': item.get('industry'),
                'size': item.get('size', 'Unknown'),
                'headquarters': item.get('hq', 'US'),
                'tags': item.get('tags', []),
                'added_by': 'smart_import_us',
                'added_at': datetime.utcnow(),
                'verified': False
            }
        }
        
        new_companies.append(company_doc)
        logger.info(f"➕ 准备导入 {name} (ATS: {ats_type or 'Unknown'})")
        
    if new_companies:
        logger.info(f"🚀 正在批量导入 {len(new_companies)} 个新公司...")
        db.companies.insert_many(new_companies)
        logger.info(f"✅ 导入完成。")
    else:
        logger.info("ℹ️ 没有发现需要添加的新公司。")
        
    logger.info(f"📊 汇总: 处理 {len(company_list)}，新增 {len(new_companies)}，跳过 {skipped_count}")
    close_db()
    return [c['name'] for c in new_companies]

async def audit_silent_companies():
    """
    审计并修复没有职位的公司
    """
    db = get_db()
    silent_companies = list(db.companies.find({
        'stats.active_jobs': 0,
        'is_active': True
    }))
    
    logger.info(f"🕵️ 正在审计 {len(silent_companies)} 家职位数为 0 的公司...")
    
    fixed_count = 0
    for company in silent_companies:
        # 如果没有 ats_url 或者 ats_system.type 是 custom，尝试重新发现
        if not company.get('ats_url') or company.get('ats_system', {}).get('type') == 'custom':
            logger.info(f"🔍 尝试修复 {company['name']}...")
            ats_type, ats_url = await discover_ats(company['name'], company['domain'])
            
            if ats_type and ats_url:
                db.companies.update_one(
                    {'_id': company['_id']},
                    {'$set': {
                        'ats_url': ats_url,
                        'ats_system.type': ats_type,
                        'ats_system.confidence': 1.0,
                        'ats_system.detected_at': datetime.utcnow()
                    }}
                )
                logger.info(f"✅ 已修复 {company['name']}: {ats_type} -> {ats_url}")
                fixed_count += 1
                
    logger.info(f"🏁 审计完成。修复了 {fixed_count} 家公司。")
    close_db()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true", help="Audit silent companies")
    args = parser.parse_args()
    
    if args.audit:
        asyncio.run(audit_silent_companies())
    else:
        # 默认运行 Smart Import
        sample_list = [
            {'name': 'OpenAI', 'domain': 'openai.com', 'tags': ['AI', 'Research']},
            {'name': 'Anthropic', 'domain': 'anthropic.com', 'tags': ['AI', 'Safety']},
            {'name': 'NVIDIA', 'domain': 'nvidia.com', 'tags': ['AI', 'Hardware']},
            {'name': 'Cohere', 'domain': 'cohere.ai', 'tags': ['AI', 'NLP']},
            {'name': 'Perplexity AI', 'domain': 'perplexity.ai', 'tags': ['AI', 'Search']},
            {'name': 'Mistral AI', 'domain': 'mistral.ai', 'tags': ['AI', 'Open Source']},
            {'name': 'Databricks', 'domain': 'databricks.com', 'tags': ['Data', 'AI']},
            {'name': 'Snowflake', 'domain': 'snowflake.com', 'tags': ['Cloud', 'Data']},
            {'name': 'Stripe', 'domain': 'stripe.com', 'tags': ['Fintech', 'Payments']},
            {'name': 'Plaid', 'domain': 'plaid.com', 'tags': ['Fintech', 'Banking']},
            {'name': 'Affirm', 'domain': 'affirm.com', 'tags': ['Fintech', 'Lending']},
            {'name': 'Chime', 'domain': 'chime.com', 'tags': ['Fintech', 'Banking']},
            {'name': 'Gusto', 'domain': 'gusto.com', 'tags': ['Fintech', 'HR']},
            {'name': 'Rippling', 'domain': 'rippling.com', 'tags': ['Fintech', 'HR']},
            {'name': 'Deel', 'domain': 'deel.com', 'tags': ['Fintech', 'Remote']},
            {'name': 'Brex', 'domain': 'brex.com', 'tags': ['Fintech', 'Corporate Card']},
            {'name': 'Ramp', 'domain': 'ramp.com', 'tags': ['Fintech', 'Finance']},
            {'name': 'Vanta', 'domain': 'vanta.com', 'tags': ['Cybersecurity', 'Compliance']},
            {'name': 'Wiz', 'domain': 'wiz.io', 'tags': ['Cybersecurity', 'Cloud']},
            {'name': 'Snyk', 'domain': 'snyk.io', 'tags': ['Cybersecurity', 'DevSecOps']},
            {'name': 'Docker', 'domain': 'docker.com', 'tags': ['Infrastructure', 'Containers']},
            {'name': 'Postman', 'domain': 'postman.com', 'tags': ['DevTools', 'API']}
        ]
        asyncio.run(smart_import(sample_list))
