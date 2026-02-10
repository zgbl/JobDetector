import os
import sys
from typing import List, Optional
from fastapi import FastAPI, Request, HTTPException, Query
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
from datetime import datetime, timedelta

load_dotenv()

app = FastAPI(title="JobDetector Dashboard")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve index.html at root
@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_file = project_root_path / "index.html"
    if index_file.exists():
        return index_file.read_text()
    return "<h1>Index.html not found at root</h1>"

@app.get("/favicon.ico")
async def favicon():
    """Return 204 No Content for favicon to prevent 404 errors"""
    from fastapi.responses import Response
    return Response(status_code=204)

@app.get("/favorites.html", response_class=HTMLResponse)
async def read_favorites():
    favorites_file = project_root_path / "favorites.html"
    if favorites_file.exists():
        return favorites_file.read_text()
    return "<h1>Page not found</h1>"

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "JobDetector API is running"}

# Mount static folders if they exist
# Mount static folders if they exist
css_path = project_root_path / "css"
js_path = project_root_path / "js"

if css_path.exists():
    app.mount("/css", StaticFiles(directory=str(css_path)), name="css")
else:
    print(f"WARNING: CSS path not found at {css_path}")

if js_path.exists():
    app.mount("/js", StaticFiles(directory=str(js_path)), name="js")
else:
    print(f"WARNING: JS path not found at {js_path}")

@app.get("/api/jobs")
async def get_jobs(
    q: Optional[str] = None,
    company: Optional[str] = None,
    job_type: Optional[str] = None,
    remote_type: Optional[str] = None,
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

    if location:
        # Normalize common country names
        country_map = {
            "usa": "United States|USA|U.S.",
            "japan": "Japan|Tokyo|Osaka|Kyoto",
            "china": "China|Shanghai|Beijing|Shenzhen",
            "uk": "United Kingdom|UK|London",
            "germany": "Germany|Berlin|Munich",
            "france": "France|Paris",
        }
        
        search_val = country_map.get(location.lower(), location)
        
        if location.lower() == "remote":
            and_conditions.append({
                "$or": [
                    {"location": {"$regex": "remote", "$options": "i"}},
                    {"remote_type": "Remote"}
                ]
            })
        else:
            # Check both job location and company base location
            and_conditions.append({
                "$or": [
                    {"location": {"$regex": search_val, "$options": "i"}},
                    {"company_location": {"$regex": search_val, "$options": "i"}}
                ]
            })

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
            "People": ["people", "hr", "recruiting", "talent"]
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
        cutoff = datetime.utcnow() - timedelta(days=days)
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
    verification_expires = datetime.utcnow() + timedelta(hours=24)

    user_doc = {
        "email": email,
        "hashed_password": get_password_hash(password),
        "full_name": full_name or email.split("@")[0],
        "created_at": datetime.utcnow(),
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
    if user.get("verification_token_expires") and user["verification_token_expires"] < datetime.utcnow():
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
    """Send password reset email"""
    data = await request.json()
    email = data.get("email")
    
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    
    db = get_db()
    user = db.users.find_one({"email": email})
    
    # Don't reveal if email exists or not (security best practice)
    if not user:
        return {"message": "If an account with that email exists, a password reset link has been sent."}
    
    # Generate reset token
    reset_token = secrets.token_urlsafe(32)
    reset_expires = datetime.utcnow() + timedelta(hours=1)
    
    # Save reset token
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
    email_sent = email_service.send_password_reset_email(email, reset_token, base_url)
    
    if not email_sent:
        print(f"Warning: Failed to send password reset email to {email}")
    
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
    if user.get("reset_token_expires") and user["reset_token_expires"] < datetime.utcnow():
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
    
    return {
        "email": user["email"],
        "full_name": user.get("full_name"),
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
        "created_at": datetime.utcnow(),
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
async def record_visit():
    """Increment and return site visit count"""
    db = get_db()
    try:
        # Atomic increment
        result = db.site_stats.find_one_and_update(
            {"_id": "global"},
            {"$inc": {"visits": 1}},
            upsert=True,
            return_document=True
        )
        return {"visits": result["visits"]}
    except Exception as e:
        print(f"Visit count error: {e}")
        return {"visits": 0}

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
            update_fields['ats_system'] = {'type': ats_type, 'detected_at': datetime.utcnow()}
            
        if update_fields:
            db.companies.update_one({'_id': existing_company['_id']}, {'$set': update_fields})
            
    else:
        # Create new company record stub
        from src.database.models import Company, ATSSystem, CompanyMetadata
        
        metadata = CompanyMetadata(
            added_by="user_request", 
            tags=["User Favorite"],
            added_at=datetime.utcnow()
        )
        
        new_company = Company(
            name=final_company_name,
            domain="", # Unknown initially
            ats_system=ATSSystem(type=ats_type if ats_type else "unknown", detected_at=datetime.utcnow()),
            ats_url=ats_url,
            metadata=metadata,
            is_active=True
        )
        
        res = db.companies.insert_one(new_company.to_dict())
        final_company_id = str(res.inserted_id)
        
    # Upsert User Favorite
    fav_entry = {
        "created_at": datetime.utcnow(),
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
        {"$set": {"last_checked_at": datetime.utcnow()}}
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

if __name__ == "__main__":
    import uvicorn
    port = 8123
    print(f"🚀 Starting Dashboard on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
