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
        get_password_hash, 
        verify_password, 
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
    
    if q:
        # Search in title, company, and description
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"company": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"skills": {"$in": [re.compile(q, re.I)]}}
        ]
    
    if company:
        query["company"] = company
    
    if job_type:
        query["job_type"] = job_type
        
    if remote_type:
        query["remote_type"] = remote_type

    if location:
        if location.lower() == "remote":
            query["$or"] = query.get("$or", []) + [{"location": {"$regex": "remote", "$options": "i"}}, {"remote_type": "Remote"}]
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
            query["$or"] = query.get("$or", []) + [
                {"title": {"$regex": category_regex, "$options": "i"}},
                {"skills": {"$in": [re.compile(category_regex, re.I)]}}
            ]

    if days:
        cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        query["posted_date"] = {"$gte": cutoff}

    try:
        # Get jobs sorted by date (newest first)
        jobs = list(db.jobs.find(query).sort("posted_date", -1).limit(100))
        
        # Format for API (handle ObjectId)
        for job in jobs:
            job["_id"] = str(job["_id"])
            if job.get("posted_date"):
                job["posted_date"] = job["posted_date"].isoformat()
            if job.get("scraped_at"):
                job["scraped_at"] = job["scraped_at"].isoformat()
                
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
                job["posted_date"] = job["posted_date"].isoformat()
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
    
    db = get_db()
    user = db.users.find_one({"email": payload["sub"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {
        "email": user["email"],
        "full_name": user.get("full_name"),
        "created_at": user["created_at"].isoformat() if "created_at" in user else None
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

if __name__ == "__main__":
    import uvicorn
    port = 8123
    print(f"🚀 Starting Dashboard on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
