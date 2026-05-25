import os
import sys
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, File, Request, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv
import re
import secrets
from bson import ObjectId

from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Add project root to path for database connection and models
project_root_path = Path(__file__).parent.parent
project_root = str(project_root_path)
sys.path.insert(0, project_root)

from api.db import get_db
from api.email_service import get_email_service
try:
    from api.auth_utils import (
        get_password_hash,
        verify_password,
        create_access_token,
        decode_access_token
    )
except ImportError:
    from auth_utils import (
        create_access_token, 
        decode_access_token
    )

from src.database.models import Company, ATSSystem, CompanyMetadata
from datetime import datetime, timedelta, timezone

load_dotenv(dotenv_path=project_root_path / ".env")

app = FastAPI(title="JobDetector Dashboard")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve index.html at root
# Simple Rate Limiting State (In-memory, reset on server restart)
rate_limit_store = {}

async def check_rate_limit(request: Request, limit: int = 5, window: int = 60):
    """Simple IP-based rate limiting"""
    client_ip = request.client.host
    now = datetime.now()
    
    if client_ip not in rate_limit_store:
        rate_limit_store[client_ip] = []
        
    # Clean old requests
    rate_limit_store[client_ip] = [t for t in rate_limit_store[client_ip] if now - t < timedelta(seconds=window)]
    
    if len(rate_limit_store[client_ip]) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    
    rate_limit_store[client_ip].append(now)

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_file = project_root_path / "index.html"
    if index_file.exists():
        return index_file.read_text()
    return "<h1>Index.html not found at root</h1>"

@app.get("/favicon.ico")
async def favicon():
    """Serve the local SVG favicon through the classic favicon path."""
    from fastapi.responses import Response
    favicon_file = project_root_path / "assets" / "favicon.svg"
    if favicon_file.exists():
        return Response(content=favicon_file.read_text(), media_type="image/svg+xml")
    return Response(status_code=204)

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_json():
    """Silence Chrome DevTools internal requests"""
    from fastapi.responses import Response
    return Response(status_code=204)

@app.get("/favorites.html", response_class=HTMLResponse)
async def read_favorites():
    favorites_file = project_root_path / "favorites.html"
    if favorites_file.exists():
        return favorites_file.read_text()
    return "<h1>Page not found</h1>"

@app.get("/reset-password.html", response_class=HTMLResponse)
async def read_reset_password():
    reset_file = project_root_path / "reset-password.html"
    if reset_file.exists():
        return reset_file.read_text()
    return "<h1>Page not found</h1>"

@app.get("/feedback.html", response_class=HTMLResponse)
async def read_feedback():
    feedback_file = project_root_path / "feedback.html"
    if feedback_file.exists():
        return feedback_file.read_text()
    return "<h1>Page not found</h1>"

@app.get("/admin_stats.html", response_class=HTMLResponse)
async def read_admin_stats():
    admin_file = project_root_path / "admin_stats.html"
    if admin_file.exists():
        return admin_file.read_text()
    return "<h1>Admin Page not found</h1>"

@app.get("/about.html", response_class=HTMLResponse)
async def read_about():
    about_file = project_root_path / "about.html"
    if about_file.exists():
        return about_file.read_text()
    return "<h1>Page not found</h1>"



@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "JobDetector API is running"}

# Mount static folders if they exist
# Mount static folders if they exist
css_path = project_root_path / "css"
js_path = project_root_path / "js"
assets_path = project_root_path / "assets"

if css_path.exists():
    app.mount("/css", StaticFiles(directory=str(css_path)), name="css")
else:
    print(f"WARNING: CSS path not found at {css_path}")

if js_path.exists():
    app.mount("/js", StaticFiles(directory=str(js_path)), name="js")
else:
    print(f"WARNING: JS path not found at {js_path}")

if assets_path.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")
else:
    print(f"WARNING: assets path not found at {assets_path}")

@app.get("/api/jobs")
async def get_jobs(
    q: Optional[str] = None,
    company: Optional[str] = None,
    job_type: Optional[str] = None,
    remote_type: Optional[str] = None,
    locations: Optional[List[str]] = Query(None),
    location: Optional[str] = None,
    category: Optional[str] = None,
    days: Optional[int] = None,
    companies: Optional[List[str]] = Query(None),
    skip: int = 0,
    limit: int = 100
):
    """Fetch jobs with search and filtering"""
    db = get_db()
    
    query = {"is_active": True}
    and_conditions = []
    
    if q:
        # Support multi-keyword search (AND logic)
        terms = q.strip().split()
        for term in terms:
            escaped_term = re.escape(term)
            and_conditions.append({
                "$or": [
                    {"title": {"$regex": escaped_term, "$options": "i"}},
                    {"company": {"$regex": escaped_term, "$options": "i"}},
                    {"description": {"$regex": escaped_term, "$options": "i"}},
                    {"skills": {"$in": [re.compile(escaped_term, re.I)]}}
                ]
            })
    
    if company:
        query["company"] = company
        
    if companies:
        query["company"] = {"$in": companies}
    
    if job_type:
        query["job_type"] = job_type
        
    if remote_type:
        query["remote_type"] = remote_type

    # Multi-location logic
    effective_locations = locations or ([location] if location else [])
    if effective_locations:
        location_conditions = []
        country_map = {
            "usa": "United States|USA|U.S.",
            "japan": "Japan|Tokyo|Osaka|Kyoto",
            "china": "China|Shanghai|Beijing|Shenzhen",
            "uk": "United Kingdom|UK|London",
            "germany": "Germany|Berlin|Munich",
            "france": "France|Paris",
        }
        
        for loc in effective_locations:
            if not loc: continue
            
            if loc.lower() == "remote":
                location_conditions.append({
                    "$or": [
                        {"location": {"$regex": "remote", "$options": "i"}},
                        {"remote_type": "Remote"}
                    ]
                })
            else:
                search_val = country_map.get(loc.lower(), loc)
                location_conditions.append({
                    "$or": [
                        {"location": {"$regex": search_val, "$options": "i"}},
                        {"company_location": {"$regex": search_val, "$options": "i"}}
                    ]
                })
        
        if location_conditions:
            if len(location_conditions) == 1:
                and_conditions.append(location_conditions[0])
            else:
                and_conditions.append({"$or": location_conditions})

    if category:
        # Map common categories to keywords
        category_map = {
            "Engineering": ["engineer", "developer", "software", "tech", "backend", "frontend", "fullstack", "infrastructure"],
            "Product": ["product manager", "pm", "product owner"],
            "Design": ["design", "ux", "ui", "product designer"],
            "Marketing": ["marketing", "growth", "seo", "brand"],
            "Sales": ["sales", "account executive", "ae", "business development"],
            "Finance": ["finance", "accounting", "tax", "treasury"],
            "Legal": ["legal", "law", "counsel", "compliance"],
            "Finance": ["finance", "accounting", "tax", "treasury"],
            "Legal": ["legal", "law", "counsel", "compliance"],
            "People": ["people", "hr", "recruiting", "talent"],
            "AI": [
                "ai engineer", "artificial intelligence", "machine learning", "deep learning", 
                "computer vision", "nlp", "natural language", "llm", "generative ai", 
                "gpt", "ai architect", "ml engineer", "ml ops", "mlops",
                r"\bml\b", r"\bai\b"
            ]
        }
        
        keywords = category_map.get(category)
        if keywords:
            category_regex = "|".join(keywords)
            and_conditions.append({
                "$or": [
                    {"title": {"$regex": category_regex, "$options": "i"}},
                    {"skills": {"$in": [re.compile(category_regex, re.I)]}}
                ]
            })

    if days:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        query["posted_date"] = {"$gte": cutoff}

    if and_conditions:
        query["$and"] = and_conditions

    print(f"DEBUG QUERY: {query}")

    try:
        # 1. Get total matching count (without limit)
        total_count = db.jobs.count_documents(query)
        
        # 2. Get jobs sorted by date (newest first) with pagination
        jobs = list(db.jobs.find(query).sort("posted_date", -1).skip(skip).limit(limit))
        
        # Format for API (handle ObjectId and datetime)
        for job in jobs:
            job["_id"] = str(job["_id"])
            if job.get("posted_date"):
                job["posted_date"] = job["posted_date"].isoformat() if hasattr(job["posted_date"], "isoformat") else str(job["posted_date"])
            if job.get("scraped_at"):
                job["scraped_at"] = job["scraped_at"].isoformat() if hasattr(job["scraped_at"], "isoformat") else str(job["scraped_at"])
                
        return {
            "jobs": jobs,
            "total": total_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/companies")
async def get_companies(q: Optional[str] = None):
    """Fetch all companies with search"""
    db = get_db()
    query = {}
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    
    try:
        # Fetch all companies (MongoDB sort on nested fields can be unreliable)
        companies = list(db.companies.find(query))
        
        # Sort in Python: first by active_jobs descending, then by name ascending
        companies.sort(key=lambda c: (-c.get('stats', {}).get('active_jobs', 0), c.get('name', '')))
        
        for comp in companies:
            comp["_id"] = str(comp["_id"])
            # Ensure metadata and stats exist
            if not comp.get("metadata"):
                comp["metadata"] = {}
            if not comp.get("stats"):
                comp["stats"] = {"active_jobs": 0, "total_jobs_found": 0}
        return companies
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/companies/{company_name}/jobs")
async def get_company_jobs(company_name: str):
    """Fetch jobs for a specific company"""
    db = get_db()
    try:
        jobs = list(db.jobs.find({"company": company_name, "is_active": True}).sort("posted_date", -1))
        for job in jobs:
            job["_id"] = str(job["_id"])
            if job.get("posted_date"):
                job["posted_date"] = job["posted_date"].isoformat() if hasattr(job["posted_date"], "isoformat") else str(job["posted_date"])
        return jobs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Authentication Endpoints ---

@app.post("/api/auth/register")
async def register(request: Request):
    """Register a new user (Rate limited)"""
    await check_rate_limit(request, limit=3, window=300) # Max 3 per 5 mins
    data = await request.json()
    email = data.get("email")
    password = data.get("password")
    full_name = data.get("full_name")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    db = get_db()
    # Check if user exists
    if db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    # Generate verification token
    verification_token = secrets.token_urlsafe(32)
    verification_expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24)

    user_doc = {
        "email": email,
        "hashed_password": get_password_hash(password),
        "full_name": full_name or email.split("@")[0],
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "is_active": True,
        "is_verified": False,
        "verification_token": verification_token,
        "verification_token_expires": verification_expires
    }
    
    db.users.insert_one(user_doc)
    
    # Send verification email
    base_url = os.getenv("BASE_URL", "http://localhost:8123")
    email_service = get_email_service()
    email_sent = email_service.send_verification_email(email, verification_token, base_url)
    
    if not email_sent:
        # Log warning but don't fail registration
        print(f"Warning: Failed to send verification email to {email}")
    
    return {"message": "Registration successful! Please check your email to verify your account."}

@app.post("/api/auth/login")
async def login(request: Request):
    """Login and get token (Rate limited)"""
    await check_rate_limit(request, limit=10, window=60)
    data = await request.json()
    email = data.get("email")
    password = data.get("password")

    db = get_db()
    user = db.users.find_one({"email": email})
    
    if not user or not verify_password(password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Check if email is verified
    if not user.get("is_verified", False):
        raise HTTPException(status_code=403, detail="Please verify your email before logging in. Check your inbox for the verification link.")

    access_token = create_access_token(data={"sub": user["email"]})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": {
            "email": user["email"],
            "full_name": user.get("full_name")
        }
    }

@app.get("/api/auth/verify-email")
async def verify_email(token: str = Query(...)):
    """Verify user email with token"""
    db = get_db()
    
    # Find user with this verification token
    user = db.users.find_one({"verification_token": token})
    
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    
    # Check if token is expired
    if user.get("verification_token_expires") and user["verification_token_expires"] < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Verification token has expired. Please request a new one.")
    
    # Update user as verified
    db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"is_verified": True},
            "$unset": {"verification_token": "", "verification_token_expires": ""}
        }
    )
    
    # Redirect to login page with success message
    return RedirectResponse(url="/?verified=true", status_code=302)

@app.post("/api/auth/forgot-password")
async def forgot_password(request: Request):
    """Initiate password reset (Rate limited)"""
    await check_rate_limit(request, limit=3, window=600) # Max 3 per 10 mins
    """Send password reset email"""
    print("\n--- Forgot Password Request Received ---")
    data = await request.json()
    email = data.get("email")
    print(f"Target Email: {email}")
    
    if not email:
        print("Error: No email provided in request")
        raise HTTPException(status_code=400, detail="Email required")
    
    db = get_db()
    user = db.users.find_one({"email": email})
    
    # Don't reveal if email exists or not (security best practice)
    if not user:
        print(f"Security Notice: Email '{email}' not found in DB. Returning generic success.")
        return {"message": "If an account with that email exists, a password reset link has been sent."}
    
    print(f"User found for '{email}'. Generating reset token...")
    # Generate reset token
    reset_token = secrets.token_urlsafe(32)
    reset_expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    
    # Save reset token
    print("Saving reset token to DB...")
    db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "reset_token": reset_token,
                "reset_token_expires": reset_expires
            }
        }
    )
    
    # Send reset email
    base_url = os.getenv("BASE_URL", "http://localhost:8123")
    email_service = get_email_service()
    print(f"Attempting to send reset email to {email} via {email_service.smtp_server}...")
    email_sent = email_service.send_password_reset_email(email, reset_token, base_url)
    
    if not email_sent:
        print(f"❌ ERROR: Failed to send password reset email to {email}")
    else:
        print(f"✅ SUCCESS: Password reset email sent to {email}")
    
    print("--- Request Finished ---\n")
    return {"message": "If an account with that email exists, a password reset link has been sent."}

@app.post("/api/auth/reset-password")
async def reset_password(request: Request):
    """Reset password with token"""
    data = await request.json()
    token = data.get("token")
    new_password = data.get("password")
    
    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and new password required")
    
    db = get_db()
    
    # Find user with this reset token
    user = db.users.find_one({"reset_token": token})
    
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    # Check if token is expired
    if user.get("reset_token_expires") and user["reset_token_expires"] < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Reset token has expired. Please request a new one.")
    
    # Update password and remove reset token
    db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"hashed_password": get_password_hash(new_password)},
            "$unset": {"reset_token": "", "reset_token_expires": ""}
        }
    )
    
    return {"message": "Password reset successful. You can now log in with your new password."}

@app.get("/api/auth/me")
async def get_me(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    db = get_db()
    user = db.users.find_one({"email": email})
    
    if not user:
        # User might have been deleted
        raise HTTPException(status_code=401, detail="User not found")
    
    # Admin check
    admin_email = os.getenv("ADMIN_EMAIL")
    is_admin = (admin_email and email.lower() == admin_email.lower()) or user.get("is_admin", False)
    
    print(f"DEBUG: Checking admin for {email}. Configured ADMIN_EMAIL: {admin_email}. Result: {is_admin}")
    
    return {
        "email": user["email"],
        "full_name": user.get("full_name"),
        "is_admin": is_admin,
        "created_at": user["created_at"].isoformat() if hasattr(user.get("created_at"), "isoformat") else str(user.get("created_at", ""))
    }

# --- Saved Search Endpoints ---

@app.get("/api/user/searches")
async def get_saved_searches(request: Request):
    """Get all saved searches for the current user"""
    # specific auth check to get user email
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    email = payload.get("sub")
    db = get_db()
    
    searches = list(db.saved_searches.find({"user_email": email}))
    for s in searches:
        s["id"] = str(s["_id"])
        del s["_id"]
        # Ensure dates are strings
        if s.get("created_at"):
            s["created_at"] = s["created_at"].isoformat()
        if s.get("last_emailed_at"):
            s["last_emailed_at"] = s["last_emailed_at"].isoformat()
            
    return searches

@app.post("/api/user/searches")
async def save_search(request: Request):
    """Save a new search"""
    # Auth
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    
    data = await request.json()
    name = data.get("name")
    criteria = data.get("criteria", {})
    email_alert = data.get("email_alert", False)
    
    if not name:
        raise HTTPException(status_code=400, detail="Search name is required")
        
    db = get_db()
    
    # Limit to 5
    count = db.saved_searches.count_documents({"user_email": email})
    if count >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 saved searches allowed")
        
    search_doc = {
        "user_email": email,
        "name": name,
        "criteria": criteria,
        "email_alert": email_alert,
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "last_emailed_at": None
    }
    
    res = db.saved_searches.insert_one(search_doc)
    return {"message": "Search saved", "id": str(res.inserted_id)}

@app.delete("/api/user/searches/{search_id}")
async def delete_search(search_id: str, request: Request):
    """Delete a saved search"""
    # Auth
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    
    db = get_db()
    res = db.saved_searches.delete_one({"_id": ObjectId(search_id), "user_email": email})
    
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Search not found")
        
    return {"message": "Search deleted"}

@app.patch("/api/user/searches/{search_id}")
async def update_search(search_id: str, request: Request):
    """Toggle alert status"""
    # Auth
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    email = payload.get("sub")
    
    data = await request.json()
    email_alert = data.get("email_alert")
    
    db = get_db()
    update_data = {}
    if email_alert is not None:
        update_data["email_alert"] = email_alert
        
    res = db.saved_searches.update_one(
        {"_id": ObjectId(search_id), "user_email": email},
        {"$set": update_data}
    )
    
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Search not found")
        
    return {"message": "Search updated"}
    
    db = get_db()
    user = db.users.find_one({"email": payload["sub"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {
        "email": user["email"],
        "full_name": user.get("full_name"),
        "created_at": user["created_at"].isoformat() if hasattr(user.get("created_at"), "isoformat") else str(user.get("created_at", ""))
    }

@app.get("/api/collections")
async def get_collections():
    """Fetch all curated job collections"""
    db = get_db()
    collections = list(db.collections.find({}, {"_id": 0}))
    return collections

@app.get("/api/stats")
async def get_stats():
    """Get dashboard stats"""
    db = get_db()
    try:
        total_jobs = db.jobs.count_documents({"is_active": True})
        
        # Distribution by company
        company_pipeline = [
            {"$match": {"is_active": True}},
            {"$group": {"_id": "$company", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        company_stats = list(db.jobs.aggregate(company_pipeline))
        
        # Remote counts
        remote_count = db.jobs.count_documents({"is_active": True, "remote_type": "Remote"})
        
        return {
            "total_jobs": total_jobs,
            "company_stats": company_stats,
            "remote_count": remote_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stats/visit")
async def record_visit(request: Request):
    """Increment global visit count and log detailed visitor info"""
    db = get_db()
    try:
        # 1. Atomic increment of global counter
        result = db.site_stats.find_one_and_update(
            {"_id": "global"},
            {"$inc": {"visits": 1}},
            upsert=True,
            return_document=True
        ) or {"visits": 0}

        # 2. Detailed logging
        visitor_info = {
            "timestamp": datetime.now(timezone.utc),
            "ip_address": request.client.host,
            "user_agent": request.headers.get("user-agent"),
            "referrer": request.headers.get("referer"),
            "path": request.url.path,
            "method": request.method
        }
        
        # Insert log asynchronously (fire and forget pattern if possible, but here we just wait)
        db.visitor_logs.insert_one(visitor_info)
        
        return {"visits": result.get("visits", 0)}
    except Exception as e:
        print(f"Detailed visit logging error: {e}")
        # Still try to return the global count if possible
        try:
            stats = db.site_stats.find_one({"_id": "global"})
            return {"visits": stats.get("visits", 0) if stats else 0}
        except:
            return {"visits": 0}

@app.get("/api/admin/visitor-stats")
async def get_visitor_stats(request: Request, limit: int = 50):
    """Get detailed visitor statistics for admin dashboard"""
    # Simple check for now - can be enhanced with proper auth
    # For now, we'll just allow it if it's coming from a local dev machine or has a specific secret 
    # (In a real app, this would be behind @login_required + admin role)
    db = get_db()
    try:
        # Get recent logs
        logs = list(db.visitor_logs.find().sort("timestamp", -1).limit(limit))
        for log in logs:
            log["_id"] = str(log["_id"])
            
        # Basic aggregation for stats
        total_visits = db.visitor_logs.count_documents({})
        
        # Unique visitors (by IP)
        unique_ips = len(db.visitor_logs.distinct("ip_address"))
        
        # Top referrers
        referrer_pipeline = [
            {"$group": {"_id": "$referrer", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        top_referrers = list(db.visitor_logs.aggregate(referrer_pipeline))
        
        return {
            "total_logs": total_visits,
            "unique_visitors": unique_ips,
            "top_referrers": top_referrers,
            "recent_logs": logs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Favorites Endpoints ---

@app.get("/api/user/favorites")
async def get_favorites(request: Request):
    """Get user's favorite companies"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    
    db = get_db()
    
    # Get favorite records
    favorites = list(db.user_favorites.find({"user_email": email}))
    
    if not favorites:
        return []
        
    company_names = [f["company_name"] for f in favorites]
    
    # Fetch full company details
    companies = list(db.companies.find({"name": {"$in": company_names}}))
    
    for comp in companies:
        comp["_id"] = str(comp["_id"])
        if not comp.get("metadata"):
            comp["metadata"] = {}
            
    return companies

@app.post("/api/user/favorites")
async def add_favorite(request: Request):
    """Add a company to user favorites"""
    user = verify_token(request)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    data = await request.json()
    email = user['email']
    raw_name = data.get('company_name')
    monitor_url = data.get('monitor_url')
    
    if not raw_name:
        raise HTTPException(status_code=400, detail="Company name is required")
        
    # Normalize name
    normalized_name, _ = normalize_company_name(raw_name)
    final_company_name = normalized_name
    final_company_id = None
    
    # Flags
    is_monitor = False
    ats_url = None
    ats_type = None

    # Logic: "Magic Add"
    # If a URL is provided, try to DISCOVER an ATS first.
    if monitor_url:
        try:
            from src.services.ats_discovery import ATSDiscoveryService
            service = ATSDiscoveryService()
            discovered_url, discovered_type = await service.discover_ats(monitor_url)
            
            if discovered_url:
                # SUCCESS: It's a scrapable company!
                ats_url = discovered_url
                ats_type = discovered_type
                is_monitor = False # We can scrape it!
            else:
                # FAILURE: It's a manual monitor
                is_monitor = True
        except Exception as e:
            print(f"Discovery error: {e}")
            is_monitor = True # Fallback to monitor
    
    # Check if company exists in master DB
    existing_company = db.companies.find_one({"name": {"$regex": f"^{final_company_name}$", "$options": "i"}})
    
    if existing_company:
        final_company_id = existing_company.get('company_id')
        final_company_name = existing_company.get('name') # Use canonical name
        
        # Merge new info if we discovered it
        update_fields = {}
        if ats_url and not existing_company.get('ats_url'):
            update_fields['ats_url'] = ats_url
        if ats_type and not existing_company.get('ats_system'):
            update_fields['ats_system'] = {'type': ats_type, 'detected_at': datetime.now(timezone.utc).replace(tzinfo=None)}
            
        if update_fields:
            db.companies.update_one({'_id': existing_company['_id']}, {'$set': update_fields})
            
    else:
        # Create new company record stub
        from src.database.models import Company, ATSSystem, CompanyMetadata
        
        metadata = CompanyMetadata(
            added_by="user_request", 
            tags=["User Favorite"],
            added_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        
        new_company = Company(
            name=final_company_name,
            domain="", # Unknown initially
            ats_system=ATSSystem(type=ats_type if ats_type else "unknown", detected_at=datetime.now(timezone.utc).replace(tzinfo=None)),
            ats_url=ats_url,
            metadata=metadata,
            is_active=True
        )
        
        res = db.companies.insert_one(new_company.to_dict())
        final_company_id = str(res.inserted_id)
        
    # Upsert User Favorite
    fav_entry = {
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "company_id": final_company_id,
        "is_monitor": is_monitor
    }
    if is_monitor:
        fav_entry['monitor_url'] = monitor_url
        fav_entry['last_checked_at'] = None
        
    db.user_favorites.update_one(
        {"user_email": email, "company_name": final_company_name},
        {
            "$set": fav_entry
        },
        upsert=True
    )
    
    return {
        "status": "success", 
        "company_name": final_company_name, 
        "is_monitor": is_monitor,
        "ats_detected": bool(ats_url)
    }

@app.post("/api/feedback")
async def submit_feedback(data: dict, request: Request):
    """Submit user feedback (Rate limited)"""
    await check_rate_limit(request, limit=5, window=600) # Max 5 per 10 mins
    content = data.get("content")
    email = data.get("email") # Optional user-provided email
    
    if not content:
        raise HTTPException(status_code=400, detail="Feedback content is required")
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="Feedback too long (max 2000 chars)")

    # Try to get user email from token if available
    auth_header = request.headers.get("Authorization")
    user_email = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        payload = decode_access_token(token)
        if payload:
            user_email = payload.get("sub")

    db = get_db()
    feedback_doc = {
        "content": content,
        "provided_email": email,
        "user_email": user_email,
        "user_agent": request.headers.get("User-Agent"),
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "status": "new"
    }
    
    db.user_feedbacks.insert_one(feedback_doc)
    return {"message": "Feedback submitted successfully"}

@app.get("/api/admin/feedbacks")
async def get_feedbacks(request: Request, page: int = 1, limit: int = 10):
    """Get all feedbacks with pagination (Admin only)"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    email = payload.get("sub")
    
    admin_email = os.getenv("ADMIN_EMAIL")
    # Case-insensitive check
    is_admin = (admin_email and email.lower() == admin_email.lower())
    
    if not is_admin:
        # Fallback: check if the user has is_admin=True in the DB
        db = get_db()
        user = db.users.find_one({"email": email})
        if not user or not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Forbidden: Admin only")

    db = get_db()
    total = db.user_feedbacks.count_documents({})
    skip = (page - 1) * limit
    feedbacks = list(db.user_feedbacks.find().sort("created_at", -1).skip(skip).limit(limit))
    
    for f in feedbacks:
        f["_id"] = str(f["_id"])
    
    return {
        "feedbacks": feedbacks,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.delete("/api/admin/feedback/{feedback_id}")
async def delete_feedback(feedback_id: str, request: Request):
    """Delete a feedback entry (Admin only)"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    email = payload.get("sub")
    admin_email = os.getenv("ADMIN_EMAIL")
    is_admin = (admin_email and email.lower() == admin_email.lower())
    
    if not is_admin:
        db = get_db()
        user = db.users.find_one({"email": email})
        if not user or not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Forbidden: Admin only")

    db = get_db()
    try:
        result = db.user_feedbacks.delete_one({"_id": ObjectId(feedback_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Feedback not found")
        return {"message": "Feedback deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid feedback ID: {str(e)}")

# --- Company Request Endpoints ---

@app.post("/api/user/request-company")
async def request_company(request: Request):
    """Allow users to request a new company to be crawled"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_email = payload.get("sub")
    data = await request.json()
    company_name = data.get("name", "").strip()
    careers_url = data.get("careers_url", "").strip()

    if not company_name:
        raise HTTPException(status_code=400, detail="Company name is required")

    db = get_db()
    
    # 1. Check if already exists in active companies
    existing = db.companies.find_one({"name": {"$regex": f"^{company_name}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=400, detail="This company is already being crawled")

    # 2. Check if already in requests
    existing_req = db.company_requests.find_one({
        "name": {"$regex": f"^{company_name}$", "$options": "i"},
        "status": "pending"
    })
    if existing_req:
        raise HTTPException(status_code=400, detail="A request for this company is already pending")

    request_doc = {
        "name": company_name,
        "careers_url": careers_url,
        "user_email": user_email,
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    
    db.company_requests.insert_one(request_doc)
    return {"message": "Request submitted successfully. Our team will review it soon."}

@app.get("/api/admin/company-requests")
async def get_company_requests(request: Request):
    """Get all company requests (Admin only)"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    email = payload.get("sub")
    admin_email = os.getenv("ADMIN_EMAIL")
    is_admin = (admin_email and email.lower() == admin_email.lower())
    
    if not is_admin:
        db = get_db()
        user = db.users.find_one({"email": email})
        if not user or not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Forbidden: Admin only")

    db = get_db()
    requests = list(db.company_requests.find().sort("created_at", -1))
    for r in requests:
        r["_id"] = str(r["_id"])
    return requests

@app.post("/api/admin/company-requests/{request_id}/process")
async def process_company_request(request_id: str, request: Request):
    """Approve or Reject a company request (Admin only)"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    email = payload.get("sub")
    admin_email = os.getenv("ADMIN_EMAIL")
    is_admin = (admin_email and email.lower() == admin_email.lower())
    
    if not is_admin:
        db = get_db()
        user = db.users.find_one({"email": email})
        if not user or not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Forbidden: Admin only")

    data = await request.json()
    action = data.get("action") # "approve" or "reject"
    
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'.")

    db = get_db()
    req_doc = db.company_requests.find_one({"_id": ObjectId(request_id)})
    if not req_doc:
        raise HTTPException(status_code=404, detail="Request not found")

    if action == "approve":
        # Create the company in the companies collection
        # We'll use the provided URL to try and detect the ATS later during crawling
        new_company = {
            "name": req_doc["name"],
            "domain": "", # Will be filled if possible during crawl
            "careers_url": req_doc.get("careers_url", ""),
            "ats_url": req_doc.get("careers_url", ""), # Fallback
            "is_active": True,
            "schedule": {"frequency_hours": 24, "priority": 1},
            "stats": {"total_jobs_found": 0, "active_jobs": 0},
            "metadata": {
                "added_by": f"request:{req_doc['user_email']}",
                "added_at": datetime.utcnow(),
                "verified": False,
                "tags": ["User Requested"]
            }
        }
        db.companies.insert_one(new_company)
        db.company_requests.update_one({"_id": ObjectId(request_id)}, {"$set": {"status": "approved"}})
        return {"message": f"Company '{req_doc['name']}' approved and added to crawl queue."}
    else:
        db.company_requests.update_one({"_id": ObjectId(request_id)}, {"$set": {"status": "rejected"}})
        return {"message": "Request rejected."}

@app.post("/api/user/favorites/{company_name}/check")
async def check_monitor(company_name: str, request: Request):
    """Update last_checked_at for a monitor"""
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else None
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
        
    payload = decode_access_token(token)
    email = payload.get("sub")
    
    db = get_db()
    
    result = db.user_favorites.update_one(
        {"user_email": email, "company_name": company_name},
        {"$set": {"last_checked_at": datetime.now(timezone.utc).replace(tzinfo=None)}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")
        
    return {"message": "Monitor updated"}

@app.delete("/api/user/favorites/{company_name}")
async def remove_favorite(company_name: str, request: Request):
    """Remove a favorite"""
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else None
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
        
    payload = decode_access_token(token)
    email = payload.get("sub")
    
    db = get_db()
    db.user_favorites.delete_one({
        "user_email": email, 
        "company_name": company_name
    })
    
    return {"message": "Removed from favorites"}

# ── Personal Digest Endpoints ─────────────────────────────────────────────────

def _get_user_email_from_request(request: Request) -> str:
    """Extract and validate any logged-in user email from Bearer token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub", "")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return email


def _split_profile_terms(value: Any) -> List[str]:
    """Normalize comma/newline separated profile text into search terms."""
    if isinstance(value, list):
        raw_terms = value
    else:
        raw_terms = re.split(r"[,;\n]+", str(value or ""))
    return [term.strip() for term in raw_terms if term and term.strip()]


def _profile_from_legacy_doc(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not profile:
        return {}
    return {
        "name": profile.get("name") or "My Profile",
        "target_roles": _split_profile_terms(profile.get("target_roles")),
        "core_skills": _split_profile_terms(profile.get("skills") or profile.get("core_skills")),
        "target_companies": _split_profile_terms(profile.get("target_companies")),
        "locations": _split_profile_terms(profile.get("locations")),
        "strict_location": profile.get("strict_location", True),
        "resume_text": profile.get("resume_text", ""),
        "resume_filename": profile.get("resume_filename", ""),
        "exclusions": _split_profile_terms(profile.get("exclusion_keywords") or profile.get("exclusions")),
        "min_score": float(profile.get("min_score", 5.0) or 5.0),
        "is_default": True,
    }


def _extract_resume_signals(resume_text: str) -> Dict[str, Any]:
    """Cheap resume parsing for first-pass matching. Stores no binary files."""
    text = (resume_text or "")[:50000]
    text_l = text.lower()
    known_skills = [
        "python", "go", "java", "javascript", "typescript", "kubernetes", "terraform",
        "aws", "azure", "gcp", "docker", "istio", "kafka", "grpc", "fastapi",
        "react", "llm", "rag", "langchain", "vector", "postgres", "mongodb",
        "snowflake", "databricks", "distributed systems", "microservices",
        "observability", "sre", "security", "machine learning", "mlops"
    ]
    extracted = []
    for skill in known_skills:
        if skill in text_l:
            extracted.append(" ".join(part.upper() if part in {"aws", "gcp", "llm", "rag", "sre"} else part.capitalize() for part in skill.split()))

    domains = []
    for domain in ["financial services", "banking", "cloud", "ai infrastructure", "enterprise", "platform", "devops"]:
        if domain in text_l:
            domains.append(domain.title())

    seniority = "Staff/Principal" if re.search(r"\b(staff|principal|vp|director|lead|architect)\b", text_l) else "Senior"
    return {
        "extracted_skills": list(dict.fromkeys(extracted))[:40],
        "domains": list(dict.fromkeys(domains))[:12],
        "seniority": seniority,
    }


def _infer_profile_from_resume(resume_text: str) -> Dict[str, Any]:
    """Infer editable profile defaults from resume text."""
    text = (resume_text or "")[:50000]
    text_l = text.lower()
    signals = _extract_resume_signals(text)

    role_rules = [
        ("Platform Engineer", ["platform engineer", "platform engineering", "kubernetes", "terraform", "infrastructure"]),
        ("Cloud Solution Architect", ["solution architect", "cloud architect", "aws certified solutions architect", "azure architect"]),
        ("DevOps Engineer", ["devops", "sre", "site reliability", "ci/cd", "observability"]),
        ("Backend Engineer", ["backend", "api", "microservices", "grpc", "fastapi", "java", "go"]),
        ("AI Platform Engineer", ["llm", "rag", "genai", "ai platform", "mlops", "vector"]),
        ("Staff Software Engineer", ["staff", "principal", "lead engineer", "architecture"]),
        ("Engineering Manager", ["manager", "managed", "team lead", "director"]),
    ]
    roles = []
    for role, needles in role_rules:
        if any(n in text_l for n in needles):
            roles.append(role)

    if not roles:
        roles = [signals.get("seniority", "Senior") + " Software Engineer"]

    location_rules = [
        ("Remote", ["remote"]),
        ("United States", ["united states", " usa", " u.s.", " seattle", " new york", " california", " texas"]),
        ("Seattle", ["seattle"]),
        ("New York", ["new york", "nyc"]),
        ("New Jersey", ["new jersey"]),
        ("California", ["california", "san francisco", "bay area", "los angeles"]),
        ("Japan", ["japan", "tokyo", "osaka"]),
        ("Canada", ["canada", "toronto", "vancouver"]),
        ("United Kingdom", ["united kingdom", "london", " uk"]),
        ("China", ["china", "beijing", "shanghai", "shenzhen"]),
    ]
    locations = []
    for loc, needles in location_rules:
        if any(n in text_l for n in needles):
            locations.append(loc)
    if not locations:
        locations = ["Remote", "United States"]
    preferred_areas = [loc for loc in locations if loc not in {"Remote", "United States"}]
    acceptable_areas = [loc for loc in locations if loc in {"Remote", "United States"}]

    exclusions = ["Junior", "Intern", "QA"]
    if "data scientist" not in text_l:
        exclusions.append("Data Scientist")
    if "frontend" not in text_l and "react" not in text_l:
        exclusions.append("Frontend only")

    return {
        "target_roles": list(dict.fromkeys(roles))[:6],
        "core_skills": signals.get("extracted_skills", [])[:18],
        "locations": list(dict.fromkeys(locations))[:8],
        "preferred_areas": list(dict.fromkeys(preferred_areas))[:6],
        "acceptable_areas": list(dict.fromkeys(acceptable_areas))[:6],
        "exclusions": exclusions,
        "seniority": signals.get("seniority", "Senior"),
    }


async def _extract_resume_text_from_upload(file: UploadFile) -> str:
    """Extract text from common resume formats. Original file bytes are not stored."""
    filename = (file.filename or "").lower()
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Resume file must be 5MB or smaller")

    if filename.endswith((".txt", ".md", ".text")):
        return content.decode("utf-8", errors="ignore").strip()

    if filename.endswith(".pdf"):
        try:
            from io import BytesIO
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            parts = [page.extract_text() or "" for page in reader.pages[:12]]
            return "\n".join(parts).strip()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not extract text from PDF: {e}")

    if filename.endswith(".docx"):
        try:
            from io import BytesIO
            from docx import Document
            doc = Document(BytesIO(content))
            paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
            return "\n".join(paragraphs).strip()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not extract text from DOCX: {e}")

    raise HTTPException(status_code=400, detail="Supported resume formats: PDF, DOCX, TXT, MD")


def _location_aliases(location: str) -> List[str]:
    loc = location.strip().lower()
    aliases = {
        "usa": ["united states", "usa", "u.s.", "america"],
        "us": ["united states", "usa", "u.s.", "america"],
        "united states": ["united states", "usa", "u.s.", "america"],
        "japan": ["japan", "tokyo", "osaka", "kyoto"],
        "canada": ["canada", "toronto", "vancouver", "montreal"],
        "uk": ["united kingdom", "uk", "london", "england"],
        "united kingdom": ["united kingdom", "uk", "london", "england"],
        "germany": ["germany", "berlin", "munich"],
        "france": ["france", "paris"],
        "australia": ["australia", "sydney", "melbourne"],
        "new york": ["new york", "nyc"],
        "new jersey": ["new jersey"],
        "california": ["california", "san francisco", "bay area", "los angeles"],
        "washington": ["washington", "seattle"],
        "texas": ["texas", "austin", "dallas", "houston"],
        "remote": ["remote", "anywhere"],
    }
    return aliases.get(loc, [loc])


def _location_matches(job: Dict[str, Any], preferred_locations: List[str]) -> bool:
    if not preferred_locations:
        return True
    job_location = str(job.get("location") or "")
    remote_type = str(job.get("remote_type") or "")
    company_location = str(job.get("company_location") or "")
    haystack = f"{job_location} {remote_type} {company_location}".lower()

    for preferred in preferred_locations:
        aliases = _location_aliases(preferred)
        if "remote" in aliases and ("remote" in haystack or remote_type.lower() == "remote"):
            return True
        if any(alias and alias in haystack for alias in aliases):
            return True
    return False


def _normalize_geo_preferences(profile: Dict[str, Any]) -> Dict[str, Any]:
    geo = profile.get("geo_preferences") or {}
    preferred_areas = _split_profile_terms(geo.get("preferred_areas", []))
    acceptable_areas = _split_profile_terms(geo.get("acceptable_areas", []))

    if not geo:
        preferred_areas = _split_profile_terms(profile.get("locations", []))

    return {
        "preferred_areas": list(dict.fromkeys(preferred_areas)),
        "acceptable_areas": list(dict.fromkeys(acceptable_areas)),
    }


def _geo_match_level(job: Dict[str, Any], profile: Dict[str, Any]) -> str:
    geo = _normalize_geo_preferences(profile)
    if _location_matches(job, geo["preferred_areas"]):
        return "preferred"
    if _location_matches(job, geo["acceptable_areas"]):
        return "acceptable"
    if not geo["preferred_areas"] and not geo["acceptable_areas"]:
        return "unspecified"
    return "none"


def _score_job_for_profile(job: Dict[str, Any], profile: Dict[str, Any], feedback: Dict[str, Any]) -> Dict[str, Any]:
    title = str(job.get("title") or "")
    company = str(job.get("company") or "")
    location = str(job.get("location") or "")
    skills = [str(s) for s in job.get("skills", [])]
    description = str(job.get("description") or "")
    resume_text = str(profile.get("resume_text") or "")
    resume_signals = profile.get("resume_signals") or {}
    resume_skills = resume_signals.get("extracted_skills", [])
    text = f"{title} {company} {location} {' '.join(skills)} {description}".lower()

    score = 2.0
    reasons: List[str] = []
    concerns: List[str] = []
    matched_skills: List[str] = []

    for term in profile.get("exclusions", []):
        if term and term.lower() in text:
            score -= 5.0
            concerns.append(f"Excluded signal: {term}")

    for role in profile.get("target_roles", []):
        role_l = role.lower()
        if role_l and role_l in title.lower():
            score += 2.7
            reasons.append(f"Title matches {role}")
        elif role_l and role_l in text:
            score += 1.2
            reasons.append(f"Description mentions {role}")

    for skill in profile.get("core_skills", []):
        skill_l = skill.lower()
        if not skill_l:
            continue
        if skill_l in " ".join(skills).lower():
            score += 0.9
            matched_skills.append(skill)
        elif skill_l in text:
            score += 0.45
            matched_skills.append(skill)

    for skill in resume_skills:
        skill_l = str(skill).lower()
        if skill_l and skill_l in text:
            score += 0.35
            matched_skills.append(skill)

    if resume_text and any(str(skill).lower() in text for skill in resume_skills):
        reasons.append("Matches uploaded resume skills")

    for target_company in profile.get("target_companies", []):
        if target_company and target_company.lower() in company.lower():
            score += 1.8
            reasons.append(f"Target company: {company}")
            break

    if any(s in title.lower() for s in ["staff", "principal", "lead", "architect", "senior"]):
        score += 0.8
        reasons.append("Seniority signal fits experienced track")

    geo_level = _geo_match_level(job, profile)
    if geo_level == "preferred":
        score += 0.9
        reasons.append(f"Preferred area: {location}")
    elif geo_level == "acceptable":
        score += 0.2
        concerns.append(f"Acceptable area: {location}")
    elif geo_level == "none" and location:
        concerns.append(f"Outside selected areas: {location}")

    action = feedback.get(str(job.get("_id")))
    if action in {"good_fit", "save", "applied"}:
        score += 1.0
        reasons.append("Boosted by your feedback")
    elif action in {"not_for_me", "hide"}:
        score -= 3.0
        concerns.append("Previously marked not relevant")
    elif action == "hide_company":
        score -= 5.0
        concerns.append("Company hidden by you")

    score = max(0.0, min(10.0, round(score, 1)))
    return {
        "score": score,
        "reasons": reasons[:4] or ["Possible match based on profile overlap"],
        "concerns": concerns[:3],
        "matched_skills": list(dict.fromkeys(matched_skills))[:8],
    }


@app.get("/api/profiles")
async def get_career_profiles(request: Request):
    """Return career radar profiles for the logged-in user."""
    email = _get_user_email_from_request(request)
    db = get_db()

    profiles = list(db.career_profiles.find({"user_email": email}).sort("created_at", 1))

    for idx, profile in enumerate(profiles):
        if profile.get("_id"):
            profile["id"] = str(profile["_id"])
            profile.pop("_id", None)
        else:
            profile["id"] = profile.get("name", f"profile-{idx}").lower().replace(" ", "-")
        profile.pop("user_email", None)
    return profiles


@app.post("/api/profiles")
async def save_career_profile(request: Request):
    """Create or update one of the user's career profiles. Limit to five tracks."""
    email = _get_user_email_from_request(request)
    data = await request.json()
    db = get_db()

    profile_id = data.get("id")
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Profile name is required")

    existing_profile = None
    if profile_id and ObjectId.is_valid(profile_id):
        existing_profile = db.career_profiles.find_one({"_id": ObjectId(profile_id), "user_email": email})
    if not existing_profile:
        existing_profile = db.career_profiles.find_one({
            "user_email": email,
            "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
        })

    existing_count = db.career_profiles.count_documents({"user_email": email})
    if not existing_profile and existing_count >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 career directions allowed. Choose an existing direction to overwrite.")

    resume_text = str(data.get("resume_text") or "")[:50000]
    preferred_areas = _split_profile_terms(data.get("preferred_areas") or data.get("locations"))
    acceptable_areas = _split_profile_terms(data.get("acceptable_areas"))
    locations = list(dict.fromkeys(preferred_areas + acceptable_areas))
    doc = {
        "user_email": email,
        "name": name,
        "target_roles": _split_profile_terms(data.get("target_roles")),
        "core_skills": _split_profile_terms(data.get("core_skills") or data.get("skills")),
        "target_companies": _split_profile_terms(data.get("target_companies")),
        "locations": locations,
        "geo_preferences": {
            "preferred_areas": preferred_areas,
            "acceptable_areas": acceptable_areas,
        },
        "strict_location": bool(data.get("strict_location", True)),
        "exclusions": _split_profile_terms(data.get("exclusions") or data.get("exclusion_keywords")),
        "resume_text": resume_text,
        "resume_filename": (data.get("resume_filename") or "").strip()[:180],
        "resume_signals": _extract_resume_signals(resume_text),
        "min_score": float(data.get("min_score", 5.0) or 5.0),
        "is_default": bool(data.get("is_default", existing_count == 0)),
        "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }

    if doc["is_default"]:
        db.career_profiles.update_many({"user_email": email}, {"$set": {"is_default": False}})

    saved_id = None
    if existing_profile:
        saved_id = existing_profile.get("_id")
        result = db.career_profiles.update_one(
            {"_id": saved_id, "user_email": email},
            {"$set": doc}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Profile not found")
    else:
        doc["created_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        result = db.career_profiles.insert_one(doc)
        saved_id = result.inserted_id

    return {
        "status": "success",
        "message": "Career profile saved",
        "id": str(saved_id) if saved_id else None,
        "name": name,
    }


@app.post("/api/profiles/parse-resume")
async def parse_resume_upload(request: Request, file: UploadFile = File(...)):
    """Parse uploaded resume into text for profile storage."""
    _get_user_email_from_request(request)
    text = await _extract_resume_text_from_upload(file)
    if not text:
        raise HTTPException(status_code=400, detail="No readable text found in resume")
    text = text[:50000]
    return {
        "filename": file.filename,
        "text": text,
        "resume_signals": _extract_resume_signals(text),
        "profile_suggestions": _infer_profile_from_resume(text),
    }


@app.get("/api/recommendations")
async def get_recommendations(
    request: Request,
    profile: Optional[str] = None,
    days: int = 14,
    limit: int = 30,
    min_score: Optional[float] = None,
):
    """Return ranked jobs for the selected career profile."""
    email = _get_user_email_from_request(request)
    db = get_db()

    profiles = list(db.career_profiles.find({"user_email": email}).sort("created_at", 1))
    if not profiles:
        return {
            "setup_required": True,
            "profile": None,
            "profile_detail": None,
            "profiles": [],
            "jobs": [],
            "total_ranked": 0,
            "strong_count": 0,
            "candidate_count": 0,
            "days": days,
            "message": "Create a career direction and add resume text to start personalized recommendations."
        }

    selected = None
    if profile:
        selected = next((
            p for p in profiles
            if str(p.get("_id", "")) == profile
            or str(p.get("name", "")).lower() == profile.lower()
            or str(p.get("id", "")).lower() == profile.lower()
        ), None)
    if not selected:
        selected = next((p for p in profiles if p.get("is_default")), profiles[0])

    selected = _profile_from_legacy_doc(selected) if "core_skills" not in selected and "skills" in selected else selected
    selected["core_skills"] = selected.get("core_skills") or _split_profile_terms(selected.get("skills"))
    selected["exclusions"] = selected.get("exclusions") or _split_profile_terms(selected.get("exclusion_keywords"))
    selected["target_roles"] = selected.get("target_roles") or []
    selected["target_companies"] = selected.get("target_companies") or []
    selected["locations"] = selected.get("locations") or []
    selected["resume_signals"] = selected.get("resume_signals") or _extract_resume_signals(selected.get("resume_text", ""))

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, min(days, 90)))
    candidate_limit = max(limit * 8, 120)
    query: Dict[str, Any] = {"is_active": True}
    if days:
        query["posted_date"] = {"$gte": cutoff}

    jobs = list(db.jobs.find(query).sort("posted_date", -1).limit(candidate_limit))
    if not jobs and days < 90:
        jobs = list(db.jobs.find({"is_active": True}).sort("posted_date", -1).limit(candidate_limit))

    feedback_rows = list(db.job_feedback.find({"user_email": email}))
    feedback = {str(row.get("job_id")): row.get("action") for row in feedback_rows}

    scored_jobs = []
    for job in jobs:
        job["_id"] = str(job["_id"])
        if job.get("posted_date"):
            job["posted_date"] = job["posted_date"].isoformat() if hasattr(job["posted_date"], "isoformat") else str(job["posted_date"])
        if job.get("scraped_at"):
            job["scraped_at"] = job["scraped_at"].isoformat() if hasattr(job["scraped_at"], "isoformat") else str(job["scraped_at"])
        geo_level = _geo_match_level(job, selected)
        if selected.get("strict_location", True) and geo_level == "none":
            continue
        scoring = _score_job_for_profile(job, selected, feedback)
        if min_score is None or scoring["score"] >= min_score:
            job["radar_score"] = scoring["score"]
            job["radar_reasons"] = scoring["reasons"]
            job["radar_concerns"] = scoring["concerns"]
            job["matched_skills"] = scoring["matched_skills"]
            scored_jobs.append(job)

    scored_jobs.sort(key=lambda j: (j.get("radar_score", 0), j.get("posted_date", "")), reverse=True)
    selected_name = selected.get("name", "My Profile")
    strong_count = sum(1 for j in scored_jobs if j.get("radar_score", 0) >= 7)

    return {
        "profile": selected_name,
        "profile_detail": {
            "id": str(selected.get("_id", selected.get("id", ""))),
            "name": selected_name,
            "target_roles": selected.get("target_roles", []),
            "core_skills": selected.get("core_skills", []),
            "target_companies": selected.get("target_companies", []),
            "locations": selected.get("locations", []),
            "geo_preferences": _normalize_geo_preferences(selected),
            "strict_location": selected.get("strict_location", True),
            "exclusions": selected.get("exclusions", []),
            "resume_text": selected.get("resume_text", ""),
            "resume_filename": selected.get("resume_filename", ""),
            "resume_signals": selected.get("resume_signals", {}),
            "min_score": selected.get("min_score", 5.0),
            "is_default": selected.get("is_default", False),
        },
        "profiles": [
            {
                "id": str(p.get("_id", p.get("id", p.get("name", "")))),
                "name": p.get("name", "Profile"),
                "is_default": p.get("is_default", False),
            }
            for p in profiles
        ],
        "jobs": scored_jobs[:limit],
        "total_ranked": len(scored_jobs),
        "strong_count": strong_count,
        "candidate_count": len(jobs),
        "days": days,
    }


@app.post("/api/jobs/{job_id}/feedback")
async def save_job_feedback(job_id: str, request: Request):
    """Store a recommendation feedback action for a job."""
    email = _get_user_email_from_request(request)
    data = await request.json()
    action = data.get("action")
    allowed = {"good_fit", "not_for_me", "save", "applied", "hide_company", "hide"}
    if action not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported feedback action")

    db = get_db()
    db.job_feedback.update_one(
        {"user_email": email, "job_id": job_id, "profile_name": data.get("profile_name", "default")},
        {
            "$set": {
                "action": action,
                "reason": data.get("reason", ""),
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
            },
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            }
        },
        upsert=True,
    )
    return {"status": "success", "message": "Feedback saved"}


@app.get("/my_digest.html", response_class=HTMLResponse)
async def read_digest_page():
    digest_file = project_root_path / "my_digest.html"
    if digest_file.exists():
        return digest_file.read_text()
    return "<h1>Digest page not found</h1>"


@app.post("/api/digest/run")
async def run_personal_digest(request: Request):
    """
    Trigger the personal AI digest. Admin only.
    Body (optional JSON): { "days": 1, "top": 15, "min_score": 5, "dry_run": false, "provider": "gemini" }
    """
    user_email = _get_user_email_from_request(request)
    
    try:
        data = await request.json()
    except Exception:
        data = {}

    recipient = data.get("recipient", user_email) # Default to logged-in user

    days      = int(data.get("days", 1))
    top_n     = int(data.get("top", 15))
    min_score = float(data.get("min_score", 5.0))
    dry_run   = bool(data.get("dry_run", False))
    provider  = data.get("provider", None)

    # Import and run digest (runs in same process — fast enough for manual trigger)
    import subprocess, sys
    args = [
        sys.executable,
        str(project_root_path / "scripts" / "personal_digest.py"),
        "--days", str(days),
        "--top", str(top_n),
        "--min-score", str(min_score),
        "--recipient", recipient
    ]
    if provider:
        args += ["--provider", provider]
    if dry_run:
        args.append("--dry-run")

    try:
        result = subprocess.run(
            args,
            capture_output=True, text=True, timeout=180,
            cwd=str(project_root_path),
        )
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "stdout": result.stdout[-5000:],   # more chars
            "stderr": result.stderr[-2000:],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "status": "timeout", 
            "message": "Digest took too long (>180s).",
            "stdout": (e.stdout.decode() if e.stdout else "") + "\n... [TIMEOUT] ...",
            "stderr": (e.stderr.decode() if e.stderr else "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user/profile")
async def get_user_profile(request: Request):
    """Get current user's career profile."""
    email = _get_user_email_from_request(request)
    db = get_db()
    
    profile = db.user_profiles.find_one({"user_email": email})
    if not profile:
        return {
            "target_roles": "",
            "skills": "",
            "target_companies": "",
            "min_experience": 0,
            "exclusion_keywords": ""
        }
    
    # Remove MongoDB internal IDs
    profile.pop("_id", None)
    return profile

@app.post("/api/user/profile")
async def update_user_profile(request: Request):
    """Update current user's career profile."""
    email = _get_user_email_from_request(request)
    data = await request.json()
    
    db = get_db()
    db.user_profiles.update_one(
        {"user_email": email},
        {
            "$set": {
                "target_roles": data.get("target_roles"),
                "skills": data.get("skills"),
                "target_companies": data.get("target_companies"),
                "min_experience": int(data.get("min_experience", 0)),
                "exclusion_keywords": data.get("exclusion_keywords"),
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None)
            }
        },
        upsert=True
    )
    
    return {"status": "success", "message": "Career profile updated"}


@app.get("/api/digest/settings")
async def get_digest_settings(request: Request):
    """Get current user's digest subscription settings."""
    email = _get_user_email_from_request(request)
    db = get_db()
    
    settings = db.user_digest_settings.find_one({"user_email": email})
    if not settings:
        # Default settings for new users
        return {
            "user_email": email,
            "frequency": "off",
            "is_active": False,
            "last_sent_at": None
        }
    
    return {
        "frequency": settings.get("frequency", "off"),
        "is_active": settings.get("is_active", False),
        "last_sent_at": settings.get("last_sent_at").isoformat() if settings.get("last_sent_at") else None
    }

@app.post("/api/digest/settings")
async def update_digest_settings(request: Request):
    """Update current user's digest subscription settings."""
    email = _get_user_email_from_request(request)
    data = await request.json()
    
    frequency = data.get("frequency", "off") # daily, weekly, off
    is_active = data.get("is_active", frequency != "off")
    
    db = get_db()
    db.user_digest_settings.update_one(
        {"user_email": email},
        {
            "$set": {
                "frequency": frequency,
                "is_active": is_active,
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None)
            }
        },
        upsert=True
    )
    
    return {"status": "success", "message": "Subscription settings updated"}


@app.get("/api/digest/log")
async def get_digest_log(request: Request, limit: int = 20):
    """Return recent digest run history. Admin only."""
    _get_user_email_from_request(request)

    db = get_db()
    try:
        logs = list(db.digest_log.find().sort("run_at", -1).limit(limit))
        for log in logs:
            log["_id"] = str(log["_id"])
            if log.get("run_at") and hasattr(log["run_at"], "isoformat"):
                log["run_at"] = log["run_at"].isoformat()
        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── User Keyword Alert Settings ───────────────────────────────────────────────

@app.get("/api/user/alert-settings")
async def get_alert_settings(request: Request):
    """
    Get the current user's keyword job alert configuration.
    Returns keywords list, alert_email, frequency, is_active, last_sent_at.
    """
    email = _get_user_email_from_request(request)
    db = get_db()

    settings = db.user_alert_settings.find_one({"user_email": email})
    if not settings:
        return {
            "user_email": email,
            "keywords": [],
            "alert_email": email,
            "frequency": "daily",
            "is_active": False,
            "last_sent_at": None,
            "total_emails_sent": 0,
        }

    return {
        "user_email": email,
        "keywords": settings.get("keywords", []),
        "alert_email": settings.get("alert_email", email),
        "frequency": settings.get("frequency", "daily"),
        "is_active": settings.get("is_active", False),
        "last_sent_at": settings["last_sent_at"].isoformat() if settings.get("last_sent_at") else None,
        "total_emails_sent": settings.get("total_emails_sent", 0),
        "last_matched_count": settings.get("last_matched_count", 0),
    }


@app.post("/api/user/alert-settings")
async def update_alert_settings(request: Request):
    """
    Save the current user's keyword job alert configuration.

    Body (JSON):
      {
        "keywords":    ["Python", "Kubernetes", "LLM"],  // list of skill keywords
        "alert_email": "me@example.com",                 // delivery address (defaults to account email)
        "frequency":   "daily" | "weekly" | "off",
        "is_active":   true | false
      }
    Setting is_active=false or frequency="off" opts the user out.
    """
    email = _get_user_email_from_request(request)
    data  = await request.json()

    keywords     = data.get("keywords", [])
    alert_email  = (data.get("alert_email") or email).strip()
    frequency    = data.get("frequency", "daily")
    is_active    = data.get("is_active", True)

    # Normalize
    if frequency not in ("daily", "weekly", "off"):
        raise HTTPException(status_code=400, detail="frequency must be 'daily', 'weekly', or 'off'")
    if frequency == "off":
        is_active = False

    # Sanitize keyword list
    keywords = [k.strip() for k in keywords if k.strip()][:30]  # max 30 keywords

    db = get_db()
    db.user_alert_settings.update_one(
        {"user_email": email},
        {
            "$set": {
                "keywords":    keywords,
                "alert_email": alert_email,
                "frequency":   frequency,
                "is_active":   is_active,
                "updated_at":  datetime.now(timezone.utc).replace(tzinfo=None),
            },
            "$setOnInsert": {
                "created_at":        datetime.now(timezone.utc).replace(tzinfo=None),
                "last_sent_at":      None,
                "total_emails_sent": 0,
            }
        },
        upsert=True,
    )

    status_msg = "Alert enabled" if is_active else "Alert disabled (opted out)"
    return {"status": "success", "message": status_msg, "keywords_count": len(keywords)}


if __name__ == "__main__":
    import uvicorn
    port = 8123
    print(f"🚀 Starting Dashboard on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
