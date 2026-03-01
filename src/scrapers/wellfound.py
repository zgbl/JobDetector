"""
Wellfound (formerly AngelList) Scraper
Uses Playwright to scrape job listings from Wellfound.
"""
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime
import random

from playwright.async_api import async_playwright
from .base import BaseScraper

logger = logging.getLogger(__name__)

class WellfoundScraper(BaseScraper):
    """Wellfound 职位采集器"""
    
    BASE_URL = "https://wellfound.com/jobs"
    
    def __init__(self):
        super().__init__("wellfound")
        
    async def scrape(self, company: Dict) -> List[Dict]:
        """
        抓取 Wellfound 上的职位
        注意：Wellfound 是一个聚合平台，因此 company['ats_url'] 通常是 wellfound.com/jobs 或特定的过滤链接
        """
        self.logger.info(f"开始抓取 {company['name']} 相关职位 (Wellfound)...")
        
        target_url = company.get('ats_url') or self.BASE_URL
        
        jobs = []
        async with async_playwright() as p:
            # 启动浏览器，使用随机 User-Agent 和一些反爬措施
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            
            page = await context.new_page()
            
            try:
                self.logger.info(f"正在访问 {target_url}...")
                await page.goto(target_url, wait_until="networkidle", timeout=60000)
                
                # 等待职位列表加载
                # Wellfound 的类名经常变化，我们寻找通用的属性或结构
                # 通常职位卡片包含 "role" 或特定的 data-test-id
                await page.wait_for_selector('div[data-test="JobResult"]', timeout=30000)
                
                # 模拟滚动以加载更多内容
                for _ in range(3):
                    await page.mouse.wheel(0, 1000)
                    await asyncio.sleep(random.uniform(1, 2))
                
                # 获取所有职位卡片
                job_elements = await page.query_selector_all('div[data-test="JobResult"]')
                self.logger.info(f"在页面上找到 {len(job_elements)} 个职位卡片")
                
                for element in job_elements:
                    try:
                        # 提取职位信息
                        # 注意：Wellfound 页面结构较复杂，需要细致提取
                        title_elem = await element.query_selector('h2') or await element.query_selector('.styles_title__')
                        title = await title_elem.inner_text() if title_elem else "Unknown Title"
                        
                        # 公司名称 - 在 Wellfound 上，通常职位卡片上方有公司名
                        # 如果我们是针对特定公司抓取，可以从 company['name'] 获取，
                        # 但如果是从 /jobs 抓取，则需要从 element 中提取
                        company_elem = await element.query_selector('.styles_companyName__')
                        job_company_name = await company_elem.inner_text() if company_elem else company['name']
                        
                        location_elem = await element.query_selector('.styles_location__')
                        location = await location_elem.inner_text() if location_elem else ""
                        
                        # 链接
                        link_elem = await element.query_selector('a[data-test="JobTitleLink"]')
                        job_url = await link_elem.get_attribute('href') if link_elem else ""
                        if job_url and not job_url.startswith('http'):
                            job_url = f"https://wellfound.com{job_url}"
                            
                        # 简单的描述（预览）
                        desc_elem = await element.query_selector('.styles_description__')
                        description = await desc_elem.inner_text() if desc_elem else ""
                        
                        # 标准化数据
                        raw_job = {
                            'id': f"wellfound_{hash(job_url)}",
                            'title': title,
                            'location': location,
                            'url': job_url,
                            'description': description,
                            'posted_date': datetime.utcnow() # Wellfound 通常显示 "active 2 days ago"
                        }
                        
                        job = self.normalize_job_data(
                            raw_job,
                            job_company_name,
                            'wellfound',
                            company.get('location')
                        )
                        
                        # 尝试提取薪资
                        salary = self.extract_salary(description)
                        if salary:
                            job['salary'] = salary
                            
                        jobs.append(job)
                        
                    except Exception as e:
                        self.logger.warning(f"解析单个 Wellfound 职位失败: {e}")
                        continue
                
            except Exception as e:
                self.logger.error(f"Wellfound 抓取过程出错: {e}")
                # 截图以供调试
                await page.screenshot(path="logs/wellfound_error.png")
            finally:
                await browser.close()
                
        self.logger.info(f"从 Wellfound 抓取到 {len(jobs)} 个职位")
        return jobs

# 用于独立测试
async def test_wellfound():
    logging.basicConfig(level=logging.INFO)
    scraper = WellfoundScraper()
    test_company = {
        'name': 'Wellfound',
        'domain': 'wellfound.com',
        'ats_url': 'https://wellfound.com/jobs'
    }
    jobs = await scraper.scrape(test_company)
    print(f"Final Count: {len(jobs)}")
    for j in jobs[:2]:
        print(f"- {j['title']} @ {j['company']} ({j['location']})")

if __name__ == "__main__":
    asyncio.run(test_wellfound())
