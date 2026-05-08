# This file is used to process the manual list of companies to be added to the database.
# /data/manualAddList.csv
# It is a one-time script that is not meant to be run regularly.

#!/usr/bin/env python3
"""
Manual Company List Processor
处理 data/manualAddList.csv，将手动添加的公司注册到数据库并执行一次性爬取。

工作流程:
1. 读取 manualAddList.csv 中未处理的条目
2. 检查公司是否已在数据库中（去重）
3. 尝试通过 careers URL 自动识别 ATS 系统并注册公司
4. 执行一次性爬取
5. 成功 → 转移到 ManualList_finished.csv
   失败 → 在原行末尾标记 [FAILED: reason]，跳过重复处理
"""
import sys
import os
import re
import csv
import asyncio
import logging
from pathlib import Path
from datetime import datetime, UTC
from urllib.parse import urlparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, close_db
from src.scrapers.greenhouse import GreenhouseScraper
from src.scrapers.lever import LeverScraper
from src.scrapers.workday import WorkdayScraper
from src.scrapers.ashby import AshbyScraper
from src.scrapers.workable import WorkableScraper
from src.scrapers.wellfound import WellfoundScraper
from scripts.prod_scraper import scrape_company

# ── File paths ─────────────────────────────────────────────────────────────────
MANUAL_ADD_LIST  = project_root / "data" / "manualAddList.csv"
FINISHED_LIST    = project_root / "data" / "ManualList_finished.csv"
FAILED_MARKER    = "[FAILED:"   # prefix for failed entries in manualAddList.csv
ALREADY_MARKER   = "[ALREADY_IN_DB]"  # marker for companies already in DB

# Configure logging
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/manual_list_processor.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("ManualListProcessor")


# ── ATS detection ──────────────────────────────────────────────────────────────

def detect_ats_from_url(url: str) -> str | None:
    """
    从 careers URL 中直接识别 ATS 系统。
    Return one of: greenhouse, lever, workday, ashby, workable, wellfound, or None
    """
    if not url:
        return None
    u = url.lower()
    if "greenhouse.io" in u or "boards.greenhouse.io" in u:
        return "greenhouse"
    if "lever.co" in u:
        return "lever"
    if "workday.com" in u or "myworkdayjobs.com" in u:
        return "workday"
    if "ashbyhq.com" in u or "jobs.ashbyhq.com" in u:
        return "ashby"
    if "workable.com" in u or "apply.workable.com" in u:
        return "workable"
    if "wellfound.com" in u or "angel.co" in u:
        return "wellfound"
    return None


async def probe_ats(company_name: str, domain: str, careers_url: str, scrapers: dict) -> tuple[str | None, str | None]:
    """
    先试着从 URL 检测；如果检测不到，逐个探测已知 ATS 系统。
    Returns (ats_type, effective_ats_url)
    """
    # 1. URL-based detection (instant, no network)
    ats_type = detect_ats_from_url(careers_url)
    if ats_type:
        logger.info(f"  🔍 URL直接识别 ATS: {ats_type}")
        return ats_type, careers_url

    # 2. Probe Greenhouse (looks up board token via API)
    company_stub = {"name": company_name, "domain": domain}
    try:
        gh_scraper = scrapers.get("greenhouse")
        if gh_scraper:
            token = await gh_scraper._get_board_token(company_stub)
            if token:
                ats_url = f"https://boards.greenhouse.io/{token}"
                logger.info(f"  🔍 探测到 Greenhouse: {ats_url}")
                return "greenhouse", ats_url
    except Exception as e:
        logger.debug(f"  Greenhouse探测失败: {e}")

    # 3. Probe Ashby (slug == domain-root or company name slug)
    try:
        ashby_scraper = scrapers.get("ashby")
        if ashby_scraper:
            slug = domain.split(".")[0]
            test_company = {"name": company_name, "domain": domain,
                            "ats_url": f"https://jobs.ashbyhq.com/{slug}"}
            jobs = await ashby_scraper.scrape(test_company)
            if jobs:
                ats_url = f"https://jobs.ashbyhq.com/{slug}"
                logger.info(f"  🔍 探测到 Ashby: {ats_url}")
                return "ashby", ats_url
    except Exception as e:
        logger.debug(f"  Ashby探测失败: {e}")

    logger.warning(f"  ⚠️ 无法自动识别 ATS，将使用 careers URL（custom 类型）")
    return "custom", careers_url


# ── Domain extraction ──────────────────────────────────────────────────────────

def extract_domain(url: str) -> str:
    """从 URL 提取主域名，例如 https://jobs.ashbyhq.com/Distyl → distyl.com (best effort)"""
    try:
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path
        # Strip known ATS subdomains
        for prefix in ["jobs.ashbyhq.com/", "boards.greenhouse.io/", "jobs.lever.co/",
                        "apply.workable.com/", "wellfound.com/company/"]:
            if prefix in url.lower():
                slug = url.lower().split(prefix)[-1].split("/")[0].split("?")[0]
                return f"{slug}.com"
        # Otherwise fall back to hostname without www
        host = host.replace("www.", "")
        return host
    except Exception:
        return url


# ── CSV helpers ────────────────────────────────────────────────────────────────

def read_manual_list() -> list[dict]:
    """
    读取 manualAddList.csv，跳过表头、空行、已标记失败/已存在的行。
    Returns list of dicts with keys: company, url, raw_line
    """
    if not MANUAL_ADD_LIST.exists():
        logger.error(f"找不到文件: {MANUAL_ADD_LIST}")
        return []

    entries = []
    with open(MANUAL_ADD_LIST, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i == 0:
                continue  # skip header
            if not row or not any(cell.strip() for cell in row):
                continue  # skip blank lines
            # Skip already-processed rows (they carry a trailing marker)
            raw = ",".join(row)
            if FAILED_MARKER in raw or ALREADY_MARKER in raw:
                logger.debug(f"  跳过已处理行: {raw[:80]}")
                continue
            company = row[0].strip() if len(row) > 0 else ""
            url     = row[1].strip() if len(row) > 1 else ""
            if not company:
                continue
            entries.append({"company": company, "url": url, "raw_line": raw})

    return entries


def append_to_finished(company: str, url: str, added_at: str):
    """向 ManualList_finished.csv 追加一条成功记录"""
    write_header = not FINISHED_LIST.exists() or FINISHED_LIST.stat().st_size == 0
    with open(FINISHED_LIST, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["Company", "URL", "Added_At"])
        writer.writerow([company, url, added_at])


def mark_line_in_source(company: str, url: str, marker: str):
    """
    在 manualAddList.csv 中找到对应行，追加标记字符串。
    marker 示例: "[FAILED: no jobs found]" 或 "[ALREADY_IN_DB]"
    """
    lines = MANUAL_ADD_LIST.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = []
    marked = False
    for line in lines:
        stripped = line.rstrip("\n\r")
        # Match by company name prefix (case-insensitive) and unmarked
        if (not marked
                and company.lower() in stripped.lower()
                and FAILED_MARKER not in stripped
                and ALREADY_MARKER not in stripped):
            stripped = f"{stripped},{marker}"
            marked = True
        new_lines.append(stripped + "\n")
    MANUAL_ADD_LIST.write_text("".join(new_lines), encoding="utf-8")


def remove_line_from_source(company: str, url: str):
    """从 manualAddList.csv 中移除成功处理的行（爬取成功后）"""
    lines = MANUAL_ADD_LIST.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = []
    removed = False
    for line in lines:
        # Keep header and lines that don't match the company
        if (not removed
                and company.lower() in line.lower()
                and FAILED_MARKER not in line
                and ALREADY_MARKER not in line):
            removed = True   # skip this line (move to finished)
            continue
        new_lines.append(line)
    MANUAL_ADD_LIST.write_text("".join(new_lines), encoding="utf-8")


# ── Core processor ─────────────────────────────────────────────────────────────

async def process_entry(entry: dict, db, scrapers: dict) -> str:
    """
    处理单个 CSV 条目。
    Returns: "already_in_db" | "success" | "failed:<reason>"
    """
    company_name = entry["company"]
    careers_url  = entry["url"]

    logger.info(f"\n{'─'*60}")
    logger.info(f"🏢 处理公司: {company_name}  |  URL: {careers_url}")

    # ── Step 1: 查重 ─────────────────────────────────────────────────────────
    existing = db.companies.find_one({
        "$or": [
            {"name": {"$regex": f"^{re.escape(company_name)}$", "$options": "i"}},
            {"careers_url": careers_url},
            {"ats_url": careers_url},
        ]
    })
    if existing:
        logger.info(f"  ⏭️  已在数据库中: {company_name}，跳过。")
        return "already_in_db"

    # ── Step 2: ATS 识别 ──────────────────────────────────────────────────────
    domain = extract_domain(careers_url)
    ats_type, ats_url = await probe_ats(company_name, domain, careers_url, scrapers)

    # ── Step 3: 注册公司到数据库 ──────────────────────────────────────────────
    company_doc = {
        "name": company_name,
        "domain": domain.lower(),
        "careers_url": careers_url,
        "ats_url": ats_url,
        "is_active": True,
        "ats_system": {
            "type": ats_type,
            "detected_at": datetime.now(UTC),
            "api_endpoint": None,
            "confidence": 1.0 if ats_type != "custom" else 0.3,
        },
        "schedule": {
            "frequency_hours": 12,
            "last_scraped_at": None,
            "next_scrape_at": None,
            "priority": 2,
        },
        "stats": {
            "total_jobs_found": 0,
            "active_jobs": 0,
            "avg_new_jobs_per_week": 0.0,
            "scrape_success_rate": 1.0,
            "last_error": None,
        },
        "metadata": {
            "industry": None,
            "size": "Unknown",
            "headquarters": "US",
            "tags": ["manual_add"],
            "added_by": "process_manual_list",
            "added_at": datetime.now(UTC),
            "verified": False,
        },
    }
    result = db.companies.insert_one(company_doc)
    inserted_id = result.inserted_id
    company_doc["_id"] = inserted_id
    logger.info(f"  ✅ 公司已注册 (id={inserted_id}, ats={ats_type})")

    # ── Step 4: 一次性爬取 ────────────────────────────────────────────────────
    if ats_type == "custom":
        # Can't scrape custom — rollback and fail
        db.companies.delete_one({"_id": inserted_id})
        reason = "ATS未识别（custom），无法自动爬取"
        logger.warning(f"  ❌ {reason}")
        return f"failed:{reason}"

    logger.info(f"  🚀 开始一次性爬取 ({ats_type})...")
    semaphore = asyncio.Semaphore(1)
    jobs_count = await scrape_company(company_doc, scrapers, db, semaphore)

    if jobs_count > 0:
        logger.info(f"  🎉 爬取成功，获取 {jobs_count} 个职位")
        return "success"
    else:
        # jobs_count == 0 could mean empty board (valid) or failed fetch
        # We treat it as success if no exception was raised; the company is registered for future runs.
        logger.info(f"  ℹ️  爬取完成，当前无新职位（公司已注册，将纳入日常爬取）")
        return "success"


async def main():
    logger.info("=" * 60)
    logger.info("🚀 Manual List Processor 启动")
    logger.info("=" * 60)

    db = get_db()

    # Initialize all scrapers
    scrapers = {
        "greenhouse": GreenhouseScraper(),
        "lever":      LeverScraper(),
        "workday":    WorkdayScraper(),
        "ashby":      AshbyScraper(),
        "workable":   WorkableScraper(),
        "wellfound":  WellfoundScraper(),
    }

    entries = read_manual_list()
    if not entries:
        logger.info("📋 没有需要处理的条目（所有行已处理或文件为空）")
        close_db()
        return

    logger.info(f"📋 共发现 {len(entries)} 条待处理条目")

    stats = {"success": 0, "already": 0, "failed": 0}

    for entry in entries:
        company = entry["company"]
        url     = entry["url"]
        try:
            result = await process_entry(entry, db, scrapers)
        except Exception as e:
            logger.error(f"  💥 处理 {company} 时异常: {e}", exc_info=True)
            result = f"failed:异常 - {e}"

        added_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        if result == "success":
            stats["success"] += 1
            # Move to finished list
            append_to_finished(company, url, added_at)
            remove_line_from_source(company, url)
            logger.info(f"  📦 已移入 ManualList_finished.csv")

        elif result == "already_in_db":
            stats["already"] += 1
            mark_line_in_source(company, url, ALREADY_MARKER)
            logger.info(f"  🏷️  已标记为 {ALREADY_MARKER}")

        else:  # failed:...
            stats["failed"] += 1
            reason = result.split(":", 1)[-1] if ":" in result else result
            marker = f"{FAILED_MARKER} {reason}]"
            mark_line_in_source(company, url, marker)
            logger.info(f"  🏷️  已标记失败原因: {marker}")

    logger.info("\n" + "=" * 60)
    logger.info("📊 处理汇总")
    logger.info("=" * 60)
    logger.info(f"  ✅ 成功注册并爬取: {stats['success']}")
    logger.info(f"  ⏭️  已在数据库:     {stats['already']}")
    logger.info(f"  ❌ 失败:           {stats['failed']}")
    logger.info("=" * 60)

    close_db()


if __name__ == "__main__":
    asyncio.run(main())
