"""
Workable ATS Scraper
Workable provides a public JSON API (v3) for job postings
"""
import aiohttp
import ssl
from typing import List, Dict, Optional
from datetime import datetime
import logging
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

class WorkableScraper(BaseScraper):
    """Workable ATS 专用采集器"""
    
    API_BASE = "https://apply.workable.com/api/v3/accounts"
    
    def __init__(self):
        super().__init__("workable")
        
    async def scrape(self, company: Dict) -> List[Dict]:
        """抓取Workable职位"""
        self.logger.info(f"开始抓取 {company['name']} 的职位 (Workable)...")
        
        slug = self._extract_slug(company)
        if not slug:
            self.logger.warning(f"无法获取 {company['name']} 的 Workable slug")
            return []
            
        url = f"{self.API_BASE}/{slug}/jobs"
        
        # SSL context
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        payload = {
            "query": "",
            "location": [],
            "department": [],
            "workplace": [],
            "worktype": []
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, ssl=ssl_context, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        self.logger.error(f"Workable API 请求失败: {response.status}")
                        return []
                        
                    data = await response.json()
                    jobs_data = data.get('results', [])
                    
                    jobs = []
                    for job_data in jobs_data:
                        try:
                            job = self._parse_job(job_data, company, slug)
                            if job:
                                jobs.append(job)
                        except Exception as e:
                            self.logger.error(f"解析 Workable 职位失败: {e}")
                            continue
                            
                    self.logger.info(f"从 {company['name']} 抓取到 {len(jobs)} 个职位")
                    return jobs
                    
        except Exception as e:
            self.logger.error(f"抓取 Workable 职位失败 ({company['name']}): {e}")
            return []

    def _extract_slug(self, company: Dict) -> Optional[str]:
        """从 ats_url 或 domain 提取 slug"""
        ats_url = company.get('ats_url', '')
        if 'workable.com/' in ats_url:
            # https://apply.workable.com/rakuten/ -> rakuten
            parts = ats_url.split('workable.com/')
            if len(parts) > 1:
                return parts[1].strip('/').split('/')[0]
                
        return company.get('domain', '').split('.')[0]

    def _parse_job(self, job_data: Dict, company: Dict, slug: str) -> Optional[Dict]:
        """解析 Workable 职位数据"""
        try:
            shortcode = job_data.get('shortcode')
            if not shortcode: return None
            
            job_id = f"workable_{shortcode}"
            title = job_data.get('title', '').strip()
            
            # Location
            loc_data = job_data.get('location', {})
            location = f"{loc_data.get('city', '')}, {loc_data.get('country', '')}".strip(', ')
            
            # URL
            source_url = f"https://apply.workable.com/{slug}/j/{shortcode}/"
            
            # Description
            description = job_data.get('description', '') or title
            
            # Published Date
            published = job_data.get('published')
            posted_date = None
            if published:
                try:
                    posted_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                except:
                    posted_date = None

            # Prepare for normalization
            normalized_raw = {
                'id': job_id,
                'title': title,
                'location': location,
                'url': source_url,
                'description': description,
                'posted_date': posted_date
            }
            
            job = self.normalize_job_data(
                normalized_raw, 
                company['name'], 
                'workable', 
                company.get('location')
            )
            
            # Add Workable-specific fields
            job.update({
                'job_type': job_data.get('type', 'Full-time'),
                'remote_type': job_data.get('workplace', 'On-site'),
                'skills': self.extract_skills(description)
            })
            
            return job
            
        except Exception as e:
            self.logger.error(f"解析 Workable 职位失败: {e}")
            return None
