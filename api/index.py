import os
import sys
from typing import List, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv
import re

# Add project root to path for database connection and models
# Path is now parent of parent because we are in api/index.py
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from src.database.connection import get_db

load_dotenv()

app = FastAPI(title="JobDetector Dashboard")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/jobs")
async def get_jobs(
    q: Optional[str] = None,
    company: Optional[str] = None,
    job_type: Optional[str] = None,
    remote_type: Optional[str] = None
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
