#!/usr/bin/env python3
"""
Bulk re-verify stored jobs against their source ATS.

This is the "batch" half of the browser-extension feature: instead of waiting
for a user to open a job page, walk the jobs already in MongoDB and ask each
employer's own ATS whether the requisition is still live. Jobs whose source has
disappeared are flagged ``is_active=False`` with a ``stale_reason`` so the
website (and the daily digest) stops recommending them.

Examples
--------
    # Dry run over the 200 newest US jobs — prints what would change
    python scripts/verify_active_jobs.py --limit 200 --dry-run

    # Verify everything scraped in the last 30 days, 8 parallel workers
    python scripts/verify_active_jobs.py --days 30 --workers 8

    # Only one company, bypass the shared cache
    python scripts/verify_active_jobs.py --company Stripe --refresh
"""
from __future__ import annotations

import argparse
import re
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db  # noqa: E402
from src.services.source_verify import (  # noqa: E402
    SourceVerifier,
    board_ref_from_company,
    STATUS_CLOSED,
    STATUS_OPEN,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("verify_active_jobs")

# ATS sources worth hitting; anything else (aggregators, custom pages) is only
# verified when ``--include-unknown-sources`` is passed.
TRUSTED_SOURCES = {
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "smartrecruiters",
    "workday",
    "breezy",
    "recruitee",
    "personio",
    "teamtailor",
}


def build_query(args: argparse.Namespace) -> Dict[str, Any]:
    query: Dict[str, Any] = {}
    if not args.include_inactive:
        query["is_active"] = {"$ne": False}
    if args.company:
        query["company"] = {"$regex": f"^{args.company}$", "$options": "i"}
    if args.source:
        query["source"] = args.source
    elif not args.all_sources:
        query["source"] = {"$in": sorted(TRUSTED_SOURCES)}
    if args.days:
        cutoff = datetime.utcnow() - timedelta(days=args.days)
        query["$or"] = [
            {"posted_date": {"$gte": cutoff}},
            {"posted_date": {"$exists": False}, "scraped_at": {"$gte": cutoff}},
        ]
    if args.recheck_after:
        cutoff = datetime.utcnow() - timedelta(hours=args.recheck_after)
        query["$and"] = query.get("$and", []) + [
            {"$or": [
                {"source_checked_at": {"$exists": False}},
                {"source_checked_at": {"$lt": cutoff}},
            ]}
        ]
    return query


def name_key(value: Any) -> str:
    """Normalize a company name for board-token lookups."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def load_company_board_refs(db) -> Dict[str, Dict[str, str]]:
    """
    Build ``company name → {"ats", "token"}`` from the companies collection.

    Needed because many employers link to their own careers page with
    ``?gh_jid=123`` instead of a ``boards.greenhouse.io`` URL; without the token
    those postings cannot be verified.
    """
    refs: Dict[str, Dict[str, str]] = {}
    try:
        for doc in db.companies.find({}, {"name": 1, "domain": 1, "ats_url": 1, "ats_system": 1}):
            ref = board_ref_from_company(doc)
            if not ref:
                continue
            key = name_key(doc.get("name"))
            if key and key not in refs:
                refs[key] = ref
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not build company board map: %s", exc)
    logger.info("Loaded %s company→ATS board mappings", len(refs))
    return refs


def verify_one(verifier: SourceVerifier, job: Dict[str, Any],
               board_ref: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Verify a single job document; returns the update payload."""
    url = job.get("source_url") or ""
    if not url:
        return {"_id": job["_id"], "skipped": "no source_url"}
    result = verifier.verify(
        url,
        hint_title=job.get("title", ""),
        hint_company=job.get("company", ""),
        token_hint=board_ref,
    )
    update: Dict[str, Any] = {
        "_id": job["_id"],
        "job_id": job.get("job_id"),
        "title": job.get("title"),
        "company": job.get("company"),
        "url": url,
        "status": result.status,
        "ats": result.ats,
        "reason": result.reason,
        "confidence": result.confidence,
        "matched_title": result.matched_title,
        "apply_url": result.apply_url,
        "elapsed_ms": result.elapsed_ms,
    }
    if result.status == STATUS_CLOSED:
        update["flags"] = {
            "is_active": False,
            "source_status": STATUS_CLOSED,
            "stale_reason": result.reason,
            "source_checked_at": datetime.utcnow(),
            "deactivated_by": "source_verify",
        }
    else:
        update["flags"] = {
            "source_status": result.status,
            "source_checked_at": datetime.utcnow(),
        }
    return update


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-verify jobs against their source ATS")
    parser.add_argument("--limit", type=int, default=200, help="max jobs to check (default 200)")
    parser.add_argument("--days", type=int, default=0, help="only jobs posted/scraped within N days")
    parser.add_argument("--company", type=str, default="", help="restrict to one company name")
    parser.add_argument("--source", type=str, default="", help="restrict to one ATS source")
    parser.add_argument("--all-sources", action="store_true", help="include non-ATS sources")
    parser.add_argument("--include-inactive", action="store_true", help="also re-check inactive jobs")
    parser.add_argument("--recheck-after", type=int, default=24,
                        help="skip jobs verified within N hours (default 24, 0 = never skip)")
    parser.add_argument("--workers", type=int, default=6, help="parallel verification workers")
    parser.add_argument("--timeout", type=int, default=12, help="per-request timeout seconds")
    parser.add_argument("--refresh", action="store_true",
                        help="accepted for symmetry; the batch path always hits the source ATS")
    parser.add_argument("--dry-run", action="store_true", help="do not write to MongoDB")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    db = get_db()
    query = build_query(args)

    projection = {"job_id": 1, "title": 1, "company": 1, "source": 1,
                  "source_url": 1, "posted_date": 1, "is_active": 1}
    cursor = db.jobs.find(query, projection).sort([("posted_date", -1), ("scraped_at", -1)])
    jobs: List[Dict[str, Any]] = list(cursor.limit(max(1, args.limit)))

    total_matching = db.jobs.count_documents(query)
    logger.info("Query matched %s jobs; checking %s", total_matching, len(jobs))
    if not jobs:
        return 0

    verifier = SourceVerifier(timeout=args.timeout)
    company_refs = load_company_board_refs(db)
    counts = {"open": 0, "closed": 0, "unknown": 0, "skipped": 0}
    closed_samples: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(verify_one, verifier, job, company_refs.get(name_key(job.get("company")))): job
            for job in jobs
        }
        for index, future in enumerate(as_completed(futures), start=1):
            job = futures[future]
            try:
                update = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("verify failed for %s: %s", job.get("job_id"), exc)
                counts["unknown"] += 1
                continue

            if update.get("skipped"):
                counts["skipped"] += 1
                continue

            status = update["status"]
            counts[status] = counts.get(status, 0) + 1
            flags = update["flags"]

            if status == STATUS_CLOSED:
                closed_samples.append(update)
                logger.info("❌ [%s/%s] %s @ %s → %s",
                            index, len(jobs), update["title"], update["company"], update["reason"])
            elif status == STATUS_OPEN:
                logger.debug("✅ %s @ %s", update["title"], update["company"])

            if not args.dry_run:
                db.jobs.update_one({"_id": update["_id"]}, {"$set": flags})

    logger.info("Done. open=%s closed=%s unknown=%s skipped=%s (dry_run=%s)",
                counts["open"], counts["closed"], counts["unknown"], counts["skipped"], args.dry_run)

    if closed_samples:
        logger.info("--- Closed postings detected (%s) ---", len(closed_samples))
        for item in closed_samples[:20]:
            logger.info("  · %s @ %s (%s) → %s",
                        item["title"], item["company"], item["ats"], item["url"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
