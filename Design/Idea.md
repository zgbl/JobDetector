# Project Blueprint: JobDetector AI & Daily Digest

## 🌟 Project Essence
JobDetector is a personalized, AI-powered job monitoring and recommendation engine. It bridges the gap between massive, messy job market data and a specific career track by automating the full lifecycle: **Ingestion → Scoring → Notification**.

---

## 🛠 Core Capabilities (Skills)

### 1. Intelligent Ingestion (The Scrapers)
- **Direct Monitoring**: Bypasses job boards by scraping company career sites directly.
- **ATS Discovery**: Automatically detects and parses jobs from Greenhouse, Lever, and Workday systems.
- **Smart Pipeline**: Supports "Ingestion Pipelines" that use AI to extract company metadata from unstructured text.
- **🛰️ Google Structured Data "Hitchhiking" (New Plan)**: 
    - **Concept**: Leverage [Google Job Posting Structured Data](https://developers.google.com/search/docs/appearance/structured-data/job-posting).
    - **Action**: Many companies embed JSON-LD (`application/ld+json`) for Googlebot. We can "hitchhike" on this to extract clean, standardized fields (`title`, `description`, `datePosted`) without custom CSS selectors for every site.
    - **Goal**: Build a universal harvester that mimics Googlebot to crawl more companies efficiently.

### 2. AI Scoring Engine (The Brain)
- **Multi-Model Support**: Integrates with **Google Gemini (1.5 Flash)**, **MiniMax**, **OpenRouter**, and **DeepSeek**.
- **Contextual Matching**: Scores jobs (0-10) by comparing job descriptions against a detailed **Career Profile**.
- **Fallback Logic**: Provides keyword-based scoring when LLM APIs are unavailable.

### 3. Daily Career Digest (The Push)
- **Personalized Delivery**: Sends premium HTML emails containing the top-matched jobs for the last 24 hours.
- **Dynamic Controls**: User-managed frequency (Daily/Weekly), lookback windows, and minimum score thresholds.
- **Self-Service Dashboard**: A dedicated interface (`my_digest.html`) for manual runs, profile updates, and history tracking.

---

## 🎯 Target Track: Xinyu Tu (The "赛道")
The system is currently optimized for a high-seniority career path in AI and Cloud Infrastructure.

### Priority Roles
1.  **AI Platform Engineer** (GenAI/LLM Infrastructure)
2.  **Cloud/Enterprise Solution Architect**
3.  **Staff/Principal Platform Engineer**

### Key Skills & Keywords
- **Cloud**: AWS (Certified), Azure (Expert), GCP
- **Infra**: Kubernetes (EKS/AKS/GKE), Terraform, Istio
- **AI/ML**: LLM Orchestration, RAG Pipelines, Vector DBs (LangChain)
- **Languages**: Go (Expert), Python (Production)

### Priority Companies (Tier 1)
- **Finance**: Morgan Stanley, JPMorgan Chase, Goldman Sachs
- **Tech Giants**: AWS, Microsoft Azure, Google Cloud
- **AI Leaders**: Databricks, Snowflake, OpenAI, Anthropic

### Exclusions (Noise)
- Junior roles (IC1/IC2), Pure ML Research (PhD), GPU Kernel/Hardware, QA/Test.

---

## 🏗 Technical Architecture

### Data Flow
1.  **Scraper** (`scripts/prod_scraper.py`) → Saves jobs to **MongoDB** (`jobs` collection).
2.  **Digest Engine** (`scripts/personal_digest.py`) → Fetches recent jobs, loads **User Profile**, calls **LLM API** for scoring.
3.  **Notifier** (`api/email_service.py`) → Sends HTML email via **SMTP**.
4.  **UI** (`my_digest.html`) → Interacts with **FastAPI** (`api/index.py`) to trigger runs and manage settings.

### Component Map
- `api/index.py`: The central nervous system (FastAPI).
- `src/database/`: Persistence layer (MongoDB models).
- `scripts/`: Operational tools (Scrapers, Pipeline, Digest).
- `.env`: Secret management (API keys, DB URIs).

---

## 🚀 Development Roadmap (Future Skills)
- [ ] **JSON-LD Universal Harvester**: Implement the "Google Hitchhiking" logic for generic job extraction.
- [ ] **Resume Tailoring**: Use AI to generate a matching pitch for high-score jobs.
- [ ] **Market Sentiment**: Track job opening trends for Tier 1 companies.
- [ ] **Interactive Chat**: Ask the AI *why* a job matched or didn't match.
- [x] **Keyword Email Alert**: Per-user keyword-based job alert with daily/weekly frequency and opt-out. *(Shipped 2026-05)*


---

## 📋 Manual Company Expansion Pipeline

### Concept
Beyond scheduled YAML imports, a lightweight manual intake channel allows ad-hoc company additions discovered during daily browsing — without touching the database directly.

### Files
| File | Role |
|---|---|
| `data/manualAddList.csv` | Hand-maintained intake queue (`Company, URL`) |
| `data/ManualList_finished.csv` | Archive of successfully processed entries |
| `scripts/process_manual_list.py` | The processor script |

### Workflow (`scripts/process_manual_list.py`)
1. **Read** `manualAddList.csv` — skips header, blank lines, and rows already marked `[FAILED:…]` or `[ALREADY_IN_DB]`.
2. **Dedup check** — queries MongoDB by name + careers URL to avoid re-registering known companies.
3. **ATS Detection** — tries URL pattern match first (Greenhouse/Lever/Workday/Ashby/Workable/Wellfound), then active probing.
4. **Register** company in MongoDB with `added_by: process_manual_list` and joins daily scrape queue.
5. **One-shot scrape** — immediately fetches current job listings.
6. **On success** → row is moved to `ManualList_finished.csv` and deleted from intake queue.
7. **On failure** → row is annotated in-place: `Company, URL,[FAILED: reason]` — prevents accidental re-paste.
8. **Already in DB** → annotated with `[ALREADY_IN_DB]` for awareness.

### Usage
```bash
# From project root
python scripts/process_manual_list.py
```
Logs are written to `logs/manual_list_processor.log`.

---

## 🔔 User-Specific Keyword Email Alert

### Concept
A lightweight, per-user email alert engine that runs **independently of the AI digest**.  
Users define a list of skill keywords (e.g. `Kubernetes, LLM, Go`). The engine queries the jobs database for matching postings since the last alert and emails a digest to the user's chosen address at their chosen frequency.  
No LLM API key required — pure keyword-match on `title`, `description`, and `skills` fields.

### Feature Highlights
| Capability | Detail |
|---|---|
| **Keyword List** | Up to 30 keywords; any match triggers inclusion (OR logic) |
| **Custom Delivery Email** | Can differ from the account login email |
| **Frequency** | `daily`, `weekly`, or `off` |
| **Opt-Out** | One-click disable; keywords are preserved for easy re-enable |
| **Stats** | Last sent date, total emails sent, last match count — shown in UI |

### Data Model (`user_alert_settings` MongoDB collection)
```json
{
  "user_email":       "user@example.com",
  "keywords":         ["Kubernetes", "LLM", "Platform Engineer"],
  "alert_email":      "custom@example.com",
  "frequency":        "daily",          // "daily" | "weekly" | "off"
  "is_active":        true,
  "last_sent_at":     "2026-05-07T13:00:00Z",
  "total_emails_sent": 12,
  "last_matched_count": 4,
  "created_at":       "2026-04-01T00:00:00Z",
  "updated_at":       "2026-05-07T12:00:00Z"
}
```

### API Endpoints
| Method | Route | Description |
|---|---|---|
| `GET` | `/api/user/alert-settings` | Fetch current user's alert config |
| `POST` | `/api/user/alert-settings` | Save keywords, email, frequency, is_active |

### Files
| File | Role |
|---|---|
| `scripts/keyword_alert.py` | Alert engine — queries DB, renders email, sends via SMTP |
| `api/index.py` | `GET/POST /api/user/alert-settings` endpoints |
| `my_digest.html` | **Keyword Email Alert** UI section with tag-pill editor |
| `.github/workflows/keyword_alert.yml` | GitHub Actions schedule: daily at 9 AM ET |

### Workflow (`scripts/keyword_alert.py`)
1. **Load** all docs from `user_alert_settings` where `is_active: true`.
2. **Frequency check** — skip if `last_sent_at` is within the window (20h for daily, 6d for weekly). Use `--force` to bypass.
3. **Compute cutoff** — `last_sent_at` (or `now - 1d/7d` for first run).
4. **Query jobs** — `is_active: true`, `posted_date >= cutoff`, title/description/skills regex OR across all keywords.
5. **Render premium HTML email** — job list, keyword pills, CTA button, unsubscribe link.
6. **Send via Gmail SMTP** to `alert_email`.
7. **Update** `last_sent_at`, `total_emails_sent`, `last_matched_count` in MongoDB.

### GitHub Actions Schedule
```yaml
# keyword_alert.yml — runs daily at 9:00 AM ET (after scraper)
on:
  schedule:
    - cron: '0 13 * * *'
  workflow_dispatch:   # manual trigger with dry_run / force / target_user inputs
```

### CLI Usage
```bash
# Normal run — respects frequency windows
python scripts/keyword_alert.py

# Preview without sending
python scripts/keyword_alert.py --dry-run

# Force-send ignoring frequency window
python scripts/keyword_alert.py --force

# Run for a single user only
python scripts/keyword_alert.py --user someone@example.com
```

