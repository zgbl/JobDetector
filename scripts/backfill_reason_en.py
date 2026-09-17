#!/usr/bin/env python3
"""
Backfill ``reason_en`` on cached source checks.

The verification engine used to emit only a Chinese ``reason``. It now returns a
bilingual result, but entries cached before that change have no ``reason_en``,
so any reader that grabs the raw document would render Chinese on the English
site. The API backfills on read; this script fixes the stored data itself so the
problem cannot resurface through a future read path.

    python scripts/backfill_reason_en.py            # dry run (default)
    python scripts/backfill_reason_en.py --apply    # write the changes
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db  # noqa: E402
from src.services.source_verify import to_english_reason  # noqa: E402

COLLECTION = "source_checks"


def needs_backfill(result: Dict[str, Any]) -> bool:
    return bool(result.get("reason")) and not result.get("reason_en")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill reason_en in source_checks")
    parser.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    parser.add_argument("--limit", type=int, default=0, help="max documents to touch (0 = all)")
    args = parser.parse_args()

    db = get_db()
    collection = db[COLLECTION]

    total = collection.count_documents({})
    cursor = collection.find({}, {"key": 1, "result": 1})
    if args.limit:
        cursor = cursor.limit(args.limit)

    scanned = 0
    pending: List[Dict[str, Any]] = []
    for doc in cursor:
        scanned += 1
        result = doc.get("result") or {}
        if not needs_backfill(result):
            continue
        translated = to_english_reason(result.get("reason", ""))
        if not translated or translated == result.get("reason"):
            print(f"  ⚠️  no English rule for: {result.get('reason', '')[:60]!r}")
        pending.append({
            "_id": doc["_id"],
            "key": doc.get("key"),
            "reason": result.get("reason", ""),
            "reason_en": translated,
        })

    print(f"collection: {COLLECTION}")
    print(f"documents : {total} (scanned {scanned})")
    print(f"to fix    : {len(pending)}")

    for item in pending[:20]:
        print(f"  · {item['key']}")
        print(f"      zh: {item['reason'][:70]}")
        print(f"      en: {item['reason_en'][:70]}")

    if not pending:
        print("nothing to do ✅")
        return 0

    if not args.apply:
        print("\n(dry run — re-run with --apply to write)")
        return 0

    updated = 0
    for item in pending:
        collection.update_one(
            {"_id": item["_id"]},
            {"$set": {"result.reason_en": item["reason_en"]}},
        )
        updated += 1

    remaining = collection.count_documents({"result.reason": {"$nin": [None, ""]},
                                            "result.reason_en": {"$in": [None, ""]}})
    print(f"\nupdated {updated} document(s); still missing reason_en: {remaining} ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
