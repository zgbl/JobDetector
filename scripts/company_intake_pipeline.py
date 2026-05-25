#!/usr/bin/env python3
"""
Company Intake Pipeline

Turn rough company lists into active crawl targets.

Supported inputs:
- YAML files with `companies: [{name, domain, careers_url, ats_url, ats_type, tags, ...}]`
- CSV files with columns like company/name/company_name, domain, url/careers_url/jobs_url
- TXT files with one company per line, numbered lists, or simple category headings

The pipeline:
1. Parses input files.
2. Deduplicates against MongoDB.
3. Discovers ATS/careers URLs when needed.
4. Inserts or updates `companies`.
5. Optionally runs a one-time scrape for newly active companies.
"""
import argparse
import asyncio
import csv
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import yaml

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.ats_discovery import ATSDiscoveryService

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/company_intake_pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("CompanyIntake")

SUPPORTED_ATS = {"greenhouse", "lever", "workday", "ashby", "workable", "wellfound", "breezy"}
KNOWN_TLDS = {
    "com", "co", "io", "ai", "dev", "app", "net", "org", "cloud", "software",
    "tech", "health", "finance", "capital", "systems", "labs", "jp", "us", "uk",
}


@dataclass
class CandidateCompany:
    name: str
    domain: str = ""
    careers_url: str = ""
    ats_url: str = ""
    ats_type: str = ""
    size: str = "Unknown"
    industry: str = ""
    tags: list[str] = field(default_factory=list)
    source_file: str = ""
    source_category: str = ""


def clean_name(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^\s*[\d]+[\.\)]\s*", "", value)
    value = re.sub(r"^[•\-*]\s*", "", value)
    value = value.replace("\t", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -–—:，,")


def slugify_domain(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"\([^)]*\)", "", slug)
    slug = slug.replace("&", "and")
    slug = re.sub(r"[^a-z0-9]+", "", slug)
    if not slug:
        return ""
    return f"{slug}.com"


def normalize_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("www."):
        return f"https://{value}"
    if value.startswith(("http://", "https://")):
        return value
    if "." in value and " " not in value:
        return f"https://{value}"
    return value


def extract_domain(value: str) -> str:
    value = normalize_url(value)
    if not value:
        return ""
    if "google.com/search" in value:
        query = parse_qs(urlparse(value).query).get("q", [""])[0]
        name = re.sub(r"\bcareers?\b|\bjobs?\b", "", unquote(query), flags=re.I).strip()
        return slugify_domain(name)
    if value.startswith(("http://", "https://")):
        host = urlparse(value).netloc.lower().replace("www.", "")
        if host in {"boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com", "apply.workable.com"}:
            path_slug = urlparse(value).path.strip("/").split("/")[0]
            return f"{path_slug}.com" if path_slug else ""
        return host
    if "." in value and " " not in value:
        return value.lower().replace("www.", "")
    return ""


def identify_ats(url: str, ats_type: str = "") -> str:
    ats_type = (ats_type or "").strip().lower()
    if ats_type in SUPPORTED_ATS:
        return ats_type
    u = (url or "").lower()
    if "greenhouse.io" in u:
        return "greenhouse"
    if "lever.co" in u:
        return "lever"
    if "workday.com" in u or "myworkdayjobs.com" in u:
        return "workday"
    if "ashbyhq.com" in u:
        return "ashby"
    if "workable.com" in u:
        return "workable"
    if "wellfound.com" in u or "angel.co" in u:
        return "wellfound"
    if "breezy.hr" in u:
        return "breezy"
    return ats_type


def split_tags(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in re.split(r"[,;/|]", str(value)) if part.strip()]


def parse_yaml(path: Path) -> list[CandidateCompany]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = data.get("companies", data if isinstance(data, list) else [])
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = clean_name(row.get("name") or row.get("company") or row.get("company_name") or "")
        if not name:
            continue
        careers_url = normalize_url(row.get("careers_url") or row.get("jobs_url") or row.get("url") or "")
        domain = extract_domain(row.get("domain") or careers_url) or slugify_domain(name)
        ats_url = normalize_url(row.get("ats_url") or careers_url)
        candidates.append(CandidateCompany(
            name=name,
            domain=domain,
            careers_url=careers_url,
            ats_url=ats_url if identify_ats(ats_url, row.get("ats_type")) else "",
            ats_type=identify_ats(ats_url, row.get("ats_type")),
            size=row.get("size") or "Unknown",
            industry=row.get("industry") or "",
            tags=split_tags(row.get("tags")),
            source_file=str(path),
        ))
    return candidates


def row_get(row: dict[str, str], *names: str) -> str:
    lowered = {k.lower().strip(): v for k, v in row.items()}
    for name in names:
        if name in lowered and lowered[name]:
            return lowered[name]
    return ""


def parse_csv(path: Path) -> list[CandidateCompany]:
    candidates = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = clean_name(row_get(row, "company", "company_name", "name", "company name"))
            if not name:
                continue
            url = normalize_url(row_get(row, "careers_url", "jobs_url", "url", "ats_url", "website", "domain"))
            domain = extract_domain(row_get(row, "domain", "website") or url) or slugify_domain(name)
            ats_url = normalize_url(row_get(row, "ats_url") or url)
            industry = row_get(row, "industry", "category")
            candidates.append(CandidateCompany(
                name=name,
                domain=domain,
                careers_url=url,
                ats_url=ats_url if identify_ats(ats_url, row_get(row, "ats_type")) else "",
                ats_type=identify_ats(ats_url, row_get(row, "ats_type")),
                size=row_get(row, "size") or "Unknown",
                industry=industry,
                tags=split_tags(row_get(row, "tags") or industry),
                source_file=str(path),
            ))
    return candidates


def parse_txt(path: Path) -> list[CandidateCompany]:
    candidates = []
    category = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or set(line) <= {"-", "—", "─", "⸻"}:
            continue
        if not re.search(r"[A-Za-z0-9]", line):
            continue
        if re.match(r"^[A-Za-z].{0,80}$", line) and not re.match(r"^\s*[\d]+[\.\)]|^[•\-*]", line):
            if "/" in line or "公司" in line or "Tech" in line or "AI" in line:
                category = clean_name(line)
                continue
        if "包括" in line or "后面补足" in line:
            continue
        if "•" in line and not line.startswith("•"):
            parts = [clean_name(part) for part in line.split("•") if clean_name(part)]
        else:
            parts = [clean_name(line)]
        for part in parts:
            if not part or len(part) > 80:
                continue
            if part.startswith(("（", "(", "后面")):
                continue
            candidates.append(CandidateCompany(
                name=part,
                domain=slugify_domain(part),
                tags=[category] if category else [],
                source_category=category,
                source_file=str(path),
            ))
    return candidates


def parse_inputs(paths: list[Path]) -> list[CandidateCompany]:
    all_candidates = []
    for path in paths:
        if not path.exists():
            logger.warning("Input file not found: %s", path)
            continue
        suffix = path.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            candidates = parse_yaml(path)
        elif suffix == ".csv":
            candidates = parse_csv(path)
        else:
            candidates = parse_txt(path)
        logger.info("Parsed %s candidates from %s", len(candidates), path)
        all_candidates.extend(candidates)

    deduped = {}
    for candidate in all_candidates:
        key = candidate.domain.lower() if candidate.domain else candidate.name.lower()
        if key not in deduped:
            deduped[key] = candidate
        else:
            old = deduped[key]
            old.careers_url = old.careers_url or candidate.careers_url
            old.ats_url = old.ats_url or candidate.ats_url
            old.ats_type = old.ats_type or candidate.ats_type
            old.tags = list(dict.fromkeys(old.tags + candidate.tags))
    return list(deduped.values())


def existing_company(db, candidate: CandidateCompany) -> dict | None:
    checks = [{"name": {"$regex": f"^{re.escape(candidate.name)}$", "$options": "i"}}]
    if candidate.domain:
        checks.append({"domain": candidate.domain.lower()})
    if candidate.ats_url:
        checks.append({"ats_url": candidate.ats_url})
    if candidate.careers_url:
        checks.append({"careers_url": candidate.careers_url})
    return db.companies.find_one({"$or": checks})


async def enrich_candidate(candidate: CandidateCompany, discovery: ATSDiscoveryService, skip_discovery: bool) -> CandidateCompany:
    candidate.careers_url = normalize_url(candidate.careers_url)
    candidate.ats_url = normalize_url(candidate.ats_url)
    candidate.ats_type = identify_ats(candidate.ats_url or candidate.careers_url, candidate.ats_type)

    if candidate.ats_type in SUPPORTED_ATS and candidate.ats_url:
        return candidate

    if skip_discovery:
        return candidate

    seed = candidate.careers_url or candidate.domain or candidate.name
    ats_url, ats_type = await discovery.discover_ats(seed)
    if ats_url and ats_type:
        candidate.ats_url = ats_url
        candidate.ats_type = ats_type
        candidate.careers_url = candidate.careers_url or ats_url
        candidate.domain = candidate.domain or extract_domain(ats_url) or slugify_domain(candidate.name)
    return candidate


def build_company_doc(candidate: CandidateCompany) -> dict:
    now = datetime.now(UTC)
    tags = list(dict.fromkeys([tag for tag in candidate.tags if tag] + ["company_intake"]))
    confidence = 1.0 if candidate.ats_type in SUPPORTED_ATS and candidate.ats_url else 0.35
    return {
        "name": candidate.name,
        "domain": (candidate.domain or slugify_domain(candidate.name)).lower(),
        "careers_url": candidate.careers_url or candidate.ats_url,
        "ats_url": candidate.ats_url,
        "is_active": candidate.ats_type in SUPPORTED_ATS,
        "ats_system": {
            "type": candidate.ats_type or "custom",
            "detected_at": now,
            "api_endpoint": None,
            "confidence": confidence,
        },
        "schedule": {
            "frequency_hours": 12,
            "last_scraped_at": None,
            "next_scrape_at": None,
            "priority": 2 if candidate.ats_type in SUPPORTED_ATS else 4,
        },
        "stats": {
            "total_jobs_found": 0,
            "active_jobs": 0,
            "avg_new_jobs_per_week": 0.0,
            "scrape_success_rate": 1.0,
            "last_error": None,
        },
        "metadata": {
            "industry": candidate.industry or candidate.source_category or None,
            "size": candidate.size,
            "headquarters": None,
            "tags": tags,
            "added_by": "company_intake_pipeline",
            "added_at": now,
            "verified": candidate.ats_type in SUPPORTED_ATS,
            "source_file": candidate.source_file,
        },
        "updated_at": now,
    }


async def maybe_scrape(company_doc: dict, db, scrapers: dict) -> int:
    from scripts.prod_scraper import scrape_company

    ats_type = (company_doc.get("ats_system") or {}).get("type", "").lower()
    if ats_type not in scrapers:
        return 0
    semaphore = asyncio.Semaphore(1)
    return await scrape_company(company_doc, scrapers, db, semaphore)


async def run(args):
    input_paths = [Path(path) for path in args.inputs]
    candidates = parse_inputs(input_paths)
    if args.only:
        wanted = {name.strip().lower() for name in args.only.split(",") if name.strip()}
        candidates = [candidate for candidate in candidates if candidate.name.lower() in wanted]
    if args.offset:
        candidates = candidates[args.offset:]
    if args.limit:
        candidates = candidates[:args.limit]

    discovery = ATSDiscoveryService()
    db = None
    close_db = None
    scrapers = {}
    if not args.dry_run:
        from src.database.connection import close_db as close_db_func, get_db
        from src.scrapers.ashby import AshbyScraper
        from src.scrapers.breezy import BreezyScraper
        from src.scrapers.greenhouse import GreenhouseScraper
        from src.scrapers.lever import LeverScraper
        from src.scrapers.wellfound import WellfoundScraper
        from src.scrapers.workable import WorkableScraper
        from src.scrapers.workday import WorkdayScraper

        close_db = close_db_func
        db = get_db()
        scrapers = {
            "greenhouse": GreenhouseScraper(),
            "lever": LeverScraper(),
            "workday": WorkdayScraper(),
            "ashby": AshbyScraper(),
            "breezy": BreezyScraper(),
            "workable": WorkableScraper(),
            "wellfound": WellfoundScraper(),
        }
    stats = {"parsed": len(candidates), "inserted": 0, "updated": 0, "skipped": 0, "inactive": 0, "scraped_jobs": 0}

    logger.info("Starting intake for %s unique candidates", len(candidates))
    for index, candidate in enumerate(candidates, 1):
        logger.info("[%s/%s] %s", index, len(candidates), candidate.name)
        existing = existing_company(db, candidate) if db is not None else None
        if existing and not args.update_existing:
            logger.info("  skip existing: %s", candidate.name)
            stats["skipped"] += 1
            continue

        candidate = await enrich_candidate(candidate, discovery, args.skip_discovery)
        company_doc = build_company_doc(candidate)

        if args.dry_run:
            logger.info(
                "  dry-run: domain=%s ats=%s ats_url=%s active=%s",
                company_doc["domain"],
                company_doc["ats_system"]["type"],
                company_doc.get("ats_url") or "-",
                company_doc["is_active"],
            )
            if not company_doc["is_active"]:
                stats["inactive"] += 1
            continue

        if existing:
            db.companies.update_one({"_id": existing["_id"]}, {"$set": company_doc})
            company_doc["_id"] = existing["_id"]
            stats["updated"] += 1
            logger.info("  updated company: ats=%s active=%s", company_doc["ats_system"]["type"], company_doc["is_active"])
        else:
            result = db.companies.insert_one(company_doc)
            company_doc["_id"] = result.inserted_id
            stats["inserted"] += 1
            logger.info("  inserted company: ats=%s active=%s", company_doc["ats_system"]["type"], company_doc["is_active"])

        if not company_doc["is_active"]:
            stats["inactive"] += 1
            continue

        if args.scrape_now:
            try:
                count = await maybe_scrape(company_doc, db, scrapers)
                stats["scraped_jobs"] += count
                logger.info("  scrape-now jobs: %s", count)
            except Exception as exc:
                logger.error("  scrape-now failed for %s: %s", candidate.name, exc)

    logger.info("Intake summary: %s", stats)
    if close_db:
        close_db()


def main():
    parser = argparse.ArgumentParser(description="Import, discover, and optionally scrape company lists.")
    parser.add_argument("inputs", nargs="+", help="Input YAML/CSV/TXT files.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and discover only; do not write DB.")
    parser.add_argument("--update-existing", action="store_true", help="Update existing companies instead of skipping.")
    parser.add_argument("--scrape-now", action="store_true", help="Run one-time scrape after insert/update.")
    parser.add_argument("--skip-discovery", action="store_true", help="Do not crawl homepages to find ATS URLs.")
    parser.add_argument("--offset", type=int, default=0, help="Skip the first N parsed candidates before processing.")
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N parsed candidates.")
    parser.add_argument("--only", default="", help="Comma-separated company names to process from the input files.")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
