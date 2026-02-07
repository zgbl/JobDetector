import aiohttp
import asyncio
import ssl
import json
import logging
import re
from typing import List, Dict, Optional
from datetime import datetime
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

class AshbyScraper(BaseScraper):
    """Ashby ATS Scraper (jobs.ashbyhq.com)"""
    
    def __init__(self):
        super().__init__("ashby")
        
    async def scrape(self, company: Dict) -> List[Dict]:
        """
        Scrape Ashby jobs.
        Args:
            company: Must have 'ats_url' (e.g. https://jobs.ashbyhq.com/anthropic) 
                     or we try to derive it from name.
        """
        self.logger.info(f"Starting Ashby scrape for {company['name']}...")
        
        # 1. Determine Target URL
        url = company.get('ats_url')
        if not url:
            # Fallback: Assume jobs.ashbyhq.com/company-slug
            slug = company['name'].lower().replace(' ', '') # "Scale AI" -> scaleai (might be wrong, better to rely on ats_url)
            # Try hyphenated too
            slugs_to_try = [slug, company['name'].lower().replace(' ', '-')]
            
            for s in slugs_to_try:
                test_url = f"https://jobs.ashbyhq.com/{s}"
                if await self._validate_url(test_url):
                     url = test_url
                     break
        
        if not url:
             self.logger.warning(f"Could not determine Ashby URL for {company['name']}")
             return []
             
        # Normalize URL to ensure it ends with slash or no slash consistently?
        # Actually we want the API Endpoint.
        # Ashby uses a hidden API: https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams
        # But even easier, they often embed __NEXT_DATA__ in the HTML.
        
        jobs = await self._scrape_via_html_parsing(url, company['name'])
        self.logger.info(f"Scraped {len(jobs)} jobs from {company['name']} (Ashby)")
        return jobs

    async def _validate_url(self, url):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, timeout=5) as resp:
                    return resp.status == 200
        except:
            return False

    async def _scrape_via_html_parsing(self, url: str, company_name: str) -> List[Dict]:
        """
        Ashby renders mostly server-side or hydrates via JSON.
        We will try to fetch the HTML and parse the script tags or the DOM.
        """
        # SSL Context
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=ssl_context) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to fetch {url}: {response.status}")
                    return []
                html_content = await response.text()
                
        # Method 1: Look for __NEXT_DATA__
        soup = BeautifulSoup(html_content, 'html.parser')
        next_data = soup.find('script', id='__NEXT_DATA__')
        
        if next_data:
            try:
                data = json.loads(next_data.string)
                # Traverse: props -> pageProps -> jobBoard -> jobs
                # Note: Structure varies. Let's try to print keys if debugging.
                job_board = data.get('props', {}).get('pageProps', {}).get('jobBoard', {})
                raw_jobs = job_board.get('jobs', [])
                
                if raw_jobs:
                    return [self._parse_job(j, company_name, url) for j in raw_jobs]
            except Exception as e:
                self.logger.warning(f"Failed to parse __NEXT_DATA__: {e}")

        # Method 2: Use the unofficial public API endpoint (more reliable if next_data fails)
        # We need the 'organization' slug from the URL.
        # url: https://jobs.ashbyhq.com/anthropic -> slug: anthropic
        slug_match = re.search(r'jobs\.ashbyhq\.com/([^/]+)', url)
        if slug_match:
            slug = slug_match.group(1)
            return await self._scrape_via_api(slug, company_name)
            
        return []

    async def _scrape_via_api(self, slug: str, company_name: str) -> List[Dict]:
        """
        Ashby has a public-ish API used by their frontend.
        Endpoint: https://api.ashbyhq.com/posting-api/job-board/{slug}
        """
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        
        # SSL Context
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, ssl=ssl_context) as response:
                    if response.status == 200:
                        data = await response.json()
                        raw_jobs = data.get('jobs', [])
                        return [self._parse_job(j, company_name, f"https://jobs.ashbyhq.com/{slug}") for j in raw_jobs]
        except Exception as e:
            self.logger.error(f"Ashby API scrape failed for {slug}: {e}")
            
        return []

    def _parse_job(self, raw_job: Dict, company_name: str, base_url: str) -> Dict:
        """
        Parse generic Ashby job object.
        """
        # ID
        job_id = f"ashby_{raw_job.get('id')}"
        
        # Title
        title = raw_job.get('title', 'Unknown Role')
        
        # Location
        # Ashby locations can be complex objects or strings
        loc_raw = raw_job.get('location') or raw_job.get('address') or {}
        if isinstance(loc_raw, dict):
            # Try to build a string: "San Francisco, CA, USA"
            parts = [loc_raw.get('city'), loc_raw.get('region'), loc_raw.get('country')]
            location = ", ".join([p for p in parts if p])
        else:
            location = str(loc_raw)
            
        if not location:
            # Maybe it's remote?
            if raw_job.get('isRemote'):
                location = "Remote"
            else:
                location = "Unknown"

        # URL
        # Usually base_url + / + id
        source_url = raw_job.get('jobUrl')
        if not source_url:
            short_code = raw_job.get('shortcode') # Some versions use shortcode
            # If we used the API, we need to construct it
            # Standard: https://jobs.ashbyhq.com/{org}/{id} 
            # But we only have base_url which might be the org page.
            if base_url.endswith('/'): base_url = base_url[:-1]
            source_url = f"{base_url}/{raw_job.get('id')}"

        # Description
        # API often returns 'descriptionHtml'
        description = raw_job.get('descriptionHtml') or raw_job.get('description') or ""
        
        # Clean HTML
        if description:
            description = self._clean_html(description)

        # Meta
        posted_at = raw_job.get('publishedAt')
        if posted_at:
             try:
                 posted_date = datetime.fromisoformat(posted_at.replace('Z', '+00:00'))
             except:
                 posted_date = datetime.utcnow()
        else:
            posted_date = datetime.utcnow()

        # Job Type / Remote
        job_type = "Full-time" # Default
        employment_type = raw_job.get('employmentType')
        if employment_type:
            job_type = employment_type.replace('_', ' ').title()
            
        remote_type = "On-site"
        if raw_job.get('isRemote'):
            remote_type = "Remote"
        
        # Skills & Salary
        skills = self.extract_skills(description)
        salary = self.extract_salary(description)
        # Also check structured compensation
        comp = raw_job.get('compensation')
        if not salary and comp:
             # Try to parse obj
             # { "min": 100, "max": 200, "currency": "USD", "type": "Yearly" }
             if isinstance(comp, dict) and comp.get('min'):
                 salary = {
                     'min': int(comp.get('min')),
                     'max': int(comp.get('max')),
                     'currency': comp.get('currency', 'USD')
                 }

        content_hash = self.generate_content_hash(title, description, location)
        
        return {
            'job_id': job_id,
            'title': title,
            'company': company_name,
            'location': location,
            'salary': salary,
            'job_type': job_type,
            'remote_type': remote_type,
            'description': description,
            'requirements': [],
            'skills': skills,
            'source': 'ashby',
            'source_url': source_url,
            'posted_date': posted_date,
            'scraped_at': datetime.utcnow(),
            'last_seen_at': datetime.utcnow(),
            'content_hash': content_hash,
            'is_active': True,
            'raw_data': raw_job
        }

    def _clean_html(self, html_text):
        soup = BeautifulSoup(html_text, 'html.parser')
        return soup.get_text(separator='\n', strip=True)

# Test
async def main():
    scraper = AshbyScraper()
    # Test with Anthropic (known Ashby user)
    company = {
        "name": "Anthropic",
        "ats_url": "https://jobs.ashbyhq.com/anthropic"
    }
    jobs = await scraper.scrape(company)
    print(f"Found {len(jobs)} jobs")
    if jobs:
        print(jobs[0])

if __name__ == "__main__":
    asyncio.run(main())
