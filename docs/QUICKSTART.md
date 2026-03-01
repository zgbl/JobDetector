# Quick Start Guide

## Prerequisites

Before you begin, make sure you have:

1. **Python 3.11+** installed
2. **MongoDB Atlas account** (free tier): https://www.mongodb.com/cloud/atlas/register
3. **Gmail account** for notifications

## Step-by-Step Setup

### Step 1: Set up MongoDB Atlas (5 minutes)

1. Go to https://www.mongodb.com/cloud/atlas/register
2. Create a free account
3. Create a new cluster (select Free tier - M0)
4. Click "Connect" → "Connect your application"
5. Copy the connection string, it looks like:
   ```
   mongodb+srv://username:<password>@cluster0.xxxxx.mongodb.net/
   ```
6. Replace `<password>` with your actual password

### Step 2: Set up Gmail App Password (3 minutes)

1. Go to https://myaccount.google.com/apppasswords
2. You may need to enable 2-factor authentication first
3. Create a new app password
4. Copy the 16-character password (looks like: `abcd efgh ijkl mnop`)

### Step 3: Install Dependencies

```bash
cd /Users/tuxy/Codes/TestProjects/JobDetector

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # Mac/Linux

# Install packages
pip install -r requirements.txt
```

### Step 4: Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit .env file
nano .env  # or use any text editor
```

Fill in these values:
```bash
MONGODB_URI=mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/
MONGODB_DATABASE=jobdetector
EMAIL_USERNAME=your_email@gmail.com
EMAIL_APP_PASSWORD=abcdefghijklmnop  # 16-char password, no spaces
```

Save and exit.

### Step 5: Initialize Database

```bash
# Create collections and indexes
python scripts/init_database.py
```

You should see:
```
✅ Created collection: companies
✅ Created collection: jobs
...
✅ Database initialization completed successfully!
```

### Step 6: Import Companies

```bash
# Import 50 tech companies
python scripts/import_companies.py
```

You should see:
```
✅ Imported: Google
✅ Imported: Meta
...
📊 Total companies in database: 50
```

### Step 7: Verify Setup

```bash
# Test connection
python scripts/test_connection.py
```

You should see:
```
✅ Database connection successful
📋 Collections: ['companies', 'jobs', ...]
📊 Companies in database: 50
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'pymongo'"
```bash
# Make sure virtual environment is activated
source venv/bin/activate
pip install -r requirements.txt
```

### "ValueError: MONGODB_URI environment variable is not set"
```bash
# Make sure .env file exists and is properly configured
cat .env  # Check contents
```

### "Authentication failed" (MongoDB)
- Double-check your MongoDB connection string
- Make sure you replaced `<password>` with your actual password
- Verify IP address is whitelisted in MongoDB Atlas (use 0.0.0.0/0 for testing)

### Gmail app password not working
- Make sure you're using the app password, NOT your regular Gmail password
- Remove any spaces from the 16-character password
- Make sure 2FA is enabled on your Google account

## Next Steps

Once setup is complete, you're ready to:

1. Configure your job preferences in `config/config.yaml`
2. Run the scrapers (Phase 2 development)
3. Test job matching and notifications

## Useful Commands

```bash
# Show company statistics
python scripts/import_companies.py --stats

# Update existing companies
python scripts/import_companies.py --update

# Reset database (WARNING: deletes all data)
python scripts/reset_database.py

# Run tests (when available)
pytest tests/
```

---

Need help? Check the main README.md or create an issue on GitHub.
