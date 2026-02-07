import aiohttp
import asyncio
import ssl
import html
from typing import List, Dict, Optional
from datetime import datetime
import logging
import re
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)


class GreenhouseScraper(BaseScraper):
    """Greenhouse ATS 专用采集器"""
    
    API_BASE = "https://boards-api.greenhouse.io/v1/boards"
    
    def __init__(self):
        super().__init__("greenhouse")
    
    async def scrape(self, company: Dict) -> List[Dict]:
        """
        抓取Greenhouse职位
        
        Args:
            company: 公司信息，必须包含domain或greenhouse_board_token
            
        Returns:
            职位列表
        """
        self.logger.info(f"开始抓取 {company['name']} 的职位...")
        
        # 获取board token
        board_token = await self._get_board_token(company)
        if not board_token:
            self.logger.warning(f"无法获取 {company['name']} 的 Greenhouse board token")
            return []
        
        # 调用API获取职位
        jobs = await self._fetch_jobs_from_api(board_token, company['name'])
        
        self.logger.info(f"从 {company['name']} 抓取到 {len(jobs)} 个职位")
        return jobs
    
    async def _get_board_token(self, company: Dict) -> Optional[str]:
        """
        获取Greenhouse board token
        
        方法：
        1. 如果有 ats_url，从 URL 提取
        2. 如果公司配置中有board_token (api_endpoint)，直接使用
        3. 尝试从公司域名推断（company_name）
        4. 访问careers页面提取
        """
        # 方法0: 从 ats_url 提取 (最高优先级)
        ats_url = company.get('ats_url')
        if ats_url:
            # Match boards.greenhouse.io/{TOKEN} or /embed/job_board?for={TOKEN}
            match = re.search(r'greenhouse\.io/(?:embed/job_board\?for=)?([^/?&]+)', ats_url)
            if match:
                return match.group(1)

        # 方法1: 从配置读取
        ats_system = company.get('ats_system', {})
        if isinstance(ats_system, dict):
            api_endpoint = ats_system.get('api_endpoint')
            if api_endpoint and 'boards/' in api_endpoint:
                # Extract token from URL
                match = re.search(r'boards/([^/]+)', api_endpoint)
                if match:
                    return match.group(1)
        
        # 方法2: 使用公司domain作为token（通用做法）
        # 大多数Greenhouse公司使用简化的公司名作为token
        domain = company['domain'].replace('.com', '').replace('.', '')
        
        # Try common patterns
        potential_tokens = [
            domain,  # stripe.com -> stripe
            company['name'].lower().replace(' ', ''),  # "Scale AI" -> "scaleai"
            company['name'].lower().replace(' ', '-'),  # "Scale AI" -> "scale-ai"
        ]
        
        # 测试每个可能的token
        for token in potential_tokens:
            if await self._test_board_token(token):
                self.logger.info(f"找到有效的 board token: {token}")
                return token
        
        return None
    
    async def _test_board_token(self, token: str) -> bool:
        """测试board token是否有效"""
        url = f"{self.API_BASE}/{token}/jobs"
        
        # SSL context for development
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, ssl=ssl_context, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return 'jobs' in data or isinstance(data, list)
        except:
            pass
        
        return False
    
    async def _fetch_jobs_from_api(self, board_token: str, company_name: str) -> List[Dict]:
        """
        从Greenhouse API获取职位
        
        Args:
            board_token: Greenhouse board token
            company_name: 公司名称
            
        Returns:
            职位列表
        """
        url = f"{self.API_BASE}/{board_token}/jobs"
        
        # SSL context for development
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, ssl=ssl_context, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        self.logger.error(f"API请求失败: {response.status}")
                        return []
                    
                    data = await response.json()
                    
                    # Greenhouse API 可能返回 {'jobs': [...]} 或直接返回 [...]
                    jobs_data = data.get('jobs', data) if isinstance(data, dict) else data
                    
                    if not isinstance(jobs_data, list):
                        self.logger.error(f"意外的API响应格式: {type(jobs_data)}")
                        return []
                    
                    # 解析每个职位
                    # 注意：列表API不包含完整的job description，需要单独获取
                    jobs = []
                    for job_data in jobs_data:
                        try:
                            # 获取职位详情（包含完整描述）
                            job_detail = await self._fetch_job_detail(board_token, job_data.get('id'), session, ssl_context)
                            if job_detail:
                                # 合并基础信息和详细信息
                                full_job_data = {**job_data, **job_detail}
                                job = await self._parse_job(full_job_data, company_name, board_token)
                                if job:
                                    jobs.append(job)
                        except Exception as e:
                            self.logger.error(f"解析职位失败: {e}")
                            continue
                    
                    return jobs
                    
        except asyncio.TimeoutError:
            self.logger.error(f"API请求超时: {url}")
            return []
        except Exception as e:
            self.logger.error(f"抓取失败: {e}")
            return []
    
    async def _fetch_job_detail(self, board_token: str, job_id: int, session: aiohttp.ClientSession, ssl_context) -> Optional[Dict]:
        """
        获取单个职位的详细信息（包括完整描述）
        
        Args:
            board_token: Greenhouse board token
            job_id: 职位ID
            session: aiohttp session
            ssl_context: SSL context
            
        Returns:
            职位详情字典，包含content字段
        """
        url = f"{self.API_BASE}/{board_token}/jobs/{job_id}"
        
        try:
            async with session.get(url, ssl=ssl_context, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    detail = await response.json()
                    return detail
                else:
                    self.logger.warning(f"获取职位详情失败 {job_id}: HTTP {response.status}")
                    return None
        except Exception as e:
            self.logger.warning(f"获取职位详情失败 {job_id}: {e}")
            return None
    
    async def _parse_job(self, job_data: Dict, company_name: str, board_token: str) -> Optional[Dict]:
        """
        解析Greenhouse职位数据
        
        Greenhouse API返回格式:
        {
            "id": 123456,
            "title": "Senior Software Engineer",
            "absolute_url": "https://boards.greenhouse.io/company/jobs/123456",
            "location": {"name": "San Francisco, CA"},
            "departments": [{"name": "Engineering"}],
            "updated_at": "2024-01-01T00:00:00Z",
            "content": "<p>Job description HTML</p>"  // 或 "metadata": []
        }
        """
        try:
            # 基础字段
            job_id = f"greenhouse_{job_data.get('id', '')}"
            title = job_data.get('title', '').strip()
            
            if not title:
                return None
            
            # 地点
            location_data = job_data.get('location', {})
            location = location_data.get('name', '') if isinstance(location_data, dict) else str(location_data)
            
            # URL
            source_url = job_data.get('absolute_url', '')
            if not source_url:
                source_url = f"https://boards.greenhouse.io/{board_token}/jobs/{job_data.get('id')}"
            
            # 描述 - 清理HTML
            description = job_data.get('content', '') or job_data.get('description', '')
            if description:
                # 1. Unescape HTML entities (Greenhouse API returns &lt; &gt; etc.)
                description = html.unescape(description)
                
                # 2. BeautifulSoup to strip tags
                soup = BeautifulSoup(description, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Get text and clean whitespace
                description = soup.get_text(separator='\n', strip=True)
                
                # Clean up excessive newlines
                description = '\n'.join(line.strip() for line in description.split('\n') if line.strip())
            
            # 部门
            departments = job_data.get('departments', [])
            department_names = [d.get('name', '') for d in departments if isinstance(d, dict)]
            
            # 发布日期
            posted_date = job_data.get('updated_at') or job_data.get('created_at')
            if posted_date:
                try:
                    posted_date = datetime.fromisoformat(posted_date.replace('Z', '+00:00'))
                except:
                    posted_date = None
            
            # 提取技能和哈希
            skills = self.extract_skills(description)
            content_hash = self.generate_content_hash(title, description, location)
            
            # 提取薪资（如果描述中有）
            salary = self.extract_salary(description)
            
            # 职位类型判断
            job_type = self._determine_job_type(title, description)
            remote_type = self._determine_remote_type(location, description)
            
            job = {
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
                'source': 'greenhouse',
                'source_url': source_url,
                'posted_date': posted_date,
                'scraped_at': datetime.utcnow(),
                'last_seen_at': datetime.utcnow(),
                'content_hash': content_hash,
                'is_active': True,
                'raw_data': {
                    'id': job_data.get('id'),
                    'departments': department_names,
                    'board_token': board_token
                }
            }
            
            return job
            
        except Exception as e:
            self.logger.error(f"解析职位数据失败: {e}")
            return None
    
    def _determine_job_type(self, title: str, description: str) -> str:
        """判断职位类型"""
        text = (title + ' ' + description).lower()
        
        if 'intern' in text:
            return 'Internship'
        elif 'contract' in text or 'contractor' in text:
            return 'Contract'
        elif 'part-time' in text or 'part time' in text:
            return 'Part-time'
        else:
            return 'Full-time'
    
    def _determine_remote_type(self, location: str, description: str) -> str:
        """判断远程工作类型"""
        text = (location + ' ' + description).lower()
        
        if 'remote' in text:
            if 'hybrid' in text:
                return 'Hybrid'
            else:
                return 'Remote'
        else:
            return 'On-site'


# Async helper for testing
async def test_greenhouse_scraper():
    """测试Greenhouse抓取器"""
    scraper = GreenhouseScraper()
    
    # 测试公司
    test_company = {
        'name': 'Airbnb',
        'domain': 'airbnb.com',
        'ats_system': {'type': 'greenhouse'}
    }
    
    jobs = await scraper.scrape(test_company)
    
    print(f"\n找到 {len(jobs)} 个职位:")
    for job in jobs[:3]:  # Show first 3
        print(f"\n- {job['title']} @ {job['company']}")
        print(f"  地点: {job['location']}")
        print(f"  类型: {job['job_type']} / {job['remote_type']}")
        print(f"  技能: {', '.join(job['skills'][:5])}")
        print(f"  链接: {job['source_url']}")


if __name__ == '__main__':
    # Run test
    asyncio.run(test_greenhouse_scraper())
