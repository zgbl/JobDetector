# JobDetector MVP

Automated job scraping and notification system that monitors company career websites directly.

## Features

- 🎯 Direct scraping from 50+ tech companies' career websites
- 🤖 Automatic detection of ATS systems (Greenhouse, Lever, Workday)
- 🔍 Intelligent job matching based on skills, location, and salary
- 📧 Email notifications for matching jobs
- 🗄️ MongoDB storage with efficient indexing
- ⏰ Automated scheduling with APScheduler
- 🧭 **源头校验层 (New)**: ask the employer's own ATS whether a posting is still live
- 🧩 **Chrome 插件 (New)**: annotate Indeed / LinkedIn with 🟢 源头在招 / ⚠️ 源头已关闭
- 👻 **反 Ghost Job (New)**: rule engine + LLM scoring for stale / agency-scraped listings

## 反 Ghost Job / 源头校验（对外能力）

| 能力 | 入口 | 文档 |
| --- | --- | --- |
| 校验岗位在源头 ATS 是否还在招（10 家 ATS + 兜底页探测） | `POST /api/verify/source`、`GET /api/verify/source` | [docs/SOURCE_VERIFICATION.md](docs/SOURCE_VERIFICATION.md) |
| 只有公司名+职位名也能定位岗位（查自家库 + 实时 board 模糊匹配） | `POST /api/verify/lookup` | 同上 |
| Ghost Job 风险评分（规则引擎 → LLM 降级链） | `POST /api/ghost/analyze` | [docs/GHOST_JOB_DETECTION.md](docs/GHOST_JOB_DETECTION.md) |
| 浏览器实时标注插件 | `extension/` | [extension/README.md](extension/README.md) |
| 批量复检、把已失效岗位下线 | `scripts/verify_active_jobs.py` | [docs/SOURCE_VERIFICATION.md](docs/SOURCE_VERIFICATION.md) §6 |

```bash
# 校验一条岗位（插件用的就是它）
curl -X POST https://jobdetector.blackrice.top/api/verify/source \
  -H 'Content-Type: application/json' \
  -d '{"urls":["https://job-boards.greenhouse.io/stripe/jobs/999999999"],
       "company":"Stripe","title":"Abuse Investigator"}'

# 批量复检：源头关掉的岗位自动 is_active=false
python scripts/verify_active_jobs.py --limit 200 --dry-run

# 本地引擎体检（打真实 ATS 接口）
python scripts/verify_source_smoke.py
pytest tests/ -q
```

## Tech Stack

- **Backend**: Python 3.11+
- **Database**: MongoDB Atlas (free tier)
- **Web Automation**: Playwright
- **Task Scheduling**: APScheduler
- **Data Validation**: Pydantic (via dataclasses)

## Project Structure

```
JobDetector/
├── src/
│   ├── database/           # Database connection and models
│   ├── scrapers/           # Company-specific scrapers
│   ├── matcher/            # Job matching engine
│   ├── notifier/           # Email notification
│   └── scheduler/          # Task scheduling
├── scripts/                # Utility scripts
│   ├── init_database.py    # Initialize database
│   ├── import_companies.py # Import company list
│   └── test_connection.py  # Test database connection
├── data/                   # Data files
│   └── companies_initial.yaml
├── config/                 # Configuration files
├── tests/                  # Unit tests
└── logs/                   # Log files
```

## Quick Start

### 1. Prerequisites

- Python 3.11 or higher
- MongoDB Atlas account (free tier)
- Gmail account (for notifications)

### 2. Installation

```bash
# Clone the repository
cd /Users/tuxy/Codes/Github2/JobDetector

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env and fill in your credentials:
# - MONGODB_URI: Your MongoDB Atlas connection string
# - EMAIL_USERNAME: Your Gmail address
# - EMAIL_APP_PASSWORD: Gmail app password
```

To get a Gmail app password:
1. Go to https://myaccount.google.com/apppasswords
2. Create a new app password
3. Copy the 16-character password to .env

### 4. Database Setup

```bash
# Initialize database (creates collections and indexes)
python scripts/init_database.py

# Import 50 tech companies
python scripts/import_companies.py

# Verify setup
python scripts/test_connection.py
```

### 5. Run

```bash
# Start the job detector
python src/main.py
```

For more detailed setup and development information, see:
- [Quick Start Guide](file:///Users/tuxy/Codes/Github2/JobDetector/docs/QUICKSTART.md)
- [Development Guide](file:///Users/tuxy/Codes/Github2/JobDetector/docs/DEVELOPMENT.md)
- [Database Setup](file:///Users/tuxy/Codes/Github2/JobDetector/docs/DATABASE_SETUP.md)
- [Data Sources Summary](file:///Users/tuxy/Codes/Github2/JobDetector/docs/data_sources.md)

## Usage

### Smart Ingestion Pipeline (AI-Powered)

For unstructured company lists (text files, messy lists), use the Intelligent Ingestion Pipeline:

```bash
# Run the pipeline with AI extraction and ATS discovery
python scripts/ingestion_pipeline.py data/ImportList/YourList.txt
```

> [!NOTE]
> Requires `AI_PROVIDER` and `API_KEY` to be set in `.env`. See [docs/component_ingestion.md](file:///Users/tuxy/Codes/Github2/JobDetector/docs/component_ingestion.md) and [docs/data_sources.md](file:///Users/tuxy/Codes/Github2/JobDetector/docs/data_sources.md) for details.

### Traditional Import

# Import from custom file
python scripts/import_companies.py --file data/my_companies.yaml

# Update existing companies
python scripts/import_companies.py --update

# Show statistics only
python scripts/import_companies.py --stats
```

### Database Management

```bash
# Reset database (WARNING: deletes all data)
python scripts/reset_database.py

# Test connection
python scripts/test_connection.py
```

## Development Roadmap

### Phase 1: Foundation (Week 1) ✅
- [x] Project structure
- [x] Database initialization
- [x] Company import system
- [ ] Configuration management

### Phase 2: Scrapers (Week 2)
- [ ] Greenhouse scraper
- [ ] Lever scraper
- [ ] ATS detection
- [ ] Data validation

### Phase 3: Matching & Notification (Week 3)
- [ ] Job matching engine
- [ ] Email notifications
- [ ] Task scheduler
- [ ] End-to-end testing

## Configuration

Edit `config/config.yaml` to customize:

- User preferences (keywords, locations, salary)
- Scraping schedule
- Notification settings

## Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=src tests/
```

## Contributing

This is currently a personal project for MVP development.

## License

MIT

## Contact

For questions or suggestions, please open an issue.

---

**Status**: 🚧 In Development (Scrapers Phase)  
**Last Updated**: 2026-09-17

