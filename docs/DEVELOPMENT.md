# Local Development Guide

## Prerequisites

- Python 3.12+
- MongoDB Atlas URI (set in `.env`)
- Gmail App Password (set in `.env`)

---

## 1. Environment Setup (First Time)

```bash
cd /Users/tuxy/Codes/Github2/JobDetector

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 2. Configure `.env`

Copy and fill in the template:

```bash
cp .env.example .env
```

Minimum required keys:

```bash
MONGODB_URI=mongodb+srv://...
MONGODB_DATABASE=jobdetector
EMAIL_USERNAME=your@gmail.com
EMAIL_APP_PASSWORD=your_app_password
ADMIN_EMAIL=your@gmail.com
BASE_URL=http://localhost:8123

# For personal digest (optional)
RECIPIENT_EMAIL=your@gmail.com
GEMINI_API_KEY=your_gemini_key
AI_PROVIDER=gemini
```

---

## 3. Start the Dev Server

```bash
# Activate venv first if not already active
source venv/bin/activate

# Start FastAPI server
python api/index.py
```

The server starts on:

**URL: http://localhost:8123**

> [!IMPORTANT]
> Always use port **8123** for local testing. Do NOT use port 3000.

---

## 4. Key Pages

| Page | URL |
|------|-----|
| Job Dashboard | http://localhost:8123/ |
| Favorites | http://localhost:8123/favorites.html |
| My Career Digest | http://localhost:8123/my_digest.html |
| Admin Stats | http://localhost:8123/admin_stats.html |
| API Health | http://localhost:8123/api/health |

---

## 5. Running Scripts Manually

```bash
# Activate venv first
source venv/bin/activate

# Import companies into DB
python scripts/import_companies.py

# Run job scraper
python scripts/prod_scraper.py

# Send user job alerts
python scripts/send_alerts.py

# Run personal AI digest (dry run = preview, no email)
python scripts/personal_digest.py --dry-run

# Run personal AI digest (sends email)
python scripts/personal_digest.py --days 1 --top 15
```

---

## 6. Stopping the Server

Press `Ctrl + C` in the terminal where the server is running.

To deactivate the venv:

```bash
deactivate
```
