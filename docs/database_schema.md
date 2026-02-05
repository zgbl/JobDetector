# JobDetector Database Schema

## Overview
The application uses **MongoDB** (`JobDetector` database) for storage.
Collections are created lazily, meaning `saved_searches` will only appear **after** the first successful save operation.

---

## Collections

### 1. `saved_searches` (User Customization)
Stores user-defined search criteria and alert preferences.
- **_id**: ObjectId
- **user_email**: `String` (Link to `users` collection)
- **name**: `String` (User-friendly name, e.g., "Remote Python")
- **email_alert**: `Boolean` (True = Send daily emails)
- **last_emailed_at**: `DateTime` (Timestamp of last alert sent)
- **criteria**: `Object` (The active filters)
    - `q`: Search keyword
    - `location`: Location string
    - `category`: Job category (Engineering, Product, etc.)
    - `job_type`: Full-time, Contract, etc.
    - `remote_type`: Remote, Hybrid, On-site

### 2. `users`
Stores user authentication and profile data.
- **_id**: ObjectId
- **email**: `String` (Unique Index)
- **hashed_password**: `String` (Bcrypt hash)
- **full_name**: `String`
- **created_at**: `DateTime`

### 3. `jobs`
Stores job postings scraped from various sources.
- **_id**: ObjectId
- **title**: `String`
- **company**: `String`
- **location**: `String`
- **posted_date**: `DateTime`
- **source_url**: `String` (Direct link to application)
- **description**: `String` (Full HTML/Text)
- **content_hash**: `String` (For duplicate detection)
- **is_active**: `Boolean`

### 4. `companies`
Stores metadata about tracked companies.
- **_id**: ObjectId
- **name**: `String`
- **domain**: `String`
- **careers_url**: `String`
- **ats_system**: `Object`
    - `type`: greenhouse, lever, workday
- **metadata**: `Object`
    - `size`: Startup, Mid-size, Large Enterprise
    - `industry`: String
