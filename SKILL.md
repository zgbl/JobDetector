# JobDetector Project Skill

Use this file as the first project brief whenever an AI assistant opens this repo. It is intentionally written for both the project owner and future AI agents. Keep it easy to edit: add, remove, or mark features under the page where users see them.

## Product Goal

JobDetector is a multi-user job board and personal job radar.

The core user promise is:

> A user should not need to search keywords every day. They upload one or more resumes/career directions, open the site, and immediately see jobs that fit their direction, while still being able to browse all jobs.

Important product rule:

- This is not hardcoded for one person.
- Resume/career direction data must be user-specific.
- A user can keep up to five career directions, usually representing different resume tracks.
- Desktop UI should use horizontal space efficiently. Avoid full-width oversized cards when a compact split layout works better.

## Current Stack

- Frontend: vanilla HTML/CSS/JavaScript.
- Backend: FastAPI in `api/index.py`.
- Database: MongoDB via `api/db.py`.
- Hosting: Vercel, configured by `vercel.json`.
- Scheduled jobs: GitHub Actions in `.github/workflows/`.
- Main local URL: `http://localhost:8123`.
- Local server command: `python api/index.py`.

## Key Files

- Main jobs app: `index.html`, `js/main.js`, `css/style.css`.
- Career digest and resume directions: `my_digest.html`.
- Backend API: `api/index.py`.
- Email service: `api/email_service.py`.
- Personal AI digest script: `scripts/personal_digest.py`.
- Keyword alert script: `scripts/keyword_alert.py`.
- Production scraper: `scripts/prod_scraper.py`.
- Company intake pipeline: `scripts/company_intake_pipeline.py`.
- Company import/scrape scripts: `scripts/import_companies.py`, `scripts/import_benlang.py`, `scripts/scrape_new_companies.py`, `scripts/process_manual_list.py`.
- System design notes: `Design/SystemDesign.md`.
- Deployment docs: `docs/DEVELOPMENT.md`, `docs/PRODUCTION_DEPLOYMENT.md`.

## Local Development

Start local server:

```bash
cd /Users/tuxy/Codes/Github2/JobDetector
source venv/bin/activate
python api/index.py
```

Open:

- Jobs dashboard: `http://localhost:8123/`
- My Digest: `http://localhost:8123/my_digest.html`
- Favorites: `http://localhost:8123/favorites.html`
- Admin stats: `http://localhost:8123/admin_stats.html`
- API health: `http://localhost:8123/api/health`

Use port `8123` for local testing.

## Deployment And Automation

Production is designed as:

- Frontend and FastAPI backend deployed on Vercel.
- `vercel.json` rewrites `/api/*` to `api/index.py`.
- Push to GitHub triggers Vercel deployment if the Vercel project is connected.
- MongoDB Atlas stores jobs, companies, users, profiles, alerts, feedback, and logs.

GitHub Actions:

- `.github/workflows/scrape_jobs.yml`
  - Name: Scheduled Job Scrape.
  - Runs every 6 hours.
  - Imports companies, imports Ben Lang list, runs production scraper, sends legacy alerts.

- `.github/workflows/daily_digest.yml`
  - Name: Daily Personal Career Digest.
  - Runs daily at 8:00 AM ET.
  - Reads active AI digest subscribers from DB unless manually given a recipient.
  - Calls `scripts/personal_digest.py`.

- `.github/workflows/keyword_alert.yml`
  - Name: User Keyword Job Alerts.
  - Runs daily at 9:00 AM ET.
  - Calls `scripts/keyword_alert.py`.

## Page Map And User-Facing Features

### Page: Jobs Dashboard

File:

- `index.html`
- `js/main.js`
- `css/style.css`

URL:

- `/`

Purpose:

- Main app experience.
- Let users browse all jobs and see personalized recommendations side by side.

Visible Features:

- Top nav:
  - Jobs
  - Favorites
  - Companies
  - About
  - My Searches
  - Request Company, visible to logged-in users
  - Admin Dashboard, visible to admin users
  - My Digest, visible to logged-in users
  - Feedback

- Hero search:
  - Search title, company, or skills.
  - Quick tags: Python, Go, Cloud, Frontend.

- Stats:
  - Active Jobs
  - Companies
  - Remote Roles

- All jobs column:
  - Filters: All Jobs, Full-time, Internship, Remote Only.
  - Category filter.
  - Multi-keyword tag filter.
  - Multi-location tag filter.
  - Date filter.
  - Reset.
  - Save search / Create Job Alert.
  - Paginated job grid.

- Personal Job Radar column:
  - Shows compact recommended jobs for selected career direction.
  - Uses two-column desktop layout: all jobs on left, recommendations on right.
  - Recommendation cards are compact list items, not full-width large cards.
  - Profile selector chooses career direction.
  - Refresh button reranks recommendations.
  - Inline career profile editor can edit resume direction, geography, roles, skills, companies, exclusions.
  - Job feedback buttons: thumbs up/down/bookmark.
  - Job links should open in a new tab.

Behavior Rules:

- Logged-out users see the general job board.
- Logged-in users see Personal Job Radar.
- Jobs list must remain accessible even when recommendations exist.
- Clicking a job source should open a new tab, not replace the current tab.
- Browser Back should preserve job list/filter state.
- URL filters should round-trip through query params.
- A URL like `/?radarProfile=<profile-id>#radarSection` should load recommendations for that career direction.

Relevant APIs:

- `GET /api/jobs`
- `GET /api/stats`
- `GET /api/companies`
- `GET /api/recommendations`
- `POST /api/jobs/{job_id}/feedback`
- `GET/POST /api/profiles`
- `POST /api/profiles/parse-resume`
- `GET/POST/PATCH/DELETE /api/user/searches`
- `POST /api/user/request-company`

### Page: My Digest

File:

- `my_digest.html`

URL:

- `/my_digest.html`

Purpose:

- User setup center for resume-based career directions and digest runs.
- This page should make the primary action obvious: create/select a career direction, then view matches or run digest.

Visible Features:

- Resume setup:
  - Shows saved career directions.
  - Each saved direction appears as a chip, for example `Full stack`.
  - Direction chip includes `View matches`.
  - Clicking a direction chip should go to `/` with `radarProfile=<profile-id>` and show matching jobs.
  - Direction form includes:
    - Career direction name.
    - Minimum score.
    - Resume upload.
    - Resume text.
    - Target roles.
    - Core skills.
    - Target companies.
    - Preferred areas.
    - Acceptable areas.
    - Strict geography checkbox.
    - Exclusion keywords.
  - Supports up to five directions per user.
  - Saving a renamed direction should create a new direction until the user has five.
  - Only ask which direction to overwrite after the user already has five directions.
  - Main button: `Save Career Direction`.
  - Secondary button: `New direction`.

- Resume upload:
  - Supported file types: PDF, DOCX, TXT, MD.
  - Upload parses resume text into the text area.
  - Resume parser auto-suggests target roles, skills, geography, and exclusions when possible.
  - Resume and profile are saved in DB, not only browser local state.

- Run Once Now:
  - Temporary run controls:
    - Lookback days.
    - Max jobs.
    - Min score.
    - AI provider.
    - Mode: Send Email or Dry Run.
  - Button: `Run Digest Now`.
  - Should show matched jobs preview after running.
  - Console output is secondary diagnostic info, not the main result.

- AI Digest Schedule:
  - Optional collapsed section.
  - Configures scheduled AI-matched email frequency.
  - Button: `Update Schedule`.
  - This is not the same as saving a resume direction.

- Keyword Alert:
  - Optional collapsed section.
  - Simple keyword email alert independent of AI matching and API keys.
  - Button: `Update Keyword Alert`.
  - This is not the same as AI Digest and not the same as career direction.

- Saved Search Shortcuts:
  - Shows saved searches and keyword shortcuts.
  - Clicking a shortcut opens the Jobs page with filters applied.

- Run History:
  - Shows prior digest runs.

Behavior Rules:

- Avoid multiple primary save buttons on this page.
- `Save Career Direction` is the only primary save.
- Email schedule and keyword alert are optional settings and should stay visually weaker.
- Direction chips should feel like navigation to matching jobs, not just form editing.
- If a direction chip only loads a form, users will think it is broken.

Relevant APIs:

- `GET /api/profiles`
- `POST /api/profiles`
- `POST /api/profiles/parse-resume`
- `GET /api/recommendations`
- `POST /api/digest/run`
- `GET/POST /api/digest/settings`
- `GET /api/digest/log`
- `GET/POST /api/user/alert-settings`
- `GET /api/user/searches`

### Page: Favorites

File:

- `favorites.html`

URL:

- `/favorites.html`

Purpose:

- Let logged-in users track favorite companies and monitor company-specific job pages.

Visible Features:

- Favorite companies grid.
- Add favorite company form.
- Optional monitor URL for Big Tech or direct career pages.
- Monitor/check company button.
- Remove favorite.
- Collections summary.

Relevant APIs:

- `GET /api/user/favorites`
- `POST /api/user/favorites`
- `DELETE /api/user/favorites/{company_name}`
- `POST /api/user/favorites/{company_name}/check`
- `GET /api/collections`

### Page: Companies

File:

- `index.html`
- `js/main.js`

URL:

- `/?view=companies`

Purpose:

- Explore companies in the database and view jobs by company.

Visible Features:

- Company search.
- Company cards.
- Company detail modal.
- Company job list.

Relevant APIs:

- `GET /api/companies`
- `GET /api/companies/{company_name}/jobs`

### Page: Request Company

File:

- `index.html`
- `js/main.js`

URL:

- Main page nav section, available to logged-in users.

Purpose:

- Let users request a company to be added to the crawler.

Visible Features:

- Company name field.
- Optional careers page / ATS URL.
- Submit request.

Relevant APIs:

- `POST /api/user/request-company`
- Admin processing uses `GET /api/admin/company-requests` and `POST /api/admin/company-requests/{request_id}/process`.

### Page: My Searches

File:

- `index.html`
- `js/main.js`

URL:

- Modal opened from main nav.

Purpose:

- Save and reuse job search criteria.

Visible Features:

- Save current search.
- Name saved search.
- Optional daily email alerts.
- List saved searches.
- Load saved search.
- Delete saved search.
- Toggle alert.

Relevant APIs:

- `GET /api/user/searches`
- `POST /api/user/searches`
- `PATCH /api/user/searches/{search_id}`
- `DELETE /api/user/searches/{search_id}`

### Page: Feedback

Files:

- `feedback.html`
- Feedback modal in `index.html`

URLs:

- `/feedback.html`
- Main page feedback modal.

Purpose:

- Collect user feedback, bugs, and feature requests.

Relevant APIs:

- `POST /api/feedback`
- Admin list/delete uses `GET /api/admin/feedbacks`, `DELETE /api/admin/feedback/{feedback_id}`.

### Page: Admin Dashboard

Files:

- Admin section in `index.html`
- `admin_stats.html`

URLs:

- Admin section via main page nav for admin users.
- `/admin_stats.html`

Purpose:

- Admin-only operational view.

Visible Features:

- Feedback list.
- Feedback pagination.
- Delete feedback.
- Company request review.
- Visitor stats in `admin_stats.html`.

Relevant APIs:

- `GET /api/admin/feedbacks`
- `DELETE /api/admin/feedback/{feedback_id}`
- `GET /api/admin/company-requests`
- `POST /api/admin/company-requests/{request_id}/process`
- `GET /api/admin/visitor-stats`

### Page: Auth And Password Reset

Files:

- Auth modal in `index.html`.
- Login modal in `my_digest.html`.
- `reset-password.html`.

URLs:

- `/reset-password.html`

Purpose:

- Register, login, verify email, forgot password, reset password.

Relevant APIs:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/auth/verify-email`
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`

### Page: About

File:

- `about.html`

URL:

- `/about.html`

Purpose:

- Static product/about page.

## Data Model Cheat Sheet

Important MongoDB collections used by current features:

- `jobs`
  - Scraped job postings.
  - Queried by `/api/jobs` and recommendation engine.

- `companies`
  - Company metadata and ATS/career page info.
  - Queried by `/api/companies`.

- `users`
  - Auth accounts.

- `saved_searches`
  - User saved search filters and optional alerts.

- `career_profiles`
  - User-specific resume/career directions.
  - Core fields:
    - `user_email`
    - `name`
    - `target_roles`
    - `core_skills`
    - `target_companies`
    - `locations`
    - `geo_preferences.preferred_areas`
    - `geo_preferences.acceptable_areas`
    - `strict_location`
    - `exclusions`
    - `resume_text`
    - `resume_filename`
    - `resume_signals`
    - `min_score`
    - `is_default`

- `job_feedback`
  - Per-user feedback on recommended jobs.

- `digest_settings`
  - AI digest schedule settings.

- `digest_logs`
  - Personal digest run history.

- `user_alert_settings`
  - Keyword alert settings.

- `feedback`
  - Product feedback.

- `company_requests`
  - User requested companies.

- `visit_logs`
  - Visitor tracking/admin stats.

## Recommendation Logic

Recommendation API:

- `GET /api/recommendations`

Inputs:

- Authenticated user.
- Optional `profile` query param: profile id or profile name.
- `days`, `limit`, `min_score`.

Profile matching uses:

- Target roles.
- Core skills.
- Target companies.
- Resume signals.
- Exclusion keywords.
- Preferred areas and acceptable areas.
- Strict geography setting.
- User feedback.

Geography model:

- Preferred areas are strongest desired locations.
- Acceptable areas are allowed but less preferred.
- If `strict_location` is true, jobs outside preferred or acceptable areas should be filtered out.
- Examples:
  - Preferred: `New York, New Jersey, Seattle`
  - Acceptable: `Remote, United States, Japan, China`

## Resume Handling

Supported upload formats:

- PDF
- DOCX
- TXT
- MD

Backend parser:

- `POST /api/profiles/parse-resume`
- Uses `pypdf` for PDF.
- Uses `python-docx` for DOCX.
- Falls back to text decode for TXT/MD.

Storage rule:

- Resume text is stored in DB as part of `career_profiles.resume_text`.
- Do not store only in browser state.
- Current implementation stores text, not original binary file.

## Email Systems

There are three related but different concepts. Keep UI wording clear.

1. Career Direction
   - Saved resume/profile used for recommendations.
   - Main action: `Save Career Direction`.

2. AI Digest Schedule
   - Scheduled AI-matched email based on active/default career direction.
   - Optional action: `Update Schedule`.

3. Keyword Alert
   - Simple keyword-based email alert.
   - Does not use AI.
   - Optional action: `Update Keyword Alert`.

Do not call all three actions "Save". It confuses users.

## Design Rules For This Project

- Build the usable app, not a marketing landing page.
- Desktop pages should use available width.
- Do not push important content below many screens.
- Recommendations should be compact enough to scan.
- Users must always be able to browse all jobs, even if recommendations exist.
- Job cards/links should open in a new tab when going to external job pages.
- Make the primary action obvious on each page.
- Avoid multiple visually equal primary buttons on one screen.
- Use clear labels:
  - `Save Career Direction`
  - `View matches`
  - `Run Digest Now`
  - `Update Schedule`
  - `Update Keyword Alert`
- Do not make hidden behavior depend on undocumented clicks.
- If a chip is clickable, it should visibly do something meaningful.

## Feature Inventory For Manual Editing

Use this section to manually enable, remove, or rethink features.

### Keep As Core

- Main job board.
- Search/filter jobs.
- Saved searches.
- Login.
- Resume upload.
- Career directions.
- Personal Job Radar.
- Preferred/acceptable geography.
- New-tab job opening.
- My Digest run preview.

### Optional / Can Be Hidden

- AI Digest Schedule.
- Keyword Alert.
- Request Company.
- Feedback modal.
- Admin dashboard.
- Favorites company monitor.

### Potentially Confusing Areas

- `My Searches` and `Keyword Alert` overlap conceptually.
- `AI Digest Schedule` and `Run Digest Now` can be confused.
- Career direction chip must mean `View matches`, not just `load form`.
- There are two places to edit career profiles:
  - Full editor on `/my_digest.html`.
  - Compact inline editor on `/` Personal Job Radar.
  Decide later whether both should remain.

## Verification Checklist After Changes

Run these when touching core frontend/backend:

```bash
node --check js/main.js
python3 -m py_compile api/index.py scripts/personal_digest.py scripts/keyword_alert.py
```

Manual smoke tests:

- Open `/` logged out: general job board loads.
- Open `/` logged in: all jobs left, radar right.
- Click external job: opens new tab.
- Use Back after job modal/detail: job list state remains.
- Open `/my_digest.html`: saved career direction chips appear.
- Click a career direction chip: opens `/` and shows matches for that direction.
- Upload PDF resume: text parses and profile fields populate.
- Save Career Direction: chip appears and can be reused.
- Run Digest Now: matched jobs preview appears, not only console text.
- Update Schedule: only changes AI digest schedule.
- Update Keyword Alert: only changes keyword alert.
- Saved Search Shortcut: opens Jobs page with filters.

## Commands Often Used

Start local app:

```bash
source venv/bin/activate
python api/index.py
```

Run personal digest dry run:

```bash
python scripts/personal_digest.py --dry-run --days 7 --top 15 --min-score 5
```

Run keyword alert dry run:

```bash
python scripts/keyword_alert.py --dry-run
```

Run scraper:

```bash
python scripts/prod_scraper.py
```

Import/discover company lists:

```bash
python scripts/company_intake_pipeline.py data/companies_startups.yaml --dry-run --skip-discovery --limit 20
python scripts/company_intake_pipeline.py data/companies_startups.yaml data/companies_expansion_us_it.yaml --update-existing --scrape-now
python scripts/company_intake_pipeline.py data/neolabs_ai_startups.csv --update-existing --scrape-now
```

Company intake notes:

- YAML files with known `ats_type` are fastest to import.
- TXT or CSV files with only company names need ATS discovery.
- `--dry-run --skip-discovery` works offline and validates parsing.
- Real import needs MongoDB and network access.
- `--scrape-now` immediately tries to fetch jobs for newly imported or updated companies.
- Supported ATS scrapers: Greenhouse, Lever, Ashby, Workday, Workable, Wellfound, Breezy.
- Companies with unsupported/unknown ATS are inserted as inactive only if no supported ATS is discovered.
- Breezy boards may be valid but empty; keep them active if `ats_url` is a real `*.breezy.hr` board so future openings are picked up.
- Workday needs a concrete `ats_url` like `https://crowdstrike.wd5.myworkdayjobs.com/crowdstrikecareers`; generic `ats_type: workday` without that URL may not be enough.

## Notes For Future AI Agents

- Read this file before changing UX.
- If the user complains a button or chip "does nothing", treat it as a design bug, not user error.
- Preserve user data and DB schema compatibility.
- Do not hardcode one user's career interests into the app.
- Prefer improving clarity over adding another button.
- When adding a feature, update this SKILL.md under the correct page.
