# Runbook: Updating "Ben Lang's List" Collection

Use this guide to manually update the Ben Lang collection when Ben publishes a new Google Sheet list.

## Prerequisites
- Terminal open at project root (`/Users/tuxy/Codes/Github2/JobDetector`)
- Python environment active (ensure dependencies are installed: `pip install -r requirements.txt`)

## Step-by-Step Guide

### 1. Update the Source Data
1. Download the Google Sheet as CSV.
2. Save it under:
   ```bash
   data/benlang/google_sheets/
   ```
   Keep prior CSV files in this directory. The old `data/ImportList/BenLang.txt` remains supported.

### 2. Clean & Deduplicate
The importer deduplicates overlapping CSV files by career link or normalized company name:
```bash
python3 scripts/import_benlang.py --dry-run
```

### 3. Import & Discovery (Async)
Run the importer to find career sites and identify ATS systems for new companies. This script also updates the Collection record in the database.
```bash
python3 scripts/import_benlang.py
```
*This runs in parallel (Async) and should take 1-2 minutes for hundreds of companies.*
*Ben Lang is stored as a source record inside the unified `companies` collection. Career links, thread links, source filenames, and import identifiers are kept in `metadata.source_records`; no separate company-name collection is updated.*

### 4. Fetch Jobs (Scraping)
The import step only finds *where* to scrape. To actually populate the jobs, run the scraper:
```bash
python3 scripts/scrape_benlang.py
```
*This will iterate through all companies in the collection with valid ATS systems and download active jobs.*

### 5. Verify Updates
1. Start the local server (if not running):
   ```bash
   npm run dev
   # or
   python3 -m api.index
   ```
2. Visit [http://localhost:8123](http://localhost:8123)
3. Check the "Ben Lang's Collection" card for the updated company count.
4. Click into the collection to see new jobs.

---

## Troubleshooting

**Q: ModuleNotFoundError: No module named 'fastapi'**
A: This usually means dependencies aren't installed in your current environment.
Run: `pip install -r requirements.txt`

**Q: Some companies show "ATS type unknown"**
A: This means the auto-discovery script couldn't identify the ATS from the career page.
- **Fix**: Check `data/companies_override.yaml` (if exists) or manually check their career site. We currently support Greenhouse, Lever, Ashby, and Workable.
