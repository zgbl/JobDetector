#!/usr/bin/env python3
"""
Discover companies that are not yet in the database.

Harvests candidate companies from external sources, resolves which ATS each one
uses, scores how relevant its open roles look, and writes the result to the
``company_candidates`` staging collection. **Nothing is scraped or inserted into
``companies`` here** — a human approves candidates first (see
``scripts/review_candidates.py``).

Examples
--------
    # Latest "Who is hiring?" thread, dry run (no writes)
    python scripts/discover_companies.py --source hn --months 1 --dry-run

    # Last 3 threads, only companies with >= 3 open roles and a relevant board
    python scripts/discover_companies.py --source hn --months 3 \
        --min-jobs 3 --min-relevance 3

    # Recent YC batches in AI / dev-tools
    python scripts/discover_companies.py --source yc \
        --batches "Winter 2026,Fall 2025" --industries "Artificial Intelligence,Developer Tools"

    # Both sources, cap the network work
    python scripts/discover_companies.py --source hn,yc --max-resolve 120 --workers 8
"""
from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db  # noqa: E402
from src.services.company_discovery import (  # noqa: E402
    CompanyDiscoveryService,
    RawCandidate,
    ResolvedCandidate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("discover_companies")

CANDIDATES_COLLECTION = "company_candidates"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover new companies and stage them for review")
    parser.add_argument("--source", default="hn", help="comma separated: hn, yc")
    parser.add_argument("--months", type=int, default=1, help="How many recent HN hiring threads (hn)")
    parser.add_argument("--max-posts", type=int, default=400, help="Max HN postings to parse per run")
    parser.add_argument("--batches", default="", help="YC batches to include, comma separated")
    parser.add_argument("--industries", default="", help="YC industries to include, comma separated")
    parser.add_argument("--yc-limit", type=int, default=400, help="Max YC companies to consider")
    parser.add_argument("--max-resolve", type=int, default=80,
                        help="Max candidates to run through ATS resolution (network bound)")
    parser.add_argument("--workers", type=int, default=8, help="Parallel resolution workers")
    parser.add_argument("--timeout", type=int, default=15, help="Per-request timeout seconds")
    parser.add_argument("--min-jobs", type=int, default=1, help="Drop boards with fewer open roles")
    parser.add_argument("--min-relevance", type=int, default=0, help="Drop boards scoring below this (0-10)")
    parser.add_argument("--no-crawl", action="store_true", help="Skip the careers-page crawl fallback")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to MongoDB")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def harvest(args: argparse.Namespace, service: CompanyDiscoveryService) -> List[RawCandidate]:
    sources = [s.strip().lower() for s in args.source.split(",") if s.strip()]
    raw: List[RawCandidate] = []
    if "hn" in sources:
        found = service.fetch_hn(months=args.months, max_posts=args.max_posts)
        logger.info("HN: %s candidate postings", len(found))
        raw.extend(found)
    if "yc" in sources:
        batches = [b.strip() for b in args.batches.split(",") if b.strip()] or None
        industries = [i.strip() for i in args.industries.split(",") if i.strip()] or None
        found = service.fetch_yc(
            batches=batches, industries=industries, limit=args.yc_limit
        )
        logger.info("YC: %s candidate companies", len(found))
        raw.extend(found)
    return raw


def prioritize(raw: List[RawCandidate]) -> List[RawCandidate]:
    """
    Interleave the three candidate classes so a run spends its resolution budget
    on all of them: post-link (free), domain (probe/crawl), name-only (guess).
    Sorting by class instead would burn the whole budget on the easy ones.
    """
    def bucket(item: RawCandidate) -> int:
        if item.ats_urls:
            return 0
        if item.domain:
            return 1
        return 2

    groups: Dict[int, List[RawCandidate]] = {0: [], 1: [], 2: []}
    for item in raw:
        groups[bucket(item)].append(item)

    out: List[RawCandidate] = []
    while any(groups.values()):
        for key in (0, 1, 2):
            if groups[key]:
                out.append(groups[key].pop(0))
    return out


def resolve_all(service: CompanyDiscoveryService, raws: List[RawCandidate],
                workers: int) -> List[ResolvedCandidate]:
    results: List[ResolvedCandidate] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(service.resolve, item): item for item in raws}
        for index, future in enumerate(as_completed(futures), start=1):
            item = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                logger.warning("resolve failed for %s: %s", item.name, exc)
            if index % 25 == 0:
                logger.info("  resolved %s/%s", index, len(raws))
    return results


def write_candidates(db, candidates: List[ResolvedCandidate]) -> Dict[str, int]:
    """Upsert staged candidates. Existing rows keep their review status."""
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    collection = db[CANDIDATES_COLLECTION]
    for candidate in candidates:
        payload = candidate.to_dict()
        payload.pop("_id", None)
        existing = collection.find_one({"fingerprint": candidate.fingerprint})
        if existing is None and candidate.domain:
            existing = collection.find_one({"domain": candidate.domain, "status": {"$ne": "rejected"}})
        if existing:
            # Never overwrite a human decision.
            if existing.get("status") in ("approved", "rejected"):
                stats["skipped"] += 1
                continue
            payload["status"] = existing.get("status", "pending")
            payload["discovered_at"] = existing.get("discovered_at", payload["discovered_at"])
            payload["first_seen_at"] = existing.get("first_seen_at", payload["discovered_at"])
            collection.update_one({"_id": existing["_id"]}, {"$set": payload})
            stats["updated"] += 1
        else:
            payload["first_seen_at"] = payload["discovered_at"]
            collection.insert_one(payload)
            stats["inserted"] += 1
    return stats


def main() -> int:
    args = parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    service = CompanyDiscoveryService(
        timeout=args.timeout, crawl_fallback=not args.no_crawl
    )

    raw = harvest(args, service)
    if not raw:
        logger.warning("no candidates harvested")
        return 0
    logger.info("harvested %s raw candidates; resolving at most %s", len(raw), args.max_resolve)

    to_resolve = prioritize(raw)[: max(1, args.max_resolve)]
    resolved = resolve_all(service, to_resolve, args.workers)

    # Only keep things a human could actually act on.
    kept: List[ResolvedCandidate] = []
    for candidate in resolved:
        if candidate.ats and candidate.open_jobs >= args.min_jobs and candidate.relevance_score >= args.min_relevance:
            kept.append(candidate)

    db = None if args.dry_run else get_db()
    if db is not None:
        marked, duplicates = service.mark_duplicates(kept, db)
        fresh = [c for c in marked if c.status == "pending"]
        stats = write_candidates(db, fresh)
        logger.info("dedup: %s already known / repeated in batch", duplicates)
    else:
        service.mark_duplicates(kept, get_db())  # report-only dedup in dry runs
        fresh = [c for c in kept if c.status == "pending"]
        stats = {"inserted": 0, "updated": 0, "skipped": 0}

    resolved_count = sum(1 for c in resolved if c.ats)
    logger.info("resolution: %s/%s resolved to an ATS", resolved_count, len(resolved))
    logger.info("kept %s relevant candidates (%s new)", len(kept), len(fresh))
    logger.info("db writes: %s", stats)

    print("\n候选预览（按相关性排序）:")
    for candidate in sorted(fresh, key=lambda c: (c.relevance_score, c.open_jobs), reverse=True)[:20]:
        print(f"  {candidate.relevance_score:>2}分 | {candidate.open_jobs:>3}岗 | "
              f"{candidate.name[:22]:24} {candidate.ats or '-':10} "
              f"{candidate.board_token[:20] if candidate.board_token else '-':22} "
              f"{candidate.resolve_method}")
    if args.dry_run:
        print("\n(dry run — nothing written)")

    # Summary by method helps spot which resolution path is doing the work.
    by_method: Dict[str, int] = {}
    for candidate in resolved:
        if candidate.ats:
            by_method[candidate.resolve_method.split(":")[0]] = by_method.get(
                candidate.resolve_method.split(":")[0], 0) + 1
    if by_method:
        print(f"\n解析方式分布: {by_method}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
