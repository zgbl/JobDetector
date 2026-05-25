import aiohttp
import asyncio
import json
import ssl
from typing import List, Dict, Optional
from datetime import datetime
import logging
import re
from urllib.parse import urlparse

from .base import BaseScraper

logger = logging.getLogger(__name__)

class WorkdayScraper(BaseScraper):
    """Workday ATS 专用采集器"""
    
    def __init__(self):
        super().__init__("workday")
        
    async def scrape(self, company: Dict) -> List[Dict]:
        """抓取Workday职位"""
        self.logger.info(f"开始抓取 {company['name']} 的职位 (Workday)...")
        
        # 1. 获取Workday基础URL和Tenant信息
        config = await self._get_workday_config(company)
        if not config:
            self.logger.warning(f"无法获取 {company['name']} 的 Workday 配置")
            return []
            
        base_url = config['base_url']
        tenant = config['tenant']
        board = config.get('board', tenant)
        
        # 2. 尝试获取职位列表 (POST API)
        # 现代Workday网站通常使用 /wday/cxs/{tenant}/{board}/jobs 接口
        api_url = f"{base_url}/wday/cxs/{tenant}/{board}/jobs"
        
        # SSL context for development
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        try:
            async with aiohttp.ClientSession() as session:
                await self._warm_session(session, base_url, board, ssl_context)
                page_limit = 20
                data = await self._fetch_jobs_page(session, api_url, ssl_context, limit=page_limit, offset=0)
                if data is None and board != "External":
                    board = "External"
                    api_url = f"{base_url}/wday/cxs/{tenant}/{board}/jobs"
                    data = await self._fetch_jobs_page(session, api_url, ssl_context, limit=page_limit, offset=0)

                if data is None:
                    self.logger.error(f"Workday API 请求失败 for {api_url}")
                    return []

                all_postings = list(data.get('jobPostings', []))
                total = data.get('total') or len(all_postings)
                offset = len(all_postings)
                while offset < total:
                    page = await self._fetch_jobs_page(session, api_url, ssl_context, limit=page_limit, offset=offset)
                    if not page:
                        break
                    postings = page.get('jobPostings', [])
                    if not postings:
                        break
                    all_postings.extend(postings)
                    offset += len(postings)

                data['jobPostings'] = all_postings
                self.logger.info(f"从 {company['name']} Workday 抓取到 {len(all_postings)} 个职位")
                return await self._parse_workday_response(data, company, base_url, tenant, board)
                    
        except Exception as e:
            self.logger.error(f"抓取 Workday 职位失败 ({company['name']}): {e}")
            return []

    async def _warm_session(self, session, base_url: str, board: str, ssl_context) -> None:
        board_url = f"{base_url}/{board}"
        try:
            async with session.get(
                board_url,
                ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=20),
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            ):
                return
        except Exception as exc:
            self.logger.debug(f"Workday warm session failed for {board_url}: {exc}")

    async def _fetch_jobs_page(self, session, api_url: str, ssl_context, limit: int, offset: int) -> Optional[Dict]:
        payload = {
            "appliedFacets": {},
            "limit": limit,
            "offset": offset,
            "searchText": ""
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": api_url.split("/wday/")[0],
            "Referer": api_url.split("/wday/")[0] + "/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        }
        async with session.post(
            api_url,
            data=json.dumps(payload, separators=(",", ":")),
            headers=headers,
            ssl=ssl_context,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status != 200:
                body = await response.text()
                curl_data = await self._fetch_jobs_page_with_curl(api_url, payload)
                if curl_data is not None:
                    return curl_data
                self.logger.warning(f"Workday page request failed: {response.status} for {api_url}: {body[:200]}")
                return None
            return await response.json()

    async def _fetch_jobs_page_with_curl(self, api_url: str, payload: Dict) -> Optional[Dict]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "curl",
                "-fsS",
                "-X",
                "POST",
                api_url,
                "-H",
                "Content-Type: application/json",
                "--data",
                json.dumps(payload, separators=(",", ":")),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=35)
        except Exception as exc:
            self.logger.warning(f"Workday curl fallback failed for {api_url}: {exc}")
            return None

        if proc.returncode != 0:
            self.logger.warning(f"Workday curl fallback returned {proc.returncode}: {stderr[:200]!r}")
            return None
        try:
            return json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self.logger.warning(f"Workday curl fallback JSON parse failed: {exc}")
            return None

    async def _get_workday_config(self, company: Dict) -> Optional[Dict]:
        """从公司信息推断Workday配置"""
        # 1. Prefer explicit ATS URL discovered from the company careers page.
        for url in [company.get('ats_url'), company.get('careers_url')]:
            config = self._parse_workday_url(url or "")
            if config:
                return config

        # 2. 如果有 api_endpoint，尝试解析
        ats_system = company.get('ats_system', {})
        if isinstance(ats_system, dict):
            endpoint = ats_system.get('api_endpoint')
            config = self._parse_workday_url(endpoint or "")
            if config:
                return config

        # 3. 尝试使用 domain 推断
        # 很多公司使用 {company}.myworkdayjobs.com
        domain = company.get('domain', '').split('.')[0]
        potential_hosts = [
            f"https://{domain}.myworkdayjobs.com",
            f"https://{domain.lower()}.wd1.myworkdayjobs.com",
            f"https://{domain.lower()}.wd5.myworkdayjobs.com",
        ]
        
        # Test hosts
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with aiohttp.ClientSession() as session:
            for host in potential_hosts:
                try:
                    # 获取主页看是否重定向到真正的tenant路径
                    async with session.get(host, ssl=ssl_context, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            # 提取 tenant 信息
                            url_path = resp.url.path
                            # Usually /wday/cxs/{tenant}/...
                            # Or we can just use the subdomain as tenant
                            tenant = host.split('//')[1].split('.')[0]
                            return {'base_url': host, 'tenant': tenant}
                except:
                    continue
                    
        return None

    def _parse_workday_url(self, url: str) -> Optional[Dict]:
        if not url or 'workday' not in url:
            return None
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"

        parsed = urlparse(url)
        if not parsed.netloc:
            return None

        base_url = f"{parsed.scheme}://{parsed.netloc}"
        host_parts = parsed.netloc.split('.')
        tenant = host_parts[0]
        path_parts = [part for part in parsed.path.split('/') if part]

        # API URLs look like /wday/cxs/{tenant}/{site}/jobs.
        if len(path_parts) >= 4 and path_parts[0] == 'wday' and path_parts[1] == 'cxs':
            tenant = path_parts[2]
            board = path_parts[3]
            return {'base_url': base_url, 'tenant': tenant, 'board': board}

        # Public board URLs look like /{siteId}; host first label is usually tenant.
        board = path_parts[0] if path_parts else tenant
        return {'base_url': base_url, 'tenant': tenant, 'board': board}

    async def _parse_workday_response(self, data: Dict, company: Dict, base_url: str, tenant: str, board: str) -> List[Dict]:
        """解析 Workday API 响应"""
        job_postings = data.get('jobPostings', [])
        jobs = []
        
        for job_data in job_postings:
            try:
                ext_path = job_data.get('externalPath', '')
                job_id_raw = ext_path.split('_')[-1] if '_' in ext_path else ext_path.split('/')[-1]
                
                title = job_data.get('title', '').strip()
                description = job_data.get('description', '') or ''
                location = job_data.get('locationsText', '')
                posted_date = self._parse_posted_date(job_data.get('postedOn'))
                
                # Prepare for normalization
                normalized_raw = {
                    'id': f"workday_{job_id_raw}",
                    'title': title,
                    'location': location,
                    'url': f"{base_url}/{board}{ext_path}",
                    'description': description,
                    'posted_date': posted_date
                }
                
                job = self.normalize_job_data(
                    normalized_raw, 
                    company['name'], 
                    'workday', 
                    company.get('location')
                )
                
                # Add Workday-specific fields
                job.update({
                    'job_type': 'Full-time',
                    'remote_type': 'On-site',
                    'skills': [],
                    'raw_data': job_data
                })
                
                jobs.append(job)
                
            except Exception as e:
                self.logger.error(f"解析 Workday 职位失败: {e}")
                continue
                
        return jobs

    def _parse_posted_date(self, posted_on: Optional[str]):
        if not posted_on:
            return None
        text = posted_on.lower()
        now = datetime.utcnow()
        if 'today' in text or 'just posted' in text:
            return now
        match = re.search(r'(\d+)\s+days?\s+ago', text)
        if match:
            from datetime import timedelta
            return now - timedelta(days=int(match.group(1)))
        return None
