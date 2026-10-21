"""Add the Software Engineering & SWE board to the canonical MongoDB directory.

Runs as a dry run by default. --apply changes only the catalog groups, revision,
and timestamp; existing groups, signals, and user subscriptions are preserved.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from api.db import get_db
from api.linkedin_catalog import CATALOG_ID


SEED = Path(__file__).resolve().parent.parent / "data" / "linkedin_search_presets.json"


def add_group(db, apply=False):
    desired = next(group for group in json.loads(SEED.read_text())["groups"] if group["id"] == "software")
    collection = db.linkedin_search_catalog
    current = collection.find_one({"_id": CATALOG_ID})
    if current is None:
        raise RuntimeError("Central directory does not exist; deploy the new seed first.")
    existing = next((group for group in current["groups"] if group["id"] == "software"), None)
    if existing is not None:
        if existing != desired:
            raise RuntimeError("Software board was centrally edited; refusing to overwrite it.")
        return {"changed": False, "revision": current["revision"], "total": sum(len(g["items"]) for g in current["groups"]) + len(current["signals"])}

    groups = [desired, *current["groups"]]
    content = {"groups": groups, "signals": current["signals"]}
    revision = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]
    total = sum(len(group["items"]) for group in groups) + len(current["signals"])
    if apply:
        result = collection.update_one(
            {"_id": CATALOG_ID, "revision": current["revision"]},
            {"$set": {"groups": groups, "revision": revision, "updated_at": datetime.now(timezone.utc)}},
        )
        if result.modified_count != 1:
            raise RuntimeError("Central directory changed during update; retry after reviewing it.")
    return {"changed": apply, "revision": revision, "total": total}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the new board to MongoDB")
    args = parser.parse_args()
    result = add_group(get_db(), apply=args.apply)
    print(json.dumps(result))
