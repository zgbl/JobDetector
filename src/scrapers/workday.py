import aiohttp
import asyncio
import ssl
import json
from typing import List, Dict, Optional
from datetime import datetime
import logging
import re

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
        board = config.get('board', tenant)  # 通常board名和tenant名相同，或者叫 "External"
        
        # 2. 尝试获取职位列表 (POST API)
        # 现代Workday网站通常使用 /wday/cxs/{tenant}/{board}/jobs 接口
        api_url = f"{base_url}/wday/cxs/{tenant}/{board}/jobs"
        
        # SSL context for development
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        payload = {
            "appliedFacets": {},
            "limit": 100,
            "offset": 0,
            "searchText": ""
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url, 
                    json=payload, 
                    ssl=ssl_context, 
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        # 尝试换一个board名字，比如 "External"
                        if board != "External":
                            api_url = f"{base_url}/wday/cxs/{tenant}/External/jobs"
                            async with session.post(api_url, json=payload, ssl=ssl_context) as resp2:
                                if resp2.status == 200:
                                    data = await resp2.json()
                                    return await self._parse_workday_response(data, company, base_url, tenant, "External")
                        
                        self.logger.error(f"Workday API 请求失败: {response.status} for {api_url}")
                        return []
                        
                    data = await response.json()
                    return await self._parse_workday_response(data, company, base_url, tenant, board)
                    
        except Exception as e:
            self.logger.error(f"抓取 Workday 职位失败 ({company['name']}): {e}")
            return []

    async def _get_workday_config(self, company: Dict) -> Optional[Dict]:
        """从公司信息推断Workday配置"""
        # 1. 如果有 api_endpoint，尝试解析
        ats_system = company.get('ats_system', {})
        if isinstance(ats_system, dict):
            endpoint = ats_system.get('api_endpoint')
            if endpoint:
                # https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
                match = re.search(r'(https://[^/]+)/([^/]+)', endpoint)
                if match:
                    base_url = match.group(1)
                    tenant_parts = match.group(2).split('.')
                    tenant = tenant_parts[0]
                    return {'base_url': base_url, 'tenant': tenant}

        # 2. 尝试使用 domain 推断
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
                
                # Prepare for normalization
                normalized_raw = {
                    'id': f"workday_{job_id_raw}",
                    'title': title,
                    'location': location,
                    'url': f"{base_url}{ext_path}",
                    'description': description,
                    'posted_date': None
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
