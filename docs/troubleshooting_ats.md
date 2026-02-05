# Troubleshooting Guide: Why are there 0 Jobs for some companies?

This document serves as a guide for developers and users when encountering companies that display **0 Active Jobs** in the JobDetector dashboard.

## Root Cause: The "Custom" ATS Status

The primary reason a company shows 0 jobs is that it is marked with `ats_type: custom` in our database. 

Current JobDetector scraping architecture is built on **Standardized Scrapers**. We currently support:
1.  **Greenhouse** (`ats_type: greenhouse`)
2.  **Lever** (`ats_type: lever`)
3.  **Workday** (`ats_type: workday`)

### Why Big Tech (Google, Amazon, etc.) are "Custom"
Large enterprises often build their own proprietary recruitment platforms. These "Custom" platforms:
- Do not provide standardized public JSON APIs.
- Often use complex, single-page applications (SPA) or RPC-based data fetching (e.g., Google's `batchexecute`).
- Are not yet implemented in our `src/scrapers/` directory.

---

## Known "Custom" Companies

| Company | Domain | Reason for 0 Jobs |
| :--- | :--- | :--- |
| **Google** | google.com | Uses proprietary Google Careers platform (RPC based). |
| **Microsoft** | microsoft.com | Uses custom LinkedIn-integrated platform. |
| **Amazon** | amazon.com | Uses Amazon.jobs (proprietary). |
| **Apple** | apple.com | Uses Apple Jobs (proprietary). |
| **Netflix** | netflix.com | Uses Greenhouse (needs specialized sub-domain mapping). |

---

## How to Check a Company's Status

1.  **Check Data Files**: Look at `data/companies_initial.yaml` or other YAML files for the `ats_type` field.
2.  **Query Database**:
    ```bash
    # Example using MongoDB shell
    db.companies.find({name: "Google"}, {ats_system: 1})
    ```
3.  **Check Scraper Logs**: Check `logs/scraper_prod.log`. You will likely see:
    `WARNING - ProdScraper - 跳过 Google: 尚未实现 'custom' 的抓取器`

---

## Future Roadmap: Supporting "Custom" Companies

To fix the "0 jobs" issue for a specific company, we follow these steps:

1.  **Reverse Engineering**: Use the Browser tool/Subagent to identify the data source (API endpoint or DOM structure).
2.  **Scraper Implementation**: Create a dedicated scraper in `src/scrapers/[company_name].py` inheriting from `BaseScraper`.
3.  **Update Database**: Change the company's `ats_type` from `custom` to the new dedicated type.
4.  **Register Scraper**: Add the new scraper instance to `scripts/prod_scraper.py`.

---

## How to use this guide
Keep this file in the `docs/` folder of your project to help triage data gaps as we add more companies.
