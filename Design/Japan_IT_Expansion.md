# Design: Japan IT Market Expansion ("The English Oasis")

## 1. Objective
To provide a curated, high-signal job feed for professionals in Japan (or looking to move) who want to work in English-speaking environments in the IT/Tech sector.

## 2. Targeted Filtering Mechanism

### A. Language Filter (The "No-Japanese" Sieve)
We only accept roles that do not mandate Japanese fluency.
- **Positive Signals**: "English-only environment", "No Japanese required", "Global team".
- **Hard Rejections**: "JLPT N1/N2", "Business Japanese", "Native Japanese", "日本語必須".

### B. Role Filter (The "IT-Only" Mask)
Since many targeted companies (Rakuten, SoftBank) are conglomerates, we must filter out non-tech roles.
- **Accepted Categories**:
    - Engineering (Software, Frontend, Backend, Fullstack, Mobile, Embedded, QA).
    - Data (Data Science, Data Engineering, ML, AI).
    - Infrastructure (DevOps, SRE, Cloud Engine, Security).
    - Product (Product Manager, UX Designer, UI Designer, Solutions Architect).
- **Rejected Categories**:
    - Sales, Marketing, Customer Support.
    - HR, Recruiting, Finance, Legal.
    - Administrative, Logistics.

## 3. Persistent Rejection Mechanism
To handle the "Long Tail" of jobs without re-processing them every session:
1. **Content Hash**: Every job parsed generates a `content_hash`.
2. **Rejected Collection**: Jobs that fail the language or role filter are stored in `rejected_jobs` (hash + metadata).
3. **Short-Circuit**: The production scraper checks the `rejected_jobs` collection before running any heavy analysis on a new job title/short description.

## 4. Automation Strategy
- **Seed Data**: `data/companies_japan.yaml` (100+ entries).
- **Discovery**: Use `ATSDiscoveryService` to automatically find the career boards.
- **Schedules**: GitHub Actions cron (every 6 hours).
- **Frontend**: A dedicated "Japan IT" shortcut on the My Favorites page for quick access.
