"""
BambooHR ATS Scraper
====================

BambooHR exposes a public, unauthenticated careers feed per company tenant:

    https://{tenant}.bamboohr.com/careers/list          → all open requisitions
    https://{tenant}.bamboohr.com/careers/{id}/detail   → one requisition + JD

Both return JSON, so no HTML scraping is needed.
"""
import asyncio
import logging
import ssl
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)


class BambooHRScraper(BaseScraper):
    """BambooHR ATS 专用采集器"""

    def __init__(self):
        super().__init__("bamboohr")

    def _ssl_context(self):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    def _get_tenant(self, company: Dict) -> Optional[str]:
        """Tenant is the subdomain: endlessaccess.bamboohr.com → endlessaccess."""
        ats_url = str(company.get("ats_url") or company.get("careers_url") or "")
        if "bamboohr.com" in ats_url:
            host = ats_url.split("//")[-1].split("/")[0]
            tenant = host.split(".")[0]
            if tenant and tenant != "www":
                return tenant
        ats_system = company.get("ats_system") or {}
        if isinstance(ats_system, dict):
            endpoint = str(ats_system.get("api_endpoint") or "")
            if "bamboohr.com" in endpoint:
                return endpoint.split("//")[-1].split("/")[0].split(".")[0]
        token = str(company.get("board_identifier") or "")
        return token or None

    async def scrape(self, company: Dict) -> List[Dict]:
        tenant = self._get_tenant(company)
        if not tenant:
            self.logger.warning(f"无法确定 {company.get('name')} 的 BambooHR tenant")
            return []

        base = f"https://{tenant}.bamboohr.com"
        ssl_context = self._ssl_context()

        try:
            async with aiohttp.ClientSession(
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            ) as session:
                async with session.get(
                    f"{base}/careers/list",
                    ssl=ssl_context,
                    timeout=aiohttp.ClientTimeout(total=25),
                ) as response:
                    if response.status != 200:
                        self.logger.error(f"BambooHR list failed for {tenant}: HTTP {response.status}")
                        return []
                    data = await response.json()

                listings = data.get("result") or []
                if not isinstance(listings, list):
                    return []

                jobs: List[Dict] = []
                for listing in listings:
                    if not isinstance(listing, dict):
                        continue
                    job = await self._fetch_detail(session, base, tenant, listing, company, ssl_context)
                    if job:
                        jobs.append(job)
                self.logger.info(f"从 {company.get('name')} 抓取到 {len(jobs)} 个职位 (BambooHR)")
                return jobs
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"抓取 BambooHR 职位失败 ({company.get('name')}): {exc}")
            return []

    async def _fetch_detail(self, session, base: str, tenant: str, listing: Dict,
                            company: Dict, ssl_context) -> Optional[Dict]:
        job_id = str(listing.get("id") or "")
        if not job_id:
            return None
        detail: Dict = {}
        try:
            async with session.get(
                f"{base}/careers/{job_id}/detail",
                ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                if response.status == 200:
                    payload = await response.json()
                    detail = ((payload or {}).get("result") or {}).get("jobOpening") or {}
                elif response.status in (404, 410):
                    # Requisition disappeared between the list and detail calls.
                    return None
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(f"BambooHR detail failed for {job_id}: {exc}")

        merged = {**listing, **detail}
        if str(merged.get("jobOpeningStatus") or "Open").lower() not in ("open", "1", "true"):
            return None

        title = str(merged.get("jobOpeningName") or "").strip()
        if not title:
            return None

        description = self._clean_html(merged.get("description") or "")
        location = self._format_location(merged.get("location"))
        source_url = str(
            merged.get("jobOpeningShareUrl") or f"{base}/careers/{job_id}"
        )
        posted_date = None
        raw_date = merged.get("datePosted")
        if raw_date:
            try:
                posted_date = datetime.fromisoformat(str(raw_date))
            except ValueError:
                posted_date = None

        normalized_raw = {
            "id": f"bamboohr_{tenant}_{job_id}",
            "title": title,
            "location": location,
            "url": source_url,
            "description": description,
            "posted_date": posted_date,
        }
        job = self.normalize_job_data(
            normalized_raw, company["name"], "bamboohr", company.get("location")
        )
        job.update({
            "job_type": self._determine_job_type(merged),
            "remote_type": "Remote" if merged.get("isRemote") else "On-site",
            "skills": self.extract_skills(description),
            "salary": self.extract_salary(description),
            "raw_data": {
                "department": merged.get("departmentLabel"),
                "employment_status": merged.get("employmentStatusLabel"),
                "tenant": tenant,
            },
        })
        return job

    @staticmethod
    def _format_location(location) -> str:
        if isinstance(location, dict):
            parts = [location.get("city"), location.get("state"), location.get("country")]
            return ", ".join(str(p) for p in parts if p)
        return str(location or "")

    @staticmethod
    def _determine_job_type(merged: Dict) -> str:
        text = " ".join([
            str(merged.get("employmentStatusLabel") or ""),
            str(merged.get("employmentType") or ""),
        ]).lower()
        if "intern" in text:
            return "Internship"
        if "contract" in text:
            return "Contract"
        if "part" in text:
            return "Part-time"
        return "Full-time"

    @staticmethod
    def _clean_html(html_text: str) -> str:
        if not html_text:
            return ""
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return "\n".join(line.strip() for line in text.split("\n") if line.strip())


async def main():  # pragma: no cover - manual smoke test
    scraper = BambooHRScraper()
    jobs = await scraper.scrape({
        "name": "Endless Access",
        "ats_url": "https://endlessaccess.bamboohr.com/careers",
    })
    print(f"Found {len(jobs)} jobs")
    for job in jobs[:3]:
        print(f"- {job['title']} | {job['location']} | {job['source_url']}")


if __name__ == "__main__":
    asyncio.run(main())
