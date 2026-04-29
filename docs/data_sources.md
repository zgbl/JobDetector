# Data Sources Summary

This document summarizes the current data sources, scrapers, and company lists used by JobDetector.

## Scrapers (ATS Systems)

The project currently supports direct crawling from several major Applicant Tracking Systems (ATS). The scrapers are located in `src/scrapers/`.

| ATS System | Scraper File | Status |
|------------|--------------|--------|
| **Greenhouse** | [greenhouse.py](file:///Users/tuxy/Codes/Github2/JobDetector/src/scrapers/greenhouse.py) | ✅ Supported |
| **Lever** | [lever.py](file:///Users/tuxy/Codes/Github2/JobDetector/src/scrapers/lever.py) | ✅ Supported |
| **Workday** | [workday.py](file:///Users/tuxy/Codes/Github2/JobDetector/src/scrapers/workday.py) | ✅ Supported |
| **Ashby** | [ashby.py](file:///Users/tuxy/Codes/Github2/JobDetector/src/scrapers/ashby.py) | ✅ Supported |
| **Workable** | [workable.py](file:///Users/tuxy/Codes/Github2/JobDetector/src/scrapers/workable.py) | ✅ Supported |
| **Wellfound** | [wellfound.py](file:///Users/tuxy/Codes/Github2/JobDetector/src/scrapers/wellfound.py) | ✅ Supported |

## Company Lists (Crawl List)

Company lists are stored as YAML files in the `data/` directory. These are imported into the database to guide the scrapers.

| List Name | File Path | Description |
|-----------|-----------|-------------|
| **Initial List** | [companies_initial.yaml](file:///Users/tuxy/Codes/Github2/JobDetector/data/companies_initial.yaml) | Seed list of companies. |
| **Japan Companies** | [companies_japan.yaml](file:///Users/tuxy/Codes/Github2/JobDetector/data/companies_japan.yaml) | Companies operating in Japan. |
| **Startups** | [companies_startups.yaml](file:///Users/tuxy/Codes/Github2/JobDetector/data/companies_startups.yaml) | Various startup companies. |
| **Medium Companies** | [companies_medium.yaml](file:///Users/tuxy/Codes/Github2/JobDetector/data/companies_medium.yaml) | Mid-sized companies. |
| **US IT Expansion** | [companies_expansion_us_it.yaml](file:///Users/tuxy/Codes/Github2/JobDetector/data/companies_expansion_us_it.yaml) | Larger list of US IT companies. |

## Pending / Potential Sources

- **Crew List**: "TECH CREW" is currently in `companies_japan.yaml` but is skipped due to missing ATS configuration.

## Data Flow

1. **Import**: `scripts/import_companies.py` reads YAML files and populates the MongoDB `companies` collection.
2. **Crawl**: `scripts/prod_scraper.py` iterates through active companies, detects their ATS, and uses the appropriate scraper.
3. **Filter**: `src/services/language_filter.py` filters jobs to ensure they are English-only and IT-related.
4. **Store**: Jobs are stored in the MongoDB `jobs` collection.
