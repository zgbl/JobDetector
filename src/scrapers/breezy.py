import json
import re
import ssl
from datetime import datetime
from typing import Dict, List
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from .base import BaseScraper


class BreezyScraper(BaseScraper):
    """Breezy HR job board scraper."""

    def __init__(self):
        super().__init__("breezy")

    async def scrape(self, company: Dict) -> List[Dict]:
        self.logger.info(f"Starting Breezy scrape for {company['name']}...")
        board_url = self._get_board_url(company)
        if not board_url:
            self.logger.warning(f"Could not determine Breezy URL for {company['name']}")
            return []

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession() as session:
            jobs = await self._scrape_json_endpoint(session, board_url, company, ssl_context)
            if jobs:
                self.logger.info(f"Scraped {len(jobs)} jobs from {company['name']} (Breezy JSON)")
                return jobs

            jobs = await self._scrape_html(session, board_url, company, ssl_context)
            self.logger.info(f"Scraped {len(jobs)} jobs from {company['name']} (Breezy HTML)")
            return jobs

    def _get_board_url(self, company: Dict) -> str:
        ats_url = company.get("ats_url") or company.get("careers_url") or ""
        if "breezy.hr" in ats_url:
            parsed = urlparse(ats_url if ats_url.startswith("http") else f"https://{ats_url}")
            return f"{parsed.scheme}://{parsed.netloc}/"

        name_slug = re.sub(r"[^a-z0-9]+", "", company.get("name", "").lower())
        if name_slug:
            return f"https://{name_slug}.breezy.hr/"
        return ""

    async def _scrape_json_endpoint(self, session, board_url: str, company: Dict, ssl_context) -> List[Dict]:
        json_url = urljoin(board_url, "json")
        try:
            async with session.get(json_url, ssl=ssl_context, timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status != 200:
                    return []
                data = await response.json(content_type=None)
        except Exception as exc:
            self.logger.debug(f"Breezy JSON endpoint failed for {board_url}: {exc}")
            return []

        if isinstance(data, dict):
            raw_jobs = data.get("positions") or data.get("jobs") or data.get("data") or []
        elif isinstance(data, list):
            raw_jobs = data
        else:
            raw_jobs = []

        return [self._parse_job(raw_job, company, board_url) for raw_job in raw_jobs if isinstance(raw_job, dict)]

    async def _scrape_html(self, session, board_url: str, company: Dict, ssl_context) -> List[Dict]:
        try:
            async with session.get(board_url, ssl=ssl_context, timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status != 200:
                    return []
                html = await response.text()
        except Exception as exc:
            self.logger.warning(f"Failed to fetch Breezy board {board_url}: {exc}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        jobs = []
        seen_urls = set()
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            full_url = urljoin(board_url, href)
            if "breezy.hr" not in full_url or full_url in seen_urls:
                continue
            if not re.search(r"/p/[a-f0-9]+|/jobs/[a-z0-9-]+", urlparse(full_url).path, re.I):
                continue

            title = anchor.get_text(" ", strip=True)
            if not title:
                continue
            seen_urls.add(full_url)
            jobs.append(self._parse_job({
                "id": urlparse(full_url).path.strip("/"),
                "name": title,
                "url": full_url,
                "location": "",
                "description": "",
            }, company, board_url))
        return jobs

    def _parse_job(self, raw_job: Dict, company: Dict, board_url: str) -> Dict:
        job_id_raw = (
            raw_job.get("_id")
            or raw_job.get("id")
            or raw_job.get("friendly_id")
            or raw_job.get("slug")
            or raw_job.get("url")
            or raw_job.get("name")
            or raw_job.get("title")
            or ""
        )
        title = (raw_job.get("name") or raw_job.get("title") or raw_job.get("position") or "").strip()
        location_value = raw_job.get("location") or raw_job.get("location_name") or raw_job.get("address") or ""
        if isinstance(location_value, dict):
            parts = [
                location_value.get("city"),
                location_value.get("state"),
                location_value.get("region"),
                location_value.get("country"),
            ]
            location = ", ".join([part for part in parts if part])
        else:
            location = str(location_value or "")

        source_url = raw_job.get("url") or raw_job.get("absolute_url") or raw_job.get("apply_url") or ""
        if source_url and not source_url.startswith("http"):
            source_url = urljoin(board_url, source_url)
        if not source_url and job_id_raw:
            source_url = urljoin(board_url, str(job_id_raw).lstrip("/"))

        description = (
            raw_job.get("description")
            or raw_job.get("description_html")
            or raw_job.get("body")
            or raw_job.get("details")
            or ""
        )
        if description:
            description = BeautifulSoup(str(description), "html.parser").get_text(separator="\n", strip=True)

        posted_date = datetime.utcnow()
        for key in ("created_at", "published_at", "posted_at", "updated_at"):
            if raw_job.get(key):
                try:
                    posted_date = datetime.fromisoformat(str(raw_job[key]).replace("Z", "+00:00"))
                    break
                except ValueError:
                    pass

        normalized_raw = {
            "id": f"breezy_{job_id_raw}",
            "title": title,
            "location": location,
            "url": source_url,
            "description": description,
            "posted_date": posted_date,
        }
        job = self.normalize_job_data(normalized_raw, company["name"], "breezy", company.get("location"))
        job.update({
            "job_type": raw_job.get("type") or raw_job.get("employment_type") or "Full-time",
            "remote_type": "Remote" if "remote" in location.lower() else "On-site",
            "skills": self.extract_skills(description),
            "raw_data": raw_job,
        })
        return job
