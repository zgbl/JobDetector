"""
Lever ATS Scraper
Lever provides a public JSON API for job postings
"""
import aiohttp
import asyncio
import ssl
from typing import List, Dict, Optional
from datetime import datetime
import logging
import re
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

class LeverScraper(BaseScraper):
    """Lever ATS 专用采集器"""
    
    API_BASE = "https://api.lever.co/v0/postings"
    
    def __init__(self):
        super().__init__("lever")
        
    async def scrape(self, company: Dict) -> List[Dict]:
        """抓取Lever职位"""
        self.logger.info(f"开始抓取 {company['name']} 的职位 (Lever)...")
        
        board_token = await self._get_board_token(company)
        if not board_token:
            self.logger.warning(f"无法获取 {company['name']} 的 Lever board token")
            return []
            
        url = f"{self.API_BASE}/{board_token}?mode=json"
        
        # SSL context for development
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, ssl=ssl_context, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        self.logger.error(f"Lever API 请求失败: {response.status}")
                        return []
                        
                    jobs_data = await response.json()
                    if not isinstance(jobs_data, list):
                        self.logger.error(f"意外的 Lever API 响应格式: {type(jobs_data)}")
                        return []
                        
                    jobs = []
                    for job_data in jobs_data:
                        try:
                            job = await self._parse_job(job_data, company['name'], board_token)
                            if job:
                                jobs.append(job)
                        except Exception as e:
                            self.logger.error(f"解析 Lever 职位失败: {e}")
                            continue
                            
                    self.logger.info(f"从 {company['name']} 抓取到 {len(jobs)} 个职位")
                    return jobs
                    
        except Exception as e:
            self.logger.error(f"抓取 Lever 职位失败 ({company['name']}): {e}")
            return []

    async def _get_board_token(self, company: Dict) -> Optional[str]:
        """获取 Lever board token"""
        # 方法1: 从配置读取
        ats_system = company.get('ats_system', {})
        if isinstance(ats_system, dict):
            api_endpoint = ats_system.get('api_endpoint')
            if api_endpoint and 'lever.co/' in api_endpoint:
                return api_endpoint.split('lever.co/')[-1].split('/')[0].split('?')[0]
                
        # 方法2: 使用公司 domain
        domain = company.get('domain', '').replace('.com', '').replace('.', '')
        if domain:
            return domain
            
        return company['name'].lower().replace(' ', '')

    async def _parse_job(self, job_data: Dict, company_name: str, board_token: str) -> Optional[Dict]:
        """解析 Lever 职位数据"""
        try:
            job_id = f"lever_{job_data.get('id', '')}"
            title = job_data.get('text', '').strip()
            
            if not title:
                return None
                
            categories = job_data.get('categories', {})
            location = categories.get('location', '')
            commitment = categories.get('commitment', '') # e.g. "Full-time"
            
            # URL
            source_url = job_data.get('hostedUrl', '')
            if not source_url:
                source_url = f"https://jobs.lever.co/{board_token}/{job_data.get('id')}"
            
            # 描述解析
            # Lever contains description and lists (reqs, etc.)
            description_html = job_data.get('description', '')
            
            # Append lists to description
            lists_content = ""
            for item in job_data.get('lists', []):
                list_title = item.get('text', '')
                list_html = item.get('content', '')
                if list_title and list_html:
                    lists_content += f"<h3>{list_title}</h3>{list_html}"
            
            full_html = description_html + lists_content
            
            description = ""
            if full_html:
                soup = BeautifulSoup(full_html, 'html.parser')
                # Remove scripts
                for s in soup(["script", "style"]):
                    s.decompose()
                description = soup.get_text(separator='\n', strip=True)
                description = '\n'.join(line.strip() for line in description.split('\n') if line.strip())

            # 如果 BeautifulSoup 解析失败，回退到 descriptionPlain
            if not description:
                description = job_data.get('descriptionPlain', '')
            
            # 发布日期
            created_at = job_data.get('createdAt')
            posted_date = None
            if created_at:
                try:
                    # Lever timestamp is in milliseconds
                    posted_date = datetime.fromtimestamp(created_at / 1000.0)
                except:
                    posted_date = None

            # 提取技能和哈希
            skills = self.extract_skills(description)
            salary = self.extract_salary(description)
            content_hash = self.generate_content_hash(title, description, location)
            
            # 职位类型判断
            job_type = self._determine_job_type(title, commitment, description)
            remote_type = self._determine_remote_type(location, description)
            
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
                'source': 'lever',
                'source_url': source_url,
                'posted_date': posted_date,
                'scraped_at': datetime.utcnow(),
                'last_seen_at': datetime.utcnow(),
                'content_hash': content_hash,
                'is_active': True,
                'raw_data': {
                    'categories': categories,
                    'additional': job_data.get('additional', '')
                }
            }
            
        except Exception as e:
            self.logger.error(f"解析 Lever 职位失败: {e}")
            return None

    def _determine_job_type(self, title: str, commitment: str, description: str) -> str:
        """判断职位类型"""
        text = (title + ' ' + commitment + ' ' + description).lower()
        if 'intern' in text: return 'Internship'
        if 'contract' in text: return 'Contract'
        if 'part-time' in text: return 'Part-time'
        if 'full-time' in commitment.lower() or 'full time' in commitment.lower(): return 'Full-time'
        return 'Full-time' # Default

    def _determine_remote_type(self, location: str, description: str) -> str:
        """判断远程工作类型"""
        text = (location + ' ' + description).lower()
        if 'remote' in text:
            return 'Hybrid' if 'hybrid' in text else 'Remote'
        return 'On-site'
