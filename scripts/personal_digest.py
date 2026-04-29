#!/usr/bin/env python3
"""
Personal Job Digest - AI-Powered Career Match Engine
=====================================================
Fetches recent jobs, uses Gemini or MiniMax AI to score each against
a personal career profile, then emails the top matches.

Usage:
    python scripts/personal_digest.py [--days 1] [--top 15] [--dry-run]

Environment variables (.env):
    RECIPIENT_EMAIL       - Where to send the digest (your personal email)
    GEMINI_API_KEY        - Google Gemini API key (preferred)
    MINIMAX_API_KEY       - MiniMax API key (fallback)
    AI_PROVIDER           - "gemini" | "minimax" | "keyword" (default: gemini)
    EMAIL_USERNAME        - Gmail sender account
    EMAIL_APP_PASSWORD    - Gmail app password
    MONGODB_URI / MONGODB_DATABASE - Database connection
"""

import os
import sys
import json
import re
import smtplib
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone

# ── Project path bootstrap ───────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.database.connection import get_db
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────
RECIPIENT_EMAIL   = os.getenv("RECIPIENT_EMAIL", os.getenv("EMAIL_USERNAME", ""))
EMAIL_USER        = os.getenv("EMAIL_USERNAME", "")
EMAIL_PASS        = os.getenv("EMAIL_APP_PASSWORD", "")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
MINIMAX_API_KEY   = os.getenv("MINIMAX_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", os.getenv("MINIMAX_API_KEY", "")) # Fallback to MINIMAX_API_KEY if it's an OpenRouter key
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "minimax/minimax-m2.5:free")
DEEPSEEK_API_KEY   = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL  = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
AI_PROVIDER       = os.getenv("AI_PROVIDER", "gemini").lower()

# ── Personal Career Profile ──────────────────────────────────────────────────
CAREER_PROFILE = """
## Target: Xinyu Tu — Career Profile (AI-Powered Digest Filter)

### Target Roles (Priority Order)
1. AI Platform Engineer
2. GenAI Platform Engineer / Generative AI Platform Engineer
3. Cloud Solution Architect / Enterprise Solution Architect
4. Enterprise Solution Engineer / AI Solution Engineer
5. Staff / Principal Platform Engineer

### Target Companies (Tier 1 — Highest Priority)
- Morgan Stanley, JPMorgan Chase, Goldman Sachs (Financial + AI)
- AWS (Amazon Web Services), Microsoft Azure, Google Cloud
- Databricks, Snowflake
- OpenAI, Anthropic (Stretch)

### Core Skills Match
- Cloud: AWS (Certified), Azure (Expert), GCP
- Infrastructure: Kubernetes (EKS/AKS/GKE), Terraform, Docker, Istio
- AI/ML: LLM orchestration, RAG pipelines, Vector DBs, LangChain
- Languages: Python (production), Go (expert), Java, SQL
- Distributed Systems: Kafka, gRPC, Microservices, Event-Driven Architecture
- Experience: 20+ years, former VP @ JPMC, UBS, BNY

### Strict Exclusions (NEVER recommend these)
- GPU hardware roles: CUDA, NCCL, RDMA, GPU kernel programming
- Pure ML Research roles (PhD required)
- Data Scientist / Analyst roles
- Junior positions (IC1, IC2, entry-level)
- QA / Test Engineer

### Scoring Notes
- A strong match: AI Platform, Cloud Architect, GenAI Infrastructure, LLM Gateway, Enterprise AI
- A good match: Platform Engineering with cloud + Python/Go, Solution Architecture with financial sector
- Weak match: Generic SWE roles without cloud/AI focus, or non-tech roles
"""

# ── Keyword Fallback Filters ─────────────────────────────────────────────────
HIGH_SIGNAL_KEYWORDS = [
    "ai platform", "genai", "generative ai", "llm", "rag",
    "cloud architect", "solution architect", "platform engineer",
    "mlops", "ml platform", "enterprise ai", "ai infrastructure",
    "kubernetes", "terraform", "distributed systems",
    "staff engineer", "principal engineer",
]

EXCLUSION_KEYWORDS = [
    "cuda", "nccl", "rdma", "gpu kernel", "data scientist",
    "data analyst", "junior", "entry level", "qa engineer", "test engineer",
    "phd required", "kernel engineer",
]

TARGET_COMPANIES = [
    "morgan stanley", "jpmorgan", "jp morgan", "goldman sachs",
    "amazon", "aws", "microsoft", "azure", "google", "google cloud",
    "databricks", "snowflake", "openai", "anthropic",
]


# ═══════════════════════════════════════════════════════════════════════════
# AI Scoring Functions
# ═══════════════════════════════════════════════════════════════════════════

def score_with_gemini(jobs: list) -> list:
    """Score a batch of jobs using Gemini Flash API."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
    except ImportError:
        print("  ⚠️  google-generativeai not installed. Run: pip install google-generativeai")
        return score_with_keywords(jobs)
    except Exception as e:
        print(f"  ⚠️  Gemini init failed: {e}. Falling back to keyword scoring.")
        return score_with_keywords(jobs)

    scored = []
    # Batch jobs to avoid token limits: 10 at a time
    batch_size = 10
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        job_list_text = "\n".join([
            f"ID:{j['_id']} | Title:{j.get('title','')} | Company:{j.get('company','')} | "
            f"Location:{j.get('location','')} | Skills:{', '.join(j.get('skills',[])[:8])}"
            for j in batch
        ])

        prompt = f"""You are a job relevance scorer. I will give you a career profile and a list of jobs.
For each job, return a JSON array with objects: {{"id": <ID>, "score": <0-10>, "reason": "<1 sentence>"}}

Score 8-10: Excellent fit (AI Platform Engineer, Cloud Solution Architect, GenAI Infrastructure at top companies)
Score 5-7: Good fit (Platform Engineering with cloud+AI overlap, Solution Engineering at target companies)
Score 1-4: Weak fit (Generic SWE, unrelated to cloud/AI architecture)
Score 0: Exclude immediately (GPU hardware, CUDA, NCCL, data analyst, junior, PhD required)

## CAREER PROFILE
{CAREER_PROFILE}

## JOBS TO SCORE
{job_list_text}

Return ONLY a valid JSON array, no markdown, no explanation outside JSON."""

        try:
            response = model.generate_content(prompt)
            raw = response.text.strip()
            # Strip markdown code fences if present
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
            results = json.loads(raw)

            id_to_score = {str(r['id']): r for r in results}
            for job in batch:
                jid = str(job['_id'])
                ai_result = id_to_score.get(jid, {'score': 3, 'reason': 'Not scored'})
                job['ai_score'] = ai_result.get('score', 3)
                job['ai_reason'] = ai_result.get('reason', '')
                scored.append(job)

        except Exception as e:
            print(f"  ⚠️  Gemini batch error: {e}. Using keyword scoring for this batch.")
            scored.extend(score_with_keywords(batch))

    return scored


def score_with_minimax(jobs: list) -> list:
    """Score jobs using MiniMax API."""
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json",
        }
    except ImportError:
        return score_with_keywords(jobs)

    scored = []
    batch_size = 10
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        job_list_text = "\n".join([
            f"ID:{j['_id']} | Title:{j.get('title','')} | Company:{j.get('company','')}"
            for j in batch
        ])

        payload = {
            "model": "abab6.5s-chat",
            "messages": [
                {"role": "system", "content": "You are a job relevance scorer. Return only valid JSON arrays."},
                {"role": "user", "content": f"Score these jobs 0-10 for this career profile:\n{CAREER_PROFILE}\n\nJOBS:\n{job_list_text}\n\nReturn JSON array: [{{\"id\": <ID>, \"score\": <0-10>, \"reason\": \"<1 sentence>\"}}]"}
            ],
            "max_tokens": 2000,
        }
        try:
            resp = requests.post(
                "https://api.minimax.chat/v1/text/chatcompletion_v2",
                headers=headers,
                json=payload,
                timeout=30,
            )
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
            results = json.loads(raw)
            id_to_score = {str(r['id']): r for r in results}
            for job in batch:
                jid = str(job['_id'])
                ai_result = id_to_score.get(jid, {'score': 3, 'reason': 'Not scored'})
                job['ai_score'] = ai_result.get('score', 3)
                job['ai_reason'] = ai_result.get('reason', '')
                scored.append(job)
        except Exception as e:
            print(f"  ⚠️  MiniMax batch error: {e}. Falling back to keyword scoring.")
            scored.extend(score_with_keywords(batch))

    return scored


def score_with_openrouter(jobs: list) -> list:
    """Score jobs using OpenRouter API."""
    if not OPENROUTER_API_KEY:
        print("  ⚠️  OPENROUTER_API_KEY missing.")
        return score_with_keywords(jobs)
        
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://jobdetector.blackrice.top", # Optional, for OpenRouter rankings
            "X-Title": "JobDetector",
        }
    except ImportError:
        return score_with_keywords(jobs)

    scored = []
    batch_size = 10
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        job_list_text = "\n".join([
            f"ID:{j['_id']} | Title:{j.get('title','')} | Company:{j.get('company','')}"
            for j in batch
        ])

        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": "You are a job relevance scorer. Return only valid JSON arrays."},
                {"role": "user", "content": f"Score these jobs 0-10 for this career profile:\n{CAREER_PROFILE}\n\nJOBS:\n{job_list_text}\n\nReturn JSON array: [{{\"id\": <ID>, \"score\": <0-10>, \"reason\": \"<1 sentence>\"}}]"}
            ],
        }
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=45,
            )
            data = resp.json()
            if "choices" not in data:
                print(f"  ⚠️  OpenRouter Error: {data}")
                scored.extend(score_with_keywords(batch))
                continue
                
            raw = data["choices"][0]["message"]["content"].strip()
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
            results = json.loads(raw)
            id_to_score = {str(r['id']): r for r in results}
            for job in batch:
                jid = str(job['_id'])
                ai_result = id_to_score.get(jid, {'score': 3, 'reason': 'Not scored'})
                job['ai_score'] = ai_result.get('score', 3)
                job['ai_reason'] = ai_result.get('reason', '')
                scored.append(job)
        except Exception as e:
            print(f"  ⚠️  OpenRouter batch error: {e}. Falling back to keyword scoring.")
            scored.extend(score_with_keywords(batch))

    return scored


def score_with_deepseek(jobs: list) -> list:
    """Score jobs using DeepSeek API."""
    if not DEEPSEEK_API_KEY:
        return score_with_keywords(jobs)
        
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
    except ImportError:
        return score_with_keywords(jobs)

    scored = []
    batch_size = 10
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        job_list_text = "\n".join([
            f"ID:{j['_id']} | Title:{j.get('title','')} | Company:{j.get('company','')}"
            for j in batch
        ])

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a job relevance scorer. Return only valid JSON arrays."},
                {"role": "user", "content": f"Score these jobs 0-10 for this career profile:\n{CAREER_PROFILE}\n\nJOBS:\n{job_list_text}\n\nReturn JSON array: [{{\"id\": <ID>, \"score\": <0-10>, \"reason\": \"<1 sentence>\"}}]"}
            ],
        }
        try:
            resp = requests.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=45,
            )
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
            results = json.loads(raw)
            id_to_score = {str(r['id']): r for r in results}
            for job in batch:
                jid = str(job['_id'])
                ai_result = id_to_score.get(jid, {'score': 3, 'reason': 'Not scored'})
                job['ai_score'] = ai_result.get('score', 3)
                job['ai_reason'] = ai_result.get('reason', '')
                scored.append(job)
        except Exception as e:
            print(f"  ⚠️  DeepSeek batch error: {e}. Falling back to keyword scoring.")
            scored.extend(score_with_keywords(batch))

    return scored


def score_with_keywords(jobs: list) -> list:
    """Keyword-based scoring fallback (no API required)."""
    for job in jobs:
        text = f"{job.get('title','')} {job.get('company','')} {' '.join(job.get('skills',[]))}".lower()
        score = 3  # baseline
        reason_parts = []

        # Exclusions first
        for kw in EXCLUSION_KEYWORDS:
            if kw in text:
                score = 0
                reason_parts.append(f"Excluded: contains '{kw}'")
                break

        if score > 0:
            # Boost for high-signal keywords
            for kw in HIGH_SIGNAL_KEYWORDS:
                if kw in text:
                    score = min(10, score + 1.5)
                    reason_parts.append(kw)

            # Boost for target companies
            for co in TARGET_COMPANIES:
                if co in text:
                    score = min(10, score + 1.5)
                    reason_parts.append(f"target co: {co}")
                    break

        job['ai_score'] = round(score, 1)
        job['ai_reason'] = "Keyword match: " + ", ".join(reason_parts[:4]) if reason_parts else "Low signal match"

    return jobs


# ═══════════════════════════════════════════════════════════════════════════
# Email Generation
# ═══════════════════════════════════════════════════════════════════════════

def build_email_html(jobs: list, days: int, ai_provider: str, total_scanned: int) -> str:
    """Build a premium HTML email for the personal digest."""
    today = datetime.now().strftime("%B %d, %Y")
    job_cards = ""

    for i, job in enumerate(jobs, 1):
        score = job.get('ai_score', 0)
        reason = job.get('ai_reason', '')
        title = job.get('title', 'Unknown Title')
        company = job.get('company', 'Unknown Company')
        location = job.get('location', 'Unknown')
        url = job.get('source_url', '#')
        skills = job.get('skills', [])[:6]
        posted = job.get('posted_date', '')
        if hasattr(posted, 'strftime'):
            posted = posted.strftime("%b %d")
        elif isinstance(posted, str) and 'T' in posted:
            posted = posted[:10]

        # Score → badge color
        if score >= 8:
            badge_color = "#22c55e"
            badge_label = "🔥 Strong Match"
        elif score >= 6:
            badge_color = "#38bdf8"
            badge_label = "✅ Good Match"
        else:
            badge_color = "#94a3b8"
            badge_label = "➡ Possible"

        skills_html = "".join([
            f'<span style="display:inline-block;background:rgba(56,189,248,0.15);color:#38bdf8;'
            f'padding:2px 8px;border-radius:4px;font-size:11px;margin:2px;">{s}</span>'
            for s in skills
        ])

        job_cards += f"""
        <div style="background:rgba(30,41,59,0.9);border:1px solid rgba(255,255,255,0.08);
                    border-radius:12px;padding:20px;margin-bottom:16px;border-left:3px solid {badge_color};">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
                <span style="font-size:11px;background:{badge_color}22;color:{badge_color};
                             padding:3px 10px;border-radius:20px;font-weight:600;">{badge_label} ({score}/10)</span>
                <span style="color:#64748b;font-size:11px;">#{i} · {posted}</span>
            </div>
            <a href="{url}" style="text-decoration:none;">
                <h3 style="color:#f1f5f9;font-size:16px;font-weight:700;margin:4px 0;">{title}</h3>
            </a>
            <p style="color:#38bdf8;font-size:13px;font-weight:600;margin:2px 0;">
                {company} &nbsp;·&nbsp; <span style="color:#94a3b8;">{location}</span>
            </p>
            <p style="color:#94a3b8;font-size:12px;font-style:italic;margin:8px 0;">
                AI Insight: {reason}
            </p>
            <div style="margin-top:8px;">{skills_html}</div>
            <div style="margin-top:12px;">
                <a href="{url}" style="background:linear-gradient(135deg,#38bdf8,#818cf8);color:white;
                   text-decoration:none;padding:7px 18px;border-radius:8px;font-size:13px;font-weight:600;">
                   View Job →
                </a>
            </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:'Segoe UI',Arial,sans-serif;">
<div style="max-width:680px;margin:0 auto;padding:20px;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid rgba(56,189,248,0.2);
                border-radius:16px;padding:32px;text-align:center;margin-bottom:24px;">
        <div style="font-size:28px;margin-bottom:8px;">🎯</div>
        <h1 style="color:#f1f5f9;font-size:24px;font-weight:700;margin:0 0 8px;">
            Your Daily Career Digest
        </h1>
        <p style="color:#94a3b8;margin:0;font-size:14px;">{today} · AI Provider: {ai_provider.upper()}</p>
    </div>

    <!-- Stats Bar -->
    <div style="display:flex;gap:12px;margin-bottom:24px;">
        <div style="flex:1;background:rgba(56,189,248,0.1);border:1px solid rgba(56,189,248,0.2);
                    border-radius:10px;padding:14px;text-align:center;">
            <div style="color:#38bdf8;font-size:24px;font-weight:700;">{len(jobs)}</div>
            <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Top Matches</div>
        </div>
        <div style="flex:1;background:rgba(129,140,248,0.1);border:1px solid rgba(129,140,248,0.2);
                    border-radius:10px;padding:14px;text-align:center;">
            <div style="color:#818cf8;font-size:24px;font-weight:700;">{total_scanned}</div>
            <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Jobs Scanned</div>
        </div>
        <div style="flex:1;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.2);
                    border-radius:10px;padding:14px;text-align:center;">
            <div style="color:#22c55e;font-size:24px;font-weight:700;">{days}d</div>
            <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Lookback</div>
        </div>
    </div>

    <!-- Target Roles Reminder -->
    <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);
                border-radius:10px;padding:14px;margin-bottom:24px;">
        <p style="color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:0 0 6px;">
            🎯 Your Targets
        </p>
        <p style="color:#94a3b8;font-size:12px;margin:0;">
            AI Platform Engineer · GenAI Platform Engineer · Cloud Solution Architect ·
            Enterprise Solution Engineer @ Morgan Stanley · JPMC · AWS · GCP · Databricks · Snowflake · OpenAI
        </p>
    </div>

    <!-- Job Cards -->
    <h2 style="color:#f1f5f9;font-size:18px;font-weight:700;margin:0 0 16px;">
        ⚡ Top Matched Opportunities
    </h2>
    {job_cards if job_cards else '<p style="color:#64748b;text-align:center;padding:40px;">No new matching jobs in the last ' + str(days) + ' days.</p>'}

    <!-- Footer -->
        <div style="text-align:center;padding:24px 0;border-top:1px solid rgba(255,255,255,0.05);margin-top:24px;">
            <a href="https://jobdetector.blackrice.top" style="color:#38bdf8;text-decoration:none;font-size:13px;">
                🔍 View All Jobs on JobDetector
            </a>
            <p style="color:#334155;font-size:11px;margin-top:12px;">
                Personal Career Digest · Auto-generated by JobDetector AI Engine
            </p>
            <p style="margin-top: 10px; font-size: 10px; color: #475569;">
                To change your email frequency or unsubscribe, visit your 
                <a href="https://jobdetector.blackrice.top/my_digest.html" style="color: #64748b;">Digest Settings</a>.
            </p>
        </div>

</div>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════
# Email Sender
# ═══════════════════════════════════════════════════════════════════════════

def send_digest_email(to_email: str, html: str, matched_count: int) -> bool:
    if not EMAIL_USER or not EMAIL_PASS:
        print("❌ EMAIL_USERNAME or EMAIL_APP_PASSWORD not set in .env")
        return False
    if not to_email:
        print("❌ RECIPIENT_EMAIL not set in .env")
        return False

    today = datetime.now().strftime("%b %d")
    subject = f"🎯 Career Digest [{today}] — {matched_count} AI-Matched Jobs"

    # Create the plain-text version (fallback)
    text_version = f"JobDetector Career Digest - {today}\n"
    text_version += f"{matched_count} jobs found for your profile.\n\n"
    text_version += "View the full interactive version at https://jobdetector.blackrice.top\n"

    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    
    # Order matters: first attach plain text, then HTML
    msg.attach(MIMEText(text_version, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        print(f"   📧 Attempting to send email to {to_email} via smtp.gmail.com...")
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.set_debuglevel(1)  # Enabled for troubleshooting
            server.starttls()
            print(f"   🔐 Logging in as {EMAIL_USER}...")
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print(f"   ✅ Digest successfully sent to {to_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        print(f"   ❌ SMTP Authentication Failed for {EMAIL_USER}. Check App Password.")
        return False
    except Exception as e:
        print(f"   ❌ Email failed: {type(e).__name__}: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Main Digest Runner
# ═══════════════════════════════════════════════════════════════════════════

def run_all_subscriptions():
    """Find all active subscribers and send digests if due."""
    db = get_db()
    subscribers = list(db.user_digest_settings.find({"is_active": True}))
    
    print(f"\n⏰ Starting Multi-User Scheduler ({len(subscribers)} active subs)")
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for sub in subscribers:
        email = sub["user_email"]
        freq = sub.get("frequency", "daily")
        last_sent = sub.get("last_sent_at")
        
        # Check if due
        is_due = False
        if not last_sent:
            is_due = True
        else:
            delta = now - last_sent
            if freq == "daily" and delta.total_seconds() >= 23 * 3600: # 23h to allow some drift
                is_due = True
            elif freq == "weekly" and delta.days >= 6:
                is_due = True
        
        if is_due:
            print(f"   📬 User {email} is due ({freq}). Running digest...")
            run_digest(days=1 if freq == "daily" else 7, recipient_override=email)
        else:
            print(f"   ⏳ User {email} not due yet (last sent: {last_sent})")

def run_digest(days: int = 1, top_n: int = 15, dry_run: bool = False,
               min_score: float = 5.0, provider_override: str = None,
               recipient_override: str = None) -> dict:
    """
    Main entry point. Returns a result dict with status and matched jobs.
    Can be called from CLI or from the API endpoint.
    """
    provider = (provider_override or AI_PROVIDER).lower()
    print(f"\n🚀 Personal Digest Engine Starting")
    print(f"   Provider: {provider.upper()} | Lookback: {days}d | Top: {top_n} | Min Score: {min_score}")

    db = get_db()
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    # Fetch recent jobs
    recent_jobs = list(
        db.jobs.find({"is_active": True, "posted_date": {"$gte": cutoff}})
        .sort("posted_date", -1)
        .limit(100)  # cap to avoid huge batches and timeouts
    )

    # Stringify ObjectIds for JSON compatibility
    for job in recent_jobs:
        job["_id"] = str(job["_id"])
        if job.get("posted_date") and hasattr(job["posted_date"], "isoformat"):
            job["posted_date"] = job["posted_date"].isoformat()

    total_scanned = len(recent_jobs)
    print(f"   📦 {total_scanned} new jobs found since {cutoff.strftime('%Y-%m-%d %H:%M')} UTC")

    if total_scanned == 0:
        print("   ℹ️  No new jobs. Digest skipped.")
        return {"status": "skipped", "reason": "No new jobs", "matched": 0, "jobs": []}

    # Score jobs
    print(f"   🤖 Scoring with {provider.upper()}...")
    if provider == "gemini" and GEMINI_API_KEY:
        scored_jobs = score_with_gemini(recent_jobs)
    elif provider == "minimax" and MINIMAX_API_KEY:
        # Check if the key looks like an OpenRouter key
        if MINIMAX_API_KEY.startswith("sk-or-"):
            print("   ℹ️  Detected OpenRouter key in MINIMAX_API_KEY, switching to OpenRouter provider.")
            scored_jobs = score_with_openrouter(recent_jobs)
        else:
            scored_jobs = score_with_minimax(recent_jobs)
    elif provider == "openrouter":
        scored_jobs = score_with_openrouter(recent_jobs)
    elif provider == "deepseek":
        scored_jobs = score_with_deepseek(recent_jobs)
    else:
        print(f"   ⚠️  Unsupported provider or API key missing for '{provider}'. Using keyword scoring.")
        scored_jobs = score_with_keywords(recent_jobs)

    # Filter & sort
    matched = [j for j in scored_jobs if j.get("ai_score", 0) >= min_score]
    matched.sort(key=lambda j: j.get("ai_score", 0), reverse=True)
    top_jobs = matched[:top_n]

    print(f"   🎯 {len(matched)} jobs scored ≥ {min_score}, showing top {len(top_jobs)}")

    if dry_run:
        print("\n   [DRY RUN] Email NOT sent. Top matches:")
        for j in top_jobs[:5]:
            print(f"     [{j['ai_score']}/10] {j.get('title')} @ {j.get('company')} — {j.get('ai_reason','')}")
        return {"status": "dry_run", "matched": len(top_jobs), "jobs": top_jobs}

    # Build and send email
    html = build_email_html(top_jobs, days, provider, total_scanned)
    recipient = recipient_override or RECIPIENT_EMAIL
    sent = send_digest_email(recipient, html, len(top_jobs))

    # Log digest run to DB
    try:
        db.digest_log.insert_one({
            "run_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "provider": provider,
            "days_lookback": days,
            "total_scanned": total_scanned,
            "matched_count": len(top_jobs),
            "sent_to": recipient,
            "success": sent,
        })
        # Update user settings if not a manual run/dry run
        if sent and not dry_run:
            db.user_digest_settings.update_one(
                {"user_email": recipient},
                {"$set": {"last_sent_at": datetime.now(timezone.utc).replace(tzinfo=None)}}
            )
    except Exception as e:
        print(f"   ⚠️ Logging error: {e}")

    return {
        "status": "sent" if sent else "email_failed",
        "matched": len(top_jobs),
        "total_scanned": total_scanned,
        "provider": provider,
        "jobs": top_jobs,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Personal AI Job Digest")
    parser.add_argument("--days", type=int, default=1, help="Lookback window in days (default: 1)")
    parser.add_argument("--top", type=int, default=15, help="Max jobs to include in digest (default: 15)")
    parser.add_argument("--min-score", type=float, default=5.0, help="Minimum AI score to include (0-10, default: 5)")
    parser.add_argument("--provider", type=str, default=None, help="AI provider: gemini | minimax | keyword")
    parser.add_argument("--recipient", type=str, default=None, help="Recipient email address")
    parser.add_argument("--dry-run", action="store_true", help="Score and print but do not send email")
    parser.add_argument("--scheduler", action="store_true", help="Run for all active subscribers based on frequency")
    args = parser.parse_args()

    if args.scheduler:
        run_all_subscriptions()
    else:
        result = run_digest(
            days=args.days,
            top_n=args.top,
            dry_run=args.dry_run,
            min_score=args.min_score,
            provider_override=args.provider,
            recipient_override=args.recipient,
        )

        print(f"\n{'='*50}")
        print(f"   Status  : {result['status']}")
        print(f"   Matched : {result['matched']} jobs")
        print(f"{'='*50}\n")
