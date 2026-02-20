#!/usr/bin/env python3
"""
Company Ingestion Pipeline
Parses unstructured company lists using LLM, performs fuzzy matching for deduplication,
and discovers ATS metadata for new companies.
"""
import os
import sys
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Missing dependencies will be checked at runtime
try:
    from rapidfuzz import fuzz, process
except ImportError:
    print("❌ Missing dependencies. Please run: pip install rapidfuzz")
    sys.exit(1)

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
from src.services.ats_discovery import ATSDiscoveryService

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("IngestionPipeline")

class IngestionPipeline:
    def __init__(self):
        self.provider = os.getenv("AI_PROVIDER", "anthropic").lower()
        self.api_key = os.getenv(f"{self.provider.upper()}_API_KEY")
        
        self.db = get_db()
        self.discovery_service = ATSDiscoveryService()
        self.client = self._init_client()

    def _init_client(self):
        if not self.api_key:
            logger.warning(f"⚠️  {self.provider.upper()}_API_KEY not found. AI extraction disabled.")
            return None

        try:
            if self.provider == "anthropic":
                import anthropic
                return anthropic.Anthropic(api_key=self.api_key)
            elif self.provider == "gemini":
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                return genai.GenerativeModel('gemini-1.5-flash')
            elif self.provider in ["deepseek", "openai", "qwen"]:
                from openai import OpenAI
                base_url = os.getenv(f"{self.provider.upper()}_BASE_URL")
                return OpenAI(api_key=self.api_key, base_url=base_url)
        except ImportError:
            logger.error(f"❌ Missing SDK for {self.provider}. Please install it.")
        return None

    async def extract_companies_from_file(self, file_path: Path) -> List[Dict[str, str]]:
        """Parses messy text into a list of company names and domains using the selected AI."""
        if not self.client:
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            logger.info(f"🧠 Using {self.provider.upper()} for parsing ({len(content)} chars)...")
            
            prompt = f"""
            Identify and extract all company names from the following unstructured text. 
            For each company, suggest a likely website domain (e.g., "Google" -> "google.com").
            Return ONLY a JSON array of objects with "name" and "domain" keys.
            
            Text:
            ---
            {content}
            ---
            """

            text_response = ""
            if self.provider == "anthropic":
                response = self.client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=2000,
                    temperature=0,
                    system="You are a data extraction assistant. Return only valid JSON.",
                    messages=[{"role": "user", "content": prompt}]
                )
                text_response = response.content[0].text
            elif self.provider == "gemini":
                response = await self.client.generate_content_async(prompt)
                text_response = response.text
            elif self.provider in ["openai", "deepseek", "qwen"]:
                model = os.getenv(f"{self.provider.upper()}_MODEL") or "gpt-3.5-turbo"
                if self.provider == "deepseek": model = "deepseek-chat"
                
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Return only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0
                )
                text_response = response.choices[0].message.content

            # Extract JSON from response
            start_idx = text_response.find('[')
            end_idx = text_response.rfind(']') + 1
            if start_idx == -1 or end_idx == 0:
                logger.error("AI did not return a valid JSON array.")
                return []
            
            return json.loads(text_response[start_idx:end_idx])

        except Exception as e:
            logger.error(f"Error during {self.provider.upper()} extraction: {e}")
            return []

    def get_existing_companies(self) -> List[Dict[str, Any]]:
        """Fetch all existing companies for fuzzy matching."""
        return list(self.db.companies.find({}, {"name": 1, "domain": 1}))

    def find_duplicate(self, name: str, domain: str, existing: List[Dict[str, Any]], threshold: int = 90) -> Optional[Dict]:
        """Checks for duplicates using exact domain match and fuzzy name match."""
        # 1. Exact domain match
        for comp in existing:
            if comp.get('domain') == domain.lower():
                return comp
        
        # 2. Fuzzy name match
        names = [c['name'] for c in existing]
        best_match = process.extractOne(name, names, scorer=fuzz.token_set_ratio)
        
        if best_match and best_match[1] >= threshold:
            # Find the original object
            for comp in existing:
                if comp['name'] == best_match[0]:
                    return comp
        
        return None

    async def process_list(self, file_path: str):
        """Main pipeline execution."""
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return

        # 1. Extract
        companies_to_import = await self.extract_companies_from_file(path)
        if not companies_to_import:
            logger.warning("No companies extracted.")
            return

        logger.info(f"✅ Extracted {len(companies_to_import)} companies from file.")

        # 2. Match & De-duplicate
        existing = self.get_existing_companies()
        new_companies = []
        duplicates_count = 0

        for item in companies_to_import:
            name = item['name']
            domain = item['domain']
            
            duplicate = self.find_duplicate(name, domain, existing)
            if duplicate:
                logger.info(f"⏭️  Skipping duplicate: {name} (Matched with {duplicate['name']})")
                duplicates_count += 1
                continue
            
            new_companies.append(item)

        logger.info(f"📊 Filtering stats: {duplicates_count} duplicates found, {len(new_companies)} new companies.")

        # 3. Discover & Import
        final_list = []
        for item in new_companies:
            name = item['name']
            domain = item['domain']
            
            logger.info(f"🔍 Discovering ATS for {name} ({domain})...")
            ats_url, ats_type = await self.discovery_service.discover_ats(domain)
            
            company_doc = {
                'name': name,
                'domain': domain.lower(),
                'ats_url': ats_url,
                'is_active': True,
                'ats_system': {
                    'type': ats_type or 'custom',
                    'detected_at': datetime.utcnow(),
                    'confidence': 1.0 if ats_type else 0.5
                },
                'schedule': {
                    'frequency_hours': 12,
                    'priority': 2
                },
                'metadata': {
                    'added_by': 'ingestion_pipeline',
                    'added_at': datetime.utcnow(),
                    'verified': False,
                    'tags': ['manual_import']
                }
            }
            final_list.append(company_doc)
            logger.info(f"✨ Ready: {name} | ATS: {ats_type or 'Unknown'} | URL: {ats_url or 'N/A'}")

        # 4. Save to DB
        if final_list:
            logger.info(f"💾 Saving {len(final_list)} companies to database...")
            self.db.companies.insert_many(final_list)
            logger.info("✅ Import complete.")
        else:
            logger.info("ℹ️ No new companies to save.")

async def main():
    if len(sys.argv) < 2:
        print("Usage: python ingestion_pipeline.py <path_to_list>")
        sys.exit(1)
    
    pipeline = IngestionPipeline()
    await pipeline.process_list(sys.argv[1])
    close_db()

if __name__ == "__main__":
    asyncio.run(main())
