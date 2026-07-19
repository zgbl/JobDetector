#!/usr/bin/env python3
"""
Delete old job documents from MongoDB.

Default retention is 60 days so the current production data is not wiped while
the scraper backlog is being repaired. Pass --days 30 later for tighter cleanup.
"""
import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import close_db, get_db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("cleanup_old_jobs")


def build_old_jobs_query(cutoff: datetime) -> dict:
    """Match jobs that have not been seen/scraped within the retention window."""
    return {
        "$or": [
            {"last_seen_at": {"$lt": cutoff}},
            {
                "last_seen_at": {"$exists": False},
                "scraped_at": {"$lt": cutoff},
            },
            {
                "last_seen_at": {"$exists": False},
                "scraped_at": {"$exists": False},
                "posted_date": {"$lt": cutoff},
            },
        ]
    }


def cleanup_old_jobs(days: int, dry_run: bool) -> int:
    db = get_db()
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    query = build_old_jobs_query(cutoff)

    total_jobs = db.jobs.count_documents({})
    old_jobs = db.jobs.count_documents(query)

    logger.info("Retention window: %s days", days)
    logger.info("Cutoff UTC: %s", cutoff.isoformat(timespec="seconds"))
    logger.info("Jobs before cleanup: %s", total_jobs)
    logger.info("Jobs matching cleanup query: %s", old_jobs)

    newest_old = db.jobs.find_one(
        query,
        sort=[("last_seen_at", -1), ("scraped_at", -1), ("posted_date", -1)],
        projection={"_id": 0, "job_id": 1, "title": 1, "company": 1, "last_seen_at": 1, "scraped_at": 1, "posted_date": 1},
    )
    oldest_old = db.jobs.find_one(
        query,
        sort=[("last_seen_at", 1), ("scraped_at", 1), ("posted_date", 1)],
        projection={"_id": 0, "job_id": 1, "title": 1, "company": 1, "last_seen_at": 1, "scraped_at": 1, "posted_date": 1},
    )
    logger.info("Newest job that would be deleted: %s", newest_old)
    logger.info("Oldest job that would be deleted: %s", oldest_old)

    if dry_run:
        logger.info("Dry run only. No jobs deleted.")
        return old_jobs

    result = db.jobs.delete_many(query)
    remaining_jobs = db.jobs.count_documents({})
    logger.info("Deleted jobs: %s", result.deleted_count)
    logger.info("Jobs after cleanup: %s", remaining_jobs)
    return result.deleted_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete old jobs from MongoDB.")
    parser.add_argument("--days", type=int, default=60, help="Retention window in days. Default: 60")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting.")
    args = parser.parse_args()

    if args.days < 1:
        parser.error("--days must be at least 1")

    try:
        cleanup_old_jobs(args.days, args.dry_run)
        return 0
    except Exception:
        logger.exception("Cleanup failed")
        return 1
    finally:
        close_db()


if __name__ == "__main__":
    sys.exit(main())
