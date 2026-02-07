"""
ATS Discovery Service ('The Link Hunter')
Crawls company homepages to find their ATS (Applicant Tracking System) URL.
"""
import aiohttp
import asyncio
import re
import logging
from bs4 import BeautifulSoup
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("ATSDiscovery")

class ATSDiscoveryService:
    
    # Known ATS patterns
    ATS_PATTERNS = {
        'greenhouse': r'boards?\.greenhouse\.io',
        'lever': r'jobs\.lever\.co',
        'ashby': r'jobs\.ashbyhq\.com',
        'workable': r'apply\.workable\.com',
        'breezy': r'\.breezy\.hr',
        'workday': r'myworkdayjobs\.com'
    }
    
    # Text to look for in links
    CAREER_KEYWORDS = ['careers', 'jobs', 'join us', 'hiring', 'work with us', 'open positions', 'openings', 'team']
    
    async def discover_ats(self, domain_or_url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Discover the ATS URL for a given domain.
        Returns: (ats_url, ats_type) or (None, None)
        """
        # 1. Normalize URL
        start_url = domain_or_url
        if not start_url.startswith('http'):
            start_url = f"https://{start_url}"
            
        logger.info(f"🔍 Discovery: Starting hunt for {start_url}")
        
        # SSL Context to ignore verification
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        try:
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(connector=connector, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}) as session:
                
                # Check 1: Is the input URL already an ATS?
                ats_type = self._identify_ats_type(start_url)
                if ats_type:
                    return start_url, ats_type
                
                # Check 1.5: Active Probing (Guessing)
                # Extract slug from domain
                domain_parts = urlparse(start_url).netloc.split('.')
                if domain_parts[0] == 'www':
                    domain_parts = domain_parts[1:]
                
                # For smarthr.co.jp, we want 'smarthr'
                # parts: ['smarthr', 'co', 'jp']
                # If last parts are common TLDs, ignore them
                tlds = ['com', 'co', 'jp', 'net', 'org', 'ai', 'io', 'ne']
                
                filtered_parts = [p for p in domain_parts if p.lower() not in tlds]
                if filtered_parts:
                    slug = filtered_parts[0]
                else:
                    slug = domain_parts[0]
                
                if slug in ['www', 'careers', 'jobs']: # Bad extraction fallback
                    slug = domain_parts[-2] if len(domain_parts) >= 2 else domain_parts[0]
                
                logger.info(f"🕵️  Probing ATS patterns for slug: '{slug}'")
                probed_url, probed_type = await self._probe_known_ats_patterns(session, slug)
                if probed_url:
                    logger.info(f"✅ Active Probe Hit: {probed_url} ({probed_type})")
                    return probed_url, probed_type
                    
                # Check 2: Fetch homepage and look for ATS links directly
                try:
                    html_content = await self._fetch(session, start_url)
                except Exception as e:
                    # Try www subdomain if failed
                    if 'www' not in start_url:
                        start_url = start_url.replace('https://', 'https://www.')
                        html_content = await self._fetch(session, start_url)
                    else:
                        logger.warning(f"Could not fetch homepage for {start_url}: {e}")
                        return None, None

                # Look for direct ATS links in homepage
                ats_link, found_type = self._find_ats_link_in_html(html_content, start_url)
                if ats_link:
                    logger.info(f"✅ Found direct ATS link: {ats_link} ({found_type})")
                    return ats_link, found_type
                
                # Check 3: Find "Careers" page and crawl it
                career_page_url = self._find_career_page_link(html_content, start_url)
                if career_page_url:
                    logger.info(f"➡️  Found Careers page: {career_page_url}. Crawling...")
                    # Is the career page itself on an ATS domain? (Redirects often happen here)
                    # We need to fetch it to see where it lands or what it contains
                    try:
                        async with session.get(career_page_url, allow_redirects=True, timeout=10) as resp:
                            final_url = str(resp.url)
                            
                            # Did we get redirected to an ATS?
                            ats_type = self._identify_ats_type(final_url)
                            if ats_type:
                                logger.info(f"✅ Redirected to ATS: {final_url} ({ats_type})")
                                return final_url, ats_type
                                
                            # If not, parse the career page content
                            career_html = await resp.text()
                            ats_link, found_type = self._find_ats_link_in_html(career_html, final_url)
                            if ats_link:
                                logger.info(f"✅ Found ATS link on careers page: {ats_link} ({found_type})")
                                return ats_link, found_type
                                
                    except Exception as e:
                        logger.warning(f"Failed to crawl career page {career_page_url}: {e}")

        except Exception as e:
            logger.error(f"Discovery failed for {start_url}: {e}")
            
        logger.warning(f"❌ Could not find ATS for {start_url}")
        return None, None

    async def _fetch(self, session, url):
        async with session.get(url, timeout=10) as response:
            return await response.text()

    async def _probe_known_ats_patterns(self, session, slug: str) -> Tuple[Optional[str], Optional[str]]:
        """Try to guess ATS URLs based on the company slug"""
        
        # Patterns to try
        probes = [
            (f"https://jobs.ashbyhq.com/{slug}", "ashby"),
            (f"https://boards.greenhouse.io/{slug}", "greenhouse"),
            (f"https://jobs.lever.co/{slug}", "lever"),
            (f"https://apply.workable.com/{slug}", "workable"),
            (f"https://{slug}.breezy.hr", "breezy")
        ]
        
        for url, type in probes:
            try:
                # Use GET with small timeout, or HEAD
                async with session.get(url, timeout=5, allow_redirects=True) as resp:
                    if resp.status == 200:
                        # Double check content to ensure it's not a generic 200 page
                        # For Ashby/Greenhouse, 200 usually means it exists.
                        # Some might redirect to homepage if invalid.
                        final_url = str(resp.url)
                        # Verify we are still on the ATS domain
                        if self._identify_ats_type(final_url) == type:
                            # Special check for Ashby: it returns 200 for 404s
                            if type == 'ashby':
                                text = await resp.text()
                                # Valid boards have a populated jobBoard object in __appData
                                # Invalid ones have "jobBoard":null
                                if '"jobBoard":null' in text:
                                    logger.debug(f"🔍 Probe: Ashby returned 200 but jobBoard is null for {url}")
                                    continue
                            
                            # Special check for Workable: it returns 200 for 404s
                            if type == 'workable':
                                text = await resp.text()
                                if 'name="account" content=""' in text:
                                    logger.debug(f"🔍 Probe: Workable returned 200 but account is empty for {url}")
                                    continue
                            
                            return final_url, type
            except:
                continue
                
        return None, None

    def _identify_ats_type(self, url: str) -> Optional[str]:
        """Check if a URL matches known ATS patterns"""
        for ats_type, pattern in self.ATS_PATTERNS.items():
            if re.search(pattern, url):
                return ats_type
        return None

    def _find_ats_link_in_html(self, html_content: str, base_url: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse HTML to find links to known ATS domains"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Resolve relative URLs (though ATS links are usually absolute)
            full_url = urljoin(base_url, href)
            
            ats_type = self._identify_ats_type(full_url)
            if ats_type:
                # Basic cleaning: remove query params if they look like trackers? 
                # For now keep them as some ATS use them.
                return full_url, ats_type
                
        return None, None

    def _find_career_page_link(self, html_content: str, base_url: str) -> Optional[str]:
        """Find the internal link to the careers page"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. Look for links with keyword text
        for a in soup.find_all('a', href=True):
            text = a.get_text().lower().strip()
            href = a['href']
            
            # Skip mailto, tel, javascript
            if href.startswith(('mailto:', 'tel:', 'javascript:', '#')):
                continue
                
            # Check keywords
            for keyword in self.CAREER_KEYWORDS:
                if keyword in text:
                    return urljoin(base_url, href)
                    
            # Check href itself for 'careers' or 'jobs' if text match failed
            if 'careers' in href.lower() or 'jobs' in href.lower():
                 return urljoin(base_url, href)
                 
        return None

# For manual testing
async def main():
    service = ATSDiscoveryService()
    logging.basicConfig(level=logging.INFO)
    
    test_domains = [
        "https://www.anthropic.com",
        "https://openai.com",
        "https://www.scale.com",
        "https://perplexity.ai" 
    ]
    
    for domain in test_domains:
        url, type = await service.discover_ats(domain)
        print(f"RESULT for {domain}: {url} [{type}]")

if __name__ == "__main__":
    asyncio.run(main())
