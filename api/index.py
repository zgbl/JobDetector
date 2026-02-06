import os
import sys
from typing import List, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv
import re

from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Add project root to path for database connection and models
project_root_path = Path(__file__).parent.parent
project_root = str(project_root_path)
sys.path.insert(0, project_root)

from src.database.connection import get_db
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
from datetime import datetime

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

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "JobDetector API is running"}

# Mount static folders if they exist
if (project_root_path / "css").exists():
    app.mount("/css", StaticFiles(directory=str(project_root_path / "css")), name="css")
if (project_root_path / "js").exists():
    app.mount("/js", StaticFiles(directory=str(project_root_path / "js")), name="js")

@app.get("/api/jobs")
async def get_jobs(
    q: Optional[str] = None,
    company: Optional[str] = None,
    job_type: Optional[str] = None,
    remote_type: Optional[str] = None,
    location: Optional[str] = None,
    category: Optional[str] = None,
    days: Optional[int] = None
):
    """Fetch jobs with search and filtering"""
    db = get_db()
    
    query = {"is_active": True}
    and_conditions = []
    
    if q:
        # Search in title, company, and description
        and_conditions.append({
            "$or": [
                {"title": {"$regex": q, "$options": "i"}},
                {"company": {"$regex": q, "$options": "i"}},
                {"description": {"$regex": q, "$options": "i"}},
                {"skills": {"$in": [re.compile(q, re.I)]}}
            ]
        })
    
    if company:
        query["company"] = company
    
    if job_type:
        query["job_type"] = job_type
        
    if remote_type:
        query["remote_type"] = remote_type

    if location:
        if location.lower() == "remote":
            and_conditions.append({
                "$or": [
                    {"location": {"$regex": "remote", "$options": "i"}},
                    {"remote_type": "Remote"}
                ]
            })
        else:
            query["location"] = {"$regex": location, "$options": "i"}

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
        # Get jobs sorted by date (newest first)
        jobs = list(db.jobs.find(query).sort("posted_date", -1).limit(100))
        
        # Format for API (handle ObjectId and datetime)
        for job in jobs:
            job["_id"] = str(job["_id"])
            if job.get("posted_date"):
                job["posted_date"] = job["posted_date"].isoformat() if hasattr(job["posted_date"], "isoformat") else str(job["posted_date"])
            if job.get("scraped_at"):
                job["scraped_at"] = job["scraped_at"].isoformat() if hasattr(job["scraped_at"], "isoformat") else str(job["scraped_at"])
                
        return jobs
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
        companies = list(db.companies.find(query).sort("name", 1))
        for comp in companies:
            comp["_id"] = str(comp["_id"])
            # Ensure metadata exists
            if not comp.get("metadata"):
                comp["metadata"] = {}
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

    user_doc = {
        "email": email,
        "hashed_password": get_password_hash(password),
        "full_name": full_name or email.split("@")[0],
        "created_at": datetime.utcnow(),
        "is_active": True
    }
    
    db.users.insert_one(user_doc)
    return {"message": "User registered successfully"}

@app.post("/api/auth/login")
async def login(request: Request):
    data = await request.json()
    email = data.get("email")
    password = data.get("password")

    db = get_db()
    user = db.users.find_one({"email": email})
    
    if not user or not verify_password(password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(data={"sub": user["email"]})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": {
            "email": user["email"],
            "full_name": user.get("full_name")
        }
    }

@app.get("/api/auth/me")
async def get_me(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload

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

if __name__ == "__main__":
    import uvicorn
    port = 8123
    print(f"🚀 Starting Dashboard on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
