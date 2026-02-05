import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import sys
import re

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import get_db
from dotenv import load_dotenv

load_dotenv()

EMAIL_USER = os.getenv("EMAIL_USERNAME")
EMAIL_PASS = os.getenv("EMAIL_APP_PASSWORD")

if not EMAIL_USER or not EMAIL_PASS:
    print("Error: Email credentials not set in .env")
    sys.exit(1)

def send_email(to_email, subject, body_html):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body_html, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, to_email, msg.as_string())
        server.quit()
        print(f"✅ Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False

def check_and_send_alerts():
    db = get_db()
    
    # 1. Get all saved searches with email_alert=True
    alerts = db.saved_searches.find({"email_alert": True})
    
    count = 0
    for alert in alerts:
        user_email = alert["user_email"]
        criteria = alert["criteria"]
        last_emailed = alert["last_emailed_at"]
        
        # Default lookback to 24h if never emailed, or use last_emailed
        cutoff = last_emailed if last_emailed else (datetime.utcnow() - timedelta(days=1))
        
        print(f"Checking alert '{alert['name']}' for {user_email} (since {cutoff})...")
        
        # Build Query matching api/index.py logic
        query = {"is_active": True, "posted_date": {"$gt": cutoff}}
        and_conditions = []
        
        q = criteria.get("q")
        if q:
            and_conditions.append({
                "$or": [
                    {"title": {"$regex": q, "$options": "i"}},
                    {"company": {"$regex": q, "$options": "i"}},
                    {"skills": {"$in": [re.compile(q, re.I)]}}
                ]
            })
            
        if criteria.get("location"):
             if criteria["location"].lower() == "remote":
                and_conditions.append({
                    "$or": [
                        {"location": {"$regex": "remote", "$options": "i"}},
                        {"remote_type": "Remote"}
                    ]
                })
             else:
                query["location"] = {"$regex": criteria["location"], "$options": "i"}

        if criteria.get("category"):
             # Simplify for script: regex title/skills with category name
             # In production, share the map from api/index.py
             cat_q = criteria["category"]
             and_conditions.append({
                "$or": [
                    {"title": {"$regex": cat_q, "$options": "i"}},
                    {"skills": {"$in": [re.compile(cat_q, re.I)]}}
                ]
            })

        if and_conditions:
            query["$and"] = and_conditions
            
        new_jobs = list(db.jobs.find(query).sort("posted_date", -1).limit(10))
        
        if new_jobs:
            print(f"Found {len(new_jobs)} new jobs!")
            
            # Generate Email
            html = f"<h2>JobDetector Alert: {len(new_jobs)} New Matches</h2>"
            html += f"<p>Here are the latest jobs for your search: <strong>{alert['name']}</strong></p><ul>"
            
            for job in new_jobs:
                html += f"""
                <li style="margin-bottom: 10px;">
                    <a href="{job['source_url']}" style="font-weight: bold; font-size: 16px;">{job['title']}</a> at {job['company']}<br>
                    <span style="color: #666;">{job.get('location', '')} • Posted {job.get('posted_date', 'Recently')}</span>
                </li>
                """
            html += f"</ul><p><a href='http://localhost:8123'>View all on JobDetector</a></p>"
            
            if send_email(user_email, f"Job Alert: {len(new_jobs)} new jobs for {alert['name']}", html):
                # Update last_emailed_at
                db.saved_searches.update_one(
                    {"_id": alert["_id"]},
                    {"$set": {"last_emailed_at": datetime.utcnow()}}
                )
                count += 1
        else:
            print("No new jobs found.")
            
    print(f"Alert run complete. Sent {count} emails.")

if __name__ == "__main__":
    check_and_send_alerts()
