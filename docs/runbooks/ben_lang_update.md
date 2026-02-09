# Runbook: Updating "Ben Lang's List" Collection

Use this guide to manually update the "Ben Lang's $100M+ Raises" collection on your local machine when Ben posts a new list on LinkedIn.

## Prerequisites
- Terminal open at project root (`/Users/tuxy/Codes/TestProjects/JobDetector`)
- Python environment active (ensure dependencies are installed: `pip install -r requirements.txt`)

## Step-by-Step Guide

### 1. Update the Source Data
1. Go to [Ben Lang's LinkedIn Activity](https://www.linkedin.com/in/benmlang/recent-activity/all/).
2. Copy the text of his latest posts (lists of companies).
3. Open the source file:
   ```bash
   code data/ImportList/BenLang.txt
   ```
4. **Append** the new text to the bottom of the file (or replace it if you want a fresh start, but appending preserves history).
5. Save the file.

### 2. Clean & Deduplicate
Since Ben often reposts or overlaps lists, run the cleaner to remove duplicates and normalize format:
```bash
python3 scripts/clean_benlang_list.py
```
*Output will show how many duplicate companies were removed.*

### 3. Import & Discovery (Async)
Run the importer to find career sites and identify ATS systems for new companies. This script also updates the Collection record in the database.
```bash
python3 scripts/import_benlang.py
```
*This runs in parallel (Async) and should take 1-2 minutes for hundreds of companies.*
*Look for "✅ Imported" messages for new discoveries.*

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
