"""Initialize the central search directory once; preserve existing DB edits."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.db import get_db
from api.linkedin_catalog import get_catalog

if __name__ == '__main__':
    catalog = get_catalog(get_db())
    total = sum(len(group['items']) for group in catalog['groups']) + len(catalog['signals'])
    print(f"Central search directory ready: {total} entries, {len(catalog['groups']) + 1} sections, revision {catalog['revision']}")
