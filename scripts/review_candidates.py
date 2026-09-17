#!/usr/bin/env python3
"""
Review discovered company candidates.

``scripts/discover_companies.py`` stages new companies in
``company_candidates`` with ``status="pending"``. Nothing is scraped until a
human approves them here — approving writes the company into ``companies`` with
``is_active=True``, which is exactly what the existing scraper reads.

Examples
--------
    python scripts/review_candidates.py --stats
    python scripts/review_candidates.py --list --min-jobs 3 --min-relevance 3
    python scripts/review_candidates.py --approve 66f1...a3 66f1...b7
    python scripts/review_candidates.py --approve-all --min-jobs 5 --min-relevance 4
    python scripts/review_candidates.py --reject 66f1...a3
    python scripts/review_candidates.py --approve-all --min-jobs 5 --scrape-now
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from bson import ObjectId  # noqa: E402

from src.database.connection import get_db  # noqa: E402
from src.database.models import (  # noqa: E402
    ATSSystem,
    Company,
    CompanyMetadata,
    CompanyStats,
    Schedule,
)

CANDIDATES = "company_candidates"

STATUS_LABELS = {
    "pending": "待审",
    "approved": "已批准",
    "rejected": "已拒绝",
    "duplicate": "重复",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review discovered company candidates")
    parser.add_argument("--list", action="store_true", help="List candidates")
    parser.add_argument("--stats", action="store_true", help="Show counts by status/source")
    parser.add_argument("--status", default="pending",
                        help="pending | approved | rejected | duplicate | all (default pending)")
    parser.add_argument("--source", default="", help="Filter by source (hn_whoishiring / yc_directory)")
    parser.add_argument("--min-jobs", type=int, default=0, help="Only show boards with >= N open roles")
    parser.add_argument("--min-relevance", type=int, default=0, help="Only show scores >= N (0-10)")
    parser.add_argument("--limit", type=int, default=40, help="Max rows to list / act on")
    parser.add_argument("--approve", nargs="*", default=None, help="Candidate ids (or id prefixes) to approve")
    parser.add_argument("--reject", nargs="*", default=None, help="Candidate ids (or id prefixes) to reject")
    parser.add_argument("--approve-all", action="store_true",
                        help="Approve every pending candidate matching the filters")
    parser.add_argument("--scrape-now", action="store_true",
                        help="Immediately scrape the newly approved companies")
    parser.add_argument("--yes", action="store_true", help="Skip the approve-all confirmation")
    return parser.parse_args()


def build_query(args: argparse.Namespace) -> Dict[str, Any]:
    query: Dict[str, Any] = {}
    if args.status != "all":
        query["status"] = args.status
    if args.source:
        query["source"] = args.source
    if args.min_jobs:
        query["open_jobs"] = {"$gte": args.min_jobs}
    if args.min_relevance:
        query["relevance_score"] = {"$gte": args.min_relevance}
    return query


def find_by_prefix(collection, prefix: str) -> List[Dict[str, Any]]:
    """Accept a full ObjectId or any unambiguous prefix."""
    prefix = prefix.strip()
    if not prefix:
        return []
    matches: List[Dict[str, Any]] = []
    try:
        matches.append(collection.find_one({"_id": ObjectId(prefix)}))
    except Exception:  # noqa: BLE001
        pass
    if not matches[0] if matches else True:
        import re

        pattern = re.compile(f"^{re.escape(prefix)}")
        matches = list(collection.find({"_id": {"$regex": pattern}}).limit(5))
        matches = [m for m in matches if m]
    if not matches:
        # also allow matching on fingerprint
        doc = collection.find_one({"fingerprint": prefix})
        if doc:
            matches = [doc]
    return [m for m in matches if m]


def cmd_stats(db) -> int:
    collection = db[CANDIDATES]
    total = collection.count_documents({})
    print(f"候选公司总数: {total}")
    if not total:
        print("（还没有候选 —— 先跑 python scripts/discover_companies.py）")
        return 0
    print("\n按状态:")
    for status in ("pending", "approved", "rejected", "duplicate"):
        count = collection.count_documents({"status": status})
        print(f"  {STATUS_LABELS[status]:6} {count}")
    print("\n按来源:")
    for row in collection.aggregate([
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]):
        print(f"  {str(row['_id']):20} {row['count']}")
    print("\n按解析方式:")
    for row in collection.aggregate([
        {"$match": {"resolve_method": {"$ne": ""}}},
        {"$group": {"_id": "$resolve_method", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]):
        print(f"  {str(row['_id']):24} {row['count']}")
    print("\n按 ATS:")
    for row in collection.aggregate([
        {"$match": {"ats": {"$ne": ""}}},
        {"$group": {"_id": "$ats", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]):
        print(f"  {str(row['_id']):16} {row['count']}")
    return 0


def cmd_list(db, query: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    rows = list(
        db[CANDIDATES].find(query).sort(
            [("relevance_score", -1), ("open_jobs", -1)]
        ).limit(limit)
    )
    if not rows:
        print("没有匹配的候选。")
        return []
    print(f"{'id':26} {'公司':26} {'ATS':10} {'岗位':>5} {'相关':>4} {'置信':>5}  解析方式")
    print("-" * 110)
    for row in rows:
        print(
            f"{str(row['_id']):26} {str(row.get('name') or '')[:24]:26} "
            f"{str(row.get('ats') or '-'):10} {row.get('open_jobs', 0):>5} "
            f"{row.get('relevance_score', 0):>4} {row.get('confidence', 0):>5}  "
            f"{row.get('resolve_method', '')}"
        )
        if row.get("sample_titles"):
            print(f"{'':26} └ {', '.join(row['sample_titles'][:3])[:88]}")
        if row.get("warning"):
            print(f"{'':26} ⚠️  {row['warning'][:88]}")
    print(f"\n共 {len(rows)} 条（--limit 调整上限）")
    return rows


def approve(db, candidates: List[Dict[str, Any]], scrape_now: bool) -> int:
    from src.services.source_verify import identify

    approved = 0
    approved_names: List[str] = []
    for candidate in candidates:
        name = str(candidate.get("name") or "").strip()
        if not name:
            continue
        ats_url = str(candidate.get("ats_url") or "")
        ats_type = str(candidate.get("ats") or "")
        if not ats_url or not ats_type:
            print(f"  ⏭  {name}: 没有解析出 ATS，无法批准")
            continue

        existing = db.companies.find_one({"name": name})
        if existing:
            print(f"  ⏭  {name}: 已存在于 companies，跳过")
            db[CANDIDATES].update_one(
                {"_id": candidate["_id"]},
                {"$set": {"status": "duplicate", "reviewed_at": datetime.utcnow(),
                          "notes": "already in companies at approval time"}},
            )
            continue

        ref = identify(ats_url)
        company = Company(
            name=name,
            domain=str(candidate.get("domain") or ""),
            careers_url=ats_url,
            ats_url=ats_url,
            ats_system=ATSSystem(
                type=ats_type,
                api_endpoint=None,
                confidence=float(candidate.get("confidence") or 0.6),
            ),
            schedule=Schedule(frequency_hours=12, priority=3),
            stats=CompanyStats(),
            metadata=CompanyMetadata(
                industry=None,
                size=None,
                headquarters=None,
                tags=["discovered", str(candidate.get("source") or "")],
                added_by="company_discovery",
                verified=True,
            ),
            is_active=True,
        )
        doc = company.to_dict()
        doc.update({
            "board_identifier": ref.get("token") or candidate.get("board_token") or "",
            "created_at": datetime.utcnow(),
            "discovered_via": candidate.get("source", ""),
            "discovered_at": candidate.get("discovered_at", ""),
            "discovery_confidence": candidate.get("confidence", 0),
            "discovery_resolve_method": candidate.get("resolve_method", ""),
        })
        db.companies.insert_one(doc)
        db[CANDIDATES].update_one(
            {"_id": candidate["_id"]},
            {"$set": {"status": "approved", "reviewed_at": datetime.utcnow()}},
        )
        approved += 1
        approved_names.append(name)
        print(f"  ✅ {name} → {ats_type}/{candidate.get('board_token')} 已加入 companies")

    print(f"\n批准 {approved} 家")
    if approved and not scrape_now:
        print("下一步：它们会在下一个抓取周期（每 6 小时）被自动抓取，")
        print("       也可以立刻跑：python scripts/prod_scraper.py")
    if approved and scrape_now:
        asyncio.run(scrape_companies(approved_names))
    return approved


async def scrape_companies(names: List[str]) -> None:
    """Immediately scrape the freshly approved companies with the existing scraper."""
    from scripts.prod_scraper import scrape_company
    from src.scrapers.ashby import AshbyScraper
    from src.scrapers.bamboohr import BambooHRScraper
    from src.scrapers.breezy import BreezyScraper
    from src.scrapers.greenhouse import GreenhouseScraper
    from src.scrapers.lever import LeverScraper
    from src.scrapers.workable import WorkableScraper
    from src.scrapers.workday import WorkdayScraper
    from src.scrapers.wellfound import WellfoundScraper

    scrapers = {
        "greenhouse": GreenhouseScraper(),
        "lever": LeverScraper(),
        "workday": WorkdayScraper(),
        "ashby": AshbyScraper(),
        "breezy": BreezyScraper(),
        "bamboohr": BambooHRScraper(),
        "workable": WorkableScraper(),
        "wellfound": WellfoundScraper(),
    }
    db = get_db()
    semaphore = asyncio.Semaphore(3)
    total = 0
    for name in names:
        company = db.companies.find_one({"name": name})
        if not company:
            continue
        count = await scrape_company(company, scrapers, db, semaphore)
        total += count or 0
        print(f"  {name}: +{count} 职位")
    print(f"\n抓取完成，共新增/更新 {total} 个职位")


def reject(db, candidates: List[Dict[str, Any]]) -> int:
    count = 0
    for candidate in candidates:
        db[CANDIDATES].update_one(
            {"_id": candidate["_id"]},
            {"$set": {"status": "rejected", "reviewed_at": datetime.utcnow()}},
        )
        print(f"  🚫 {candidate.get('name')}")
        count += 1
    print(f"\n拒绝 {count} 家")
    return count


def main() -> int:
    args = parse_args()
    db = get_db()
    collection = db[CANDIDATES]

    if args.stats:
        return cmd_stats(db)

    if args.approve is not None:
        targets: List[Dict[str, Any]] = []
        for prefix in args.approve:
            found = find_by_prefix(collection, prefix)
            if not found:
                print(f"  ⚠️  找不到候选: {prefix}")
            targets.extend(found)
        return 0 if not targets else (0 if approve(db, targets, args.scrape_now) >= 0 else 1)

    if args.reject is not None:
        targets = []
        for prefix in args.reject:
            targets.extend(find_by_prefix(collection, prefix))
        return 0 if not targets else (0 if reject(db, targets) >= 0 else 1)

    query = build_query(args)
    rows = cmd_list(db, query, args.limit) if (args.list or args.approve_all) else []

    if args.approve_all:
        if not rows:
            return 0
        if not args.yes:
            answer = input(f"\n批准上面 {len(rows)} 家候选公司？[y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("已取消。")
                return 0
        approve(db, rows, args.scrape_now)
        return 0

    if not args.list:
        cmd_stats(db)
        print("\n提示：--list 查看候选，--approve-all --min-jobs 5 --min-relevance 4 批量批准")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
