#!/usr/bin/env python3
"""
keyword_alert.py — User-specific Keyword Job Alert Engine
==========================================================
Reads each user's alert settings from `user_alert_settings` collection,
finds jobs matching their keywords since last alert, and sends an HTML
email at their configured frequency (daily / weekly).

Usage:
    python scripts/keyword_alert.py                  # Run all due alerts
    python scripts/keyword_alert.py --dry-run        # Preview only, no email sent
    python scripts/keyword_alert.py --user you@email # Run for a specific user only
    python scripts/keyword_alert.py --force          # Ignore frequency check, send all active
"""

import os
import sys
import re
import smtplib
import argparse
import logging
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.database.connection import get_db
from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/keyword_alert.log", mode="a"),
    ],
)
log = logging.getLogger(__name__)

# ── Email credentials ─────────────────────────────────────────────────────────
EMAIL_USER = os.getenv("EMAIL_USERNAME")
EMAIL_PASS = os.getenv("EMAIL_APP_PASSWORD")
APP_BASE_URL = os.getenv("BASE_URL", "https://jobdetector.vercel.app")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an HTML email via Gmail SMTP."""
    if not EMAIL_USER or not EMAIL_PASS:
        log.error("Email credentials (EMAIL_USERNAME / EMAIL_APP_PASSWORD) not set.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)

        log.info(f"✅ Email sent → {to_email}")
        return True
    except Exception as exc:
        log.error(f"❌ Failed to send email to {to_email}: {exc}")
        return False


def _is_due(settings: dict, now: datetime) -> bool:
    """Return True if this alert subscription is due for a send."""
    frequency = settings.get("frequency", "off")
    if frequency == "off" or not settings.get("is_active", False):
        return False

    last_sent = settings.get("last_sent_at")
    if not last_sent:
        return True  # Never sent → always due

    # Ensure naive datetime comparison
    if hasattr(last_sent, "tzinfo") and last_sent.tzinfo:
        last_sent = last_sent.replace(tzinfo=None)

    if frequency == "daily":
        return (now - last_sent) >= timedelta(hours=20)   # ~1 day with 4h buffer
    if frequency == "weekly":
        return (now - last_sent) >= timedelta(days=6)     # ~7 days with 1d buffer
    return False


def _lookback_cutoff(settings: dict, now: datetime) -> datetime:
    """Return the earliest posted_date to include in this alert."""
    last_sent = settings.get("last_sent_at")
    if last_sent:
        if hasattr(last_sent, "tzinfo") and last_sent.tzinfo:
            last_sent = last_sent.replace(tzinfo=None)
        return last_sent

    # First run: use frequency as fallback window
    frequency = settings.get("frequency", "daily")
    days = 7 if frequency == "weekly" else 1
    return now - timedelta(days=days)


def _find_matching_jobs(db, keywords: list[str], cutoff: datetime, limit: int = 20) -> list:
    """
    Query jobs posted since `cutoff` that match ANY of the keywords
    in title, description, or skills fields.
    """
    if not keywords:
        return []

    keyword_conditions = []
    for kw in keywords:
        escaped = re.escape(kw.strip())
        if not escaped:
            continue
        keyword_conditions.append({
            "$or": [
                {"title":       {"$regex": escaped, "$options": "i"}},
                {"description": {"$regex": escaped, "$options": "i"}},
                {"skills":      {"$in": [re.compile(escaped, re.I)]}},
            ]
        })

    if not keyword_conditions:
        return []

    query = {
        "is_active": True,
        "posted_date": {"$gte": cutoff},
        "$or": keyword_conditions,   # ANY keyword match
    }

    jobs = list(db.jobs.find(query).sort("posted_date", -1).limit(limit))
    return jobs


def _build_email_html(jobs: list, user_settings: dict) -> str:
    """Render a premium HTML email body."""
    keywords      = user_settings.get("keywords", [])
    frequency     = user_settings.get("frequency", "daily").capitalize()
    unsubscribe_url = f"{APP_BASE_URL}/my_digest.html"

    kw_pills = "".join(
        f'<span style="display:inline-block;background:#1e3a5f;color:#38bdf8;'
        f'padding:3px 10px;border-radius:20px;font-size:12px;margin:2px;">{kw}</span>'
        for kw in keywords
    )

    job_rows = ""
    for job in jobs:
        title     = job.get("title", "Untitled Role")
        company   = job.get("company", "Unknown Company")
        location  = job.get("location", "—")
        url       = job.get("source_url", "#")
        raw_date  = job.get("posted_date")
        date_str  = raw_date.strftime("%b %d") if hasattr(raw_date, "strftime") else "Recent"

        job_rows += f"""
        <tr>
          <td style="padding:14px 0;border-bottom:1px solid #1e293b;">
            <a href="{url}" style="font-size:15px;font-weight:700;color:#38bdf8;text-decoration:none;">{title}</a>
            <div style="margin-top:4px;font-size:13px;color:#94a3b8;">
              <strong style="color:#cbd5e1;">{company}</strong>
              &nbsp;·&nbsp;{location}
              &nbsp;·&nbsp;<span style="color:#64748b;">{date_str}</span>
            </div>
          </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JobDetector Keyword Alert</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;font-family:'Segoe UI',Arial,sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:30px 0;">
    <tr>
      <td align="center">
        <table width="620" cellpadding="0" cellspacing="0" style="max-width:620px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#0f4c81,#1e40af);border-radius:14px 14px 0 0;padding:32px 36px;text-align:center;">
              <div style="font-size:13px;letter-spacing:3px;color:#93c5fd;text-transform:uppercase;margin-bottom:8px;">📡 JobDetector</div>
              <h1 style="margin:0;font-size:26px;color:#ffffff;font-weight:800;">Your {frequency} Job Alert</h1>
              <p style="margin:10px 0 0;font-size:14px;color:#bfdbfe;">
                {len(jobs)} new job{"s" if len(jobs) != 1 else ""} matching your keywords
              </p>
            </td>
          </tr>

          <!-- Keywords -->
          <tr>
            <td style="background:#0d1f3c;padding:16px 36px;border-left:3px solid #1e3a5f;border-right:3px solid #1e3a5f;">
              <p style="margin:0 0 8px;font-size:11px;letter-spacing:2px;color:#64748b;text-transform:uppercase;">Matching Keywords</p>
              {kw_pills}
            </td>
          </tr>

          <!-- Job List -->
          <tr>
            <td style="background:#0f172a;border:3px solid #1e3a5f;border-top:none;padding:0 36px 10px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                {job_rows}
              </table>
            </td>
          </tr>

          <!-- CTA -->
          <tr>
            <td style="background:#0f172a;border:3px solid #1e3a5f;border-top:none;padding:20px 36px 30px;text-align:center;">
              <a href="{APP_BASE_URL}" style="display:inline-block;padding:12px 32px;background:linear-gradient(135deg,#0284c7,#7c3aed);color:#ffffff;font-weight:700;font-size:14px;border-radius:8px;text-decoration:none;">
                🔍 View All Jobs on JobDetector
              </a>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#060d1a;border-radius:0 0 14px 14px;padding:20px 36px;text-align:center;">
              <p style="margin:0;font-size:11px;color:#475569;">
                You're receiving this because you enabled <strong style="color:#94a3b8;">Keyword Job Alerts</strong> on JobDetector.<br>
                <a href="{unsubscribe_url}" style="color:#38bdf8;text-decoration:none;">Manage alerts or unsubscribe</a>
                &nbsp;·&nbsp;
                <span style="color:#334155;">© 2026 JobDetector</span>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    return html


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_alerts(dry_run: bool = False, target_user: str = None, force: bool = False):
    db  = get_db()
    now = datetime.utcnow()

    query = {"is_active": True}
    if target_user:
        query["user_email"] = target_user

    alert_settings_list = list(db.user_alert_settings.find(query))
    log.info(f"Found {len(alert_settings_list)} active alert subscription(s).")

    sent_count = 0
    skipped_count = 0

    for settings in alert_settings_list:
        user_email = settings.get("user_email")
        keywords   = [k.strip() for k in settings.get("keywords", []) if k.strip()]
        alert_email = settings.get("alert_email") or user_email  # custom delivery address

        if not keywords:
            log.info(f"  ⏭ Skipping {user_email}: no keywords defined.")
            skipped_count += 1
            continue

        if not force and not _is_due(settings, now):
            freq = settings.get("frequency", "?")
            log.info(f"  ⏭ Skipping {user_email}: not due yet (frequency={freq}).")
            skipped_count += 1
            continue

        cutoff   = _lookback_cutoff(settings, now)
        log.info(f"  🔍 {user_email} | keywords={keywords} | cutoff={cutoff.date()} → {alert_email}")

        jobs = _find_matching_jobs(db, keywords, cutoff)
        log.info(f"     Found {len(jobs)} matching job(s).")

        if not jobs:
            log.info("     No new jobs found — skipping email.")
            # Still update last_sent_at so we don't re-check too eagerly
            if not dry_run:
                db.user_alert_settings.update_one(
                    {"_id": settings["_id"]},
                    {"$set": {"last_sent_at": now, "last_matched_count": 0}}
                )
            skipped_count += 1
            continue

        subject  = f"🔔 JobDetector: {len(jobs)} New Job{'s' if len(jobs)!=1 else ''} Matching Your Keywords"
        html_body = _build_email_html(jobs, settings)

        if dry_run:
            log.info(f"     [DRY RUN] Would send to {alert_email} — subject: {subject}")
            sent_count += 1
        else:
            success = _send_email(alert_email, subject, html_body)
            if success:
                db.user_alert_settings.update_one(
                    {"_id": settings["_id"]},
                    {"$set": {
                        "last_sent_at": now,
                        "last_matched_count": len(jobs),
                        "total_emails_sent": (settings.get("total_emails_sent", 0) + 1)
                    }}
                )
                sent_count += 1
            else:
                skipped_count += 1

    log.info(f"\n✅ Done. Sent={sent_count} | Skipped/No-Match={skipped_count}")
    return sent_count


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JobDetector Keyword Alert Engine")
    parser.add_argument("--dry-run",  action="store_true", help="Preview alerts without sending emails")
    parser.add_argument("--force",    action="store_true", help="Ignore frequency window and send all active alerts")
    parser.add_argument("--user",     type=str, default=None, help="Run for a specific user email only")
    args = parser.parse_args()

    run_alerts(dry_run=args.dry_run, target_user=args.user, force=args.force)
