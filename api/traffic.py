"""First-party traffic metrics; reports are restricted to the configured owner."""
import os
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from api.auth_utils import decode_access_token
from api.billing import _db, _owner, _user

router = APIRouter()
UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class TrafficEvent(BaseModel):
    event_id: str = Field(..., pattern=UUID, max_length=36)
    visitor_id: str = Field(..., pattern=UUID, max_length=36)
    session_id: str = Field(..., pattern=UUID, max_length=36)
    event: Literal["page_view", "search_open", "subscribe_click"]
    page: str = Field(..., max_length=160, pattern=r"^/[A-Za-z0-9_./-]*$")
    referrer: str = Field(default="", max_length=400)
    preset_id: str = Field(default="", max_length=100, pattern=r"^[a-z0-9-]*$")
    plan: Literal["monthly", "annual"] = "monthly"


def require_owner(request):
    user = _user(request)
    if not _owner(user):
        raise HTTPException(403, "This report is available only to Tuxy.")
    return user


@router.post("/api/traffic/event", status_code=202)
def record_event(data: TrafficEvent, request: Request):
    agent = request.headers.get("user-agent", "").lower()
    if any(bot in agent for bot in ("bot", "crawler", "spider", "headless")):
        return {"accepted": False}
    authorization = request.headers.get("Authorization", "")
    payload = decode_access_token(authorization[7:]) if authorization.startswith("Bearer ") else None
    configured = os.getenv("ADMIN_EMAIL", "")
    is_owner = bool(payload and configured and str(payload.get("sub", "")).lower() == configured.lower())
    try:
        _db().traffic_events.insert_one({
            "_id": data.event_id, "timestamp": datetime.now(timezone.utc),
            "visitor_id": data.visitor_id, "session_id": data.session_id, "event": data.event,
            "page": data.page, "source": urlparse(data.referrer).hostname or "direct",
            "preset_id": data.preset_id, "plan": data.plan, "is_owner": is_owner,
        })
    except DuplicateKeyError:
        pass
    return {"accepted": True}


@router.get("/api/traffic/admin")
def traffic_report(request: Request, response: Response, days: int = Query(30, ge=1, le=90), include_owner: bool = False):
    require_owner(request)
    response.headers["Cache-Control"] = "private, no-store"
    db = _db()
    now = datetime.now(timezone.utc)
    start_local = (now.astimezone(ZoneInfo("America/New_York")) - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    start = start_local.astimezone(timezone.utc)
    match = {"timestamp": {"$gte": start}}
    if not include_owner:
        match["is_owner"] = {"$ne": True}
    events = db.traffic_events
    views = {**match, "event": "page_view"}

    def top(field, event, limit=10):
        return [{"label": row["_id"] or "unknown", "count": row["count"]} for row in events.aggregate([
            {"$match": {**match, "event": event}}, {"$group": {"_id": "$" + field, "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}}, {"$limit": limit},
        ])]

    daily = {row["_id"]: row for row in events.aggregate([
        {"$match": match}, {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp", "timezone": "America/New_York"}},
            "views": {"$sum": {"$cond": [{"$eq": ["$event", "page_view"]}, 1, 0]}},
            "searches": {"$sum": {"$cond": [{"$eq": ["$event", "search_open"]}, 1, 0]}}}},
    ])}
    trend = []
    for offset in range(days):
        day = (start_local + timedelta(days=offset)).strftime("%Y-%m-%d")
        trend.append({"date": day, "views": daily.get(day, {}).get("views", 0), "searches": daily.get(day, {}).get("searches", 0)})
    checkout_match = {"type": "checkout.created", "processed_at": {"$gte": start}, "livemode": True}
    paid_match = {"billing_first_paid_at": {"$gte": start}}
    active_match = {"billing.status": "active", "billing.livemode": True}
    if not include_owner:
        checkout_match["is_owner"] = {"$ne": True}
        paid_match["billing.is_owner"] = {"$ne": True}
        active_match["billing.is_owner"] = {"$ne": True}
        owner_email = os.getenv("ADMIN_EMAIL", "")
        if owner_email:
            paid_match["email"] = {"$ne": owner_email}
            active_match["email"] = {"$ne": owner_email}
    first = events.find_one({}, sort=[("timestamp", 1)])
    return {
        "days": days, "timezone": "America/New_York", "generated_at": now.isoformat(), "include_owner": include_owner,
        "tracking_since": first["timestamp"].replace(tzinfo=timezone.utc).isoformat() if first else None,
        "summary": {
            "page_views": events.count_documents(views),
            "unique_visitors": len(events.distinct("visitor_id", views)),
            "sessions": len(events.distinct("session_id", views)),
            "search_clicks": events.count_documents({**match, "event": "search_open"}),
            "subscribe_clicks": events.count_documents({**match, "event": "subscribe_click"}),
            "checkouts_started": db.billing_events.count_documents(checkout_match),
            "new_paying_users": db.users.count_documents(paid_match),
            "active_subscribers": db.users.count_documents(active_match),
            "monthly_subscribers": db.users.count_documents({**active_match, "billing.plan": "monthly"}),
            "annual_subscribers": db.users.count_documents({**active_match, "billing.plan": "annual"}),
        }, "daily": trend, "top_pages": top("page", "page_view"),
        "top_sources": top("source", "page_view"), "top_searches": top("preset_id", "search_open"),
    }
