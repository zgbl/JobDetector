# Ben Lang Collection Feature - Design Document

## Overview
Ben Lang is a prominent LinkedIn influencer who regularly posts curated lists of well-funded companies ($100M+ raises) that are actively hiring. This feature will:
1. Parse his company lists from text files
2. Automatically discover career sites and ATS systems
3. Import jobs from these companies
4. Create a dedicated "Ben Lang Collection" on the platform

## Business Value
- **Timely Data**: Companies that just raised funding are actively hiring
- **Quality Signal**: $100M+ raises indicate stable, well-funded employers
- **User Trust**: Ben Lang's curation provides editorial value
- **Differentiation**: Unique collection not available on other job boards

---

## Data Source Analysis

### Input Format (`/data/ImportList/BenLang.txt`)
```
COMPANIES THAT RAISED $100M+ RECENTLY (NOW HIRING)

1) Oxide Computer Company - new kind of server (Remote)
2) Defense Unicorns - airgap-native software delivery (US remote)
...
33) Zipline - drone delivery logistics (Bay Area / Texas / Africa)
```

### Parsing Requirements
- Extract company name (before the `-`)
- Extract description/industry
- Extract location hints (in parentheses)
- Handle variations: company suffixes (Inc., Ltd., Company, etc.)

---

## Architecture Design

### Phase 1: Parser & Discovery
**File**: `scripts/import_benlang.py`

```python
class BenLangParser:
    """Parse Ben Lang's company lists"""
    
    def parse_list(self, file_path: str) -> List[CompanyEntry]:
        """
        Extract companies from BenLang.txt
        Returns: [
            {
                'name': 'Oxide Computer Company',
                'description': 'new kind of server',
                'location_hint': 'Remote',
                'source': 'BenLang-2024-02-08'
            }
        ]
        """
        
    def normalize_company_name(self, raw_name: str) -> str:
        """
        Clean company names:
        - 'Oxide Computer Company' -> 'Oxide'
        - 'Skild AI' -> 'Skild AI'
        - Handle Inc., Ltd., Company suffixes
        """
```

**Discovery Flow**:
1. Parse company name
2. Google search: `"{company_name}" careers site`
3. Extract domain from top results
4. Run `ATSDiscovery.discover_ats()` on domain
5. Store in `companies` collection with metadata

### Phase 2: Collection Management
**Database Schema** (`collections` collection):
```javascript
{
    "_id": ObjectId(...),
    "slug": "ben-lang-feb-2024",
    "name": "Ben Lang's $100M+ Raises (Feb 2024)",
    "description": "33 well-funded companies actively hiring",
    "icon": "💰",
    "companies": [
        "Oxide Computer Company",
        "Defense Unicorns",
        // ... all 33 companies
    ],
    "metadata": {
        "source": "LinkedIn",
        "author": "Ben Lang",
        "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:7425206257516646400/",
        "date_posted": "2024-02-08",
        "type": "curated_list"
    },
    "created_at": ISODate(...)
}
```

### Phase 3: Frontend Integration
**UI Additions**:

1. **Favorites Page** - New Collection Card:
   ```html
   <div class="collection-card benlang-special">
       <div class="collection-header">
           <span class="icon">💰</span>
           <span class="badge new">NEW</span>
       </div>
       <h3>Ben Lang's $100M+ Raises</h3>
       <p>33 well-funded companies actively hiring</p>
       <div class="meta">
           <span>📅 Feb 8, 2024</span>
           <span>🏢 33 companies</span>
       </div>
   </div>
   ```

2. **Special Styling** (`css/style.css`):
   ```css
   .benlang-special {
       border: 2px solid gold;
       background: linear-gradient(135deg, #1a1a2e, #16213e);
   }
   ```

---

## Implementation Plan

### Step 1: Text Parser (30 min)
**File**: `scripts/parse_benlang.py`
```python
import re
from typing import List, Dict

def parse_benlang_list(file_path: str) -> List[Dict]:
    """Parse BenLang.txt format"""
    with open(file_path) as f:
        lines = f.readlines()
    
    companies = []
    pattern = r'^\d+\)\s+(.+?)\s+-\s+(.+?)\s+\((.+?)\)'
    
    for line in lines:
        match = re.search(pattern, line)
        if match:
            companies.append({
                'name': match.group(1).strip(),
                'description': match.group(2).strip(),
                'location': match.group(3).strip()
            })
    
    return companies
```

### Step 2: Career Site Discovery (1-2 hours)
**File**: `scripts/import_benlang.py`
```python
from src.services.ats_discovery import ATSDiscovery
import requests
from bs4 import BeautifulSoup

class BenLangImporter:
    def find_career_site(self, company_name: str) -> str:
        """Google search for career page"""
        # Use SerpAPI or direct Google search
        query = f'"{company_name}" careers'
        # Extract domain from top result
        
    def import_company(self, company_data: Dict):
        """
        1. Find career site
        2. Discover ATS
        3. Add to companies collection
        4. Trigger job scrape
        """
```

### Step 3: Collection Creation (30 min)
**File**: `scripts/create_benlang_collection.py`
```python
def create_collection(db, company_names: List[str]):
    """Create Ben Lang collection in DB"""
    db.collections.insert_one({
        'slug': 'ben-lang-feb-2024',
        'name': "Ben Lang's $100M+ Raises",
        'companies': company_names,
        'metadata': {
            'source': 'LinkedIn',
            'post_url': '...',
            'date': '2024-02-08'
        }
    })
```

### Step 4: Frontend Display (1 hour)
- Update `favorites.html` to show Ben Lang collection
- Add special styling for featured collections
- Add attribution and link to original post

---

## Automation Strategy

### Manual Workflow (MVP)
1. User copies Ben Lang's post to `/data/ImportList/BenLang-YYYY-MM-DD.txt`
2. Run: `python scripts/import_benlang.py --file BenLang-2024-02-08.txt`
3. Script outputs:
   - ✅ Found 33 companies
   - ✅ Discovered 28 career sites (5 failed)
   - 🔄 Importing jobs...
4. Auto-creates collection in DB

### Future: LinkedIn Scraper (Optional)
- Monitor Ben Lang's LinkedIn profile
- Auto-detect posts with keywords: "RAISED", "HIRING", "$100M+"
- Auto-parse and import

---

## Risk Mitigation

### Challenge 1: Company Name Ambiguity
**Problem**: "Clear Street" vs "ClearStreet" vs "Clear"  
**Solution**: 
- Fuzzy matching against existing companies
- Manual review list for ambiguous names
- Store multiple name variations

### Challenge 2: ATS Discovery Failures
**Problem**: Some companies may not have public career pages  
**Solution**:
- Fallback to LinkedIn Jobs API
- Manual career URL input
- Mark as "pending_discovery"

### Challenge 3: Stale Data
**Problem**: Ben Lang posts are time-sensitive (companies stop hiring)  
**Solution**:
- Add `expiry_date` to collections (e.g., 3 months)
- Auto-archive old collections
- Badge: "🔥 Active" vs "📦 Archived"

---

## Success Metrics

### Phase 1 (Parser)
- ✅ Successfully parse 95%+ of company names
- ✅ Extract locations correctly

### Phase 2 (Discovery)
- 🎯 Find career site for 80%+ companies
- 🎯 Discover ATS for 70%+ companies
- 🎯 Import jobs from 60%+ companies

### Phase 3 (User Engagement)
- 📈 Track clicks on "Ben Lang Collection"
- 📈 Jobs applied from this collection
- 📈 Collection bookmark rate

---

## Timeline Estimate

| Phase | Task | Time | Priority |
|-------|------|------|----------|
| 1 | Text parser | 30 min | P0 |
| 2 | Career site discovery | 2 hrs | P0 |
| 3 | ATS discovery integration | 1 hr | P0 |
| 4 | Collection DB schema | 30 min | P0 |
| 5 | Frontend UI | 1 hr | P1 |
| 6 | Styling & polish | 30 min | P1 |
| **Total** | **MVP** | **~6 hours** | |

---

## File Structure
```
JobDetector/
├── data/
│   └── ImportList/
│       ├── BenLang-2024-02-08.txt
│       └── BenLang-2024-03-15.txt (future)
├── scripts/
│   ├── parse_benlang.py          # NEW
│   ├── import_benlang.py         # NEW
│   └── create_benlang_collection.py  # NEW
├── Design/
│   └── BenLang_Collection.md     # THIS FILE
└── favorites.html                # UPDATE
```

---

## Next Steps

1. **Immediate**: Run parser on current file to validate format
2. **Week 1**: Implement career site discovery
3. **Week 1**: Create first collection manually
4. **Week 2**: Add frontend UI
5. **Future**: Consider automation for new posts

---

## Example Output

**Terminal**:
```bash
$ python scripts/import_benlang.py --file BenLang-2024-02-08.txt

📋 Parsing Ben Lang list: BenLang-2024-02-08.txt
✅ Found 33 companies

🔍 Discovering career sites...
✅ Oxide Computer Company → https://oxide.computer/careers (Greenhouse)
✅ Defense Unicorns → https://defenseunicorns.com/careers (Lever)
❌ Zanskar → No career page found (will retry manually)
...

📊 Summary:
   - Companies parsed: 33
   - Career sites found: 28 (85%)
   - ATS discovered: 24 (73%)
   - Jobs imported: 847

🎉 Collection created: ben-lang-feb-2024
   View at: http://localhost:8123/favorites?collection=ben-lang-feb-2024
```

**Frontend**:
User sees new collection card with gold border, Ben Lang's profile picture, and attribution.
