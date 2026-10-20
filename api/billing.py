"""Stripe-hosted subscription checkout and server-side Search Console access."""
import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from api.auth_utils import decode_access_token

router = APIRouter()
logger = logging.getLogger(__name__)
PRODUCT_ID = "prod_VTQVFnqvuTNwG0"
PLANS = {"monthly": {"amount": 100, "interval": "month", "env": "STRIPE_MONTHLY_PRICE_ID", "price_id": "price_1USTeLFC3kxu6kUOBgyDTB6A"},
         "annual": {"amount": 999, "interval": "year", "env": "STRIPE_ANNUAL_PRICE_ID", "price_id": "price_1USTfIFC3kxu6kUOZksDu146"}}
APP_NAME = "jobdetector-search"


class CheckoutPlan(BaseModel):
    plan: Literal["monthly", "annual"] = "monthly"


def _enabled():
    return os.getenv("BILLING_ENABLED", "false").lower() == "true"


def _ready():
    return _enabled() and _configured()


def _configured():
    return all(os.getenv(name) for name in (
        "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"))


def _price_id(plan):
    return os.getenv(PLANS[plan]["env"]) or PLANS[plan]["price_id"]


@lru_cache(maxsize=1)
def _db():
    from api.db import get_db
    return get_db()


def _client(allow_disabled=False):
    if not _configured() or (not allow_disabled and not _enabled()):
        raise HTTPException(503, "Subscriptions are not available yet. Please try again later.")
    import stripe
    return stripe.StripeClient(os.environ["STRIPE_SECRET_KEY"], max_network_retries=1,
                               http_client=stripe.RequestsClient(timeout=10))


def _base_url():
    value = os.getenv("BASE_URL", "https://jobdetector.blackrice.top").rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")):
        raise HTTPException(503, "Billing return URL is not configured correctly.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(503, "Billing return URL is not configured correctly.")
    return value


def _user(request, required=True):
    authorization = request.headers.get("Authorization", "")
    if not authorization:
        if required:
            raise HTTPException(401, "Sign in to subscribe.")
        return None
    payload = decode_access_token(authorization[7:]) if authorization.startswith("Bearer ") else None
    if not payload or not isinstance(payload.get("sub"), str):
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    user = _db().users.find_one({"email": payload["sub"]})
    if not user or not user.get("is_active", True) or not user.get("is_verified", False):
        raise HTTPException(401, "Please sign in with a verified account.")
    return user


def _admin(user):
    configured = os.getenv("ADMIN_EMAIL", "")
    return bool(user and (user.get("is_admin") or (configured and user["email"].lower() == configured.lower())))


def _owner(user):
    configured = os.getenv("ADMIN_EMAIL", "")
    return bool(user and configured and user["email"].lower() == configured.lower())


def _stripe_call(operation, *args, **kwargs):
    try:
        result = operation(*args, **kwargs)
        # Stripe 16 resources are not dicts. Keep paged lists intact until iteration.
        import stripe
        if isinstance(result, stripe.StripeObject) and not isinstance(result, stripe.ListObject):
            return result.to_dict()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        # Never return provider errors, API keys, or payment/customer data to the client.
        logger.warning("Stripe request failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Stripe is temporarily unavailable. Please try again.") from None


def _validate_price(client, plan):
    expected = PLANS[plan]
    price = _stripe_call(client.v1.prices.retrieve, _price_id(plan))
    recurring = price.get("recurring") or {}
    if not (price.get("active") and price.get("product") == os.getenv("STRIPE_PRODUCT_ID", PRODUCT_ID)
            and price.get("currency") == "usd" and price.get("unit_amount") == expected["amount"]
            and recurring.get("interval") == expected["interval"] and recurring.get("interval_count") == 1
            and recurring.get("usage_type") == "licensed"):
        raise HTTPException(503, "The subscription price has not been configured correctly.")
    return price


def _customer(client, user):
    if user.get("stripe_customer_id"):
        return user["stripe_customer_id"]
    user_id = str(user["_id"])
    customer = _stripe_call(client.v1.customers.create,
                            {"email": user["email"], "metadata": {"app": APP_NAME, "user_id": user_id}},
                            options={"idempotency_key": "jd-customer-" + hashlib.sha256(user_id.encode()).hexdigest()})
    _db().users.update_one({"_id": user["_id"]}, {"$set": {"stripe_customer_id": customer["id"]}})
    user["stripe_customer_id"] = customer["id"]
    return customer["id"]


def _our_subscription(subscription):
    return (subscription.get("metadata") or {}).get("app") == APP_NAME and any(
        (item.get("price") or {}).get("id") in [_price_id(plan) for plan in PLANS]
        for item in (subscription.get("items") or {}).get("data", []))


def _sync_customer(client, customer_id):
    """Read current Stripe state, rather than trusting an out-of-order webhook payload."""
    user = _db().users.find_one({"stripe_customer_id": customer_id})
    if not user:
        return {"subscribed": False, "status": "none", "cancel_at_period_end": False, "period_end": None}
    subscriptions = _stripe_call(client.v1.subscriptions.list,
                                 {"customer": customer_id, "status": "all", "limit": 100})
    rows = _stripe_call(lambda: [sub if isinstance(sub, dict) else sub.to_dict() for sub in subscriptions.auto_paging_iter()])
    candidates = [sub for sub in rows if _our_subscription(sub)]
    candidates.sort(key=lambda sub: (sub.get("status") == "active", sub.get("created", 0)), reverse=True)
    subscription = candidates[0] if candidates else {}
    period_end = subscription.get("current_period_end") or max(
        (item.get("current_period_end", 0) for item in (subscription.get("items") or {}).get("data", [])), default=0)
    result = {
        "subscribed": subscription.get("status") == "active",
        "status": subscription.get("status", "none"),
        "cancel_at_period_end": bool(subscription.get("cancel_at_period_end")),
        "period_end": period_end or None,
        "plan": next((name for name, plan in PLANS.items() if any(
            (item.get("price") or {}).get("id") == _price_id(name)
            for item in (subscription.get("items") or {}).get("data", []))), None),
        "livemode": bool(subscription.get("livemode")),
        "is_owner": _owner(user),
    }
    _db().users.update_one({"_id": user["_id"]}, {"$set": {
        "billing": {**result, "subscription_id": subscription.get("id"), "updated_at": datetime.now(timezone.utc)},
    }})
    if result["subscribed"] and result["livemode"]:
        _db().users.update_one({"_id": user["_id"], "billing_first_paid_at": {"$exists": False}},
                              {"$set": {"billing_first_paid_at": datetime.now(timezone.utc)}})
    return result


def access_for(user):
    if not _enabled() or _admin(user):
        return True
    if not user or not _ready() or not user.get("stripe_customer_id"):
        return False
    return _sync_customer(_client(), user["stripe_customer_id"])["subscribed"]


@router.get("/api/billing/status")
def billing_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    user = _user(request, required=False)
    result = {"enabled": _enabled(), "checkout_available": _ready(), "authenticated": bool(user),
              "is_owner": _owner(user), "test_mode": bool(os.getenv("STRIPE_SECRET_KEY", "").startswith(("sk_test_", "rk_test_"))),
              "full_access": not _enabled() or _admin(user), "subscribed": False,
              "plans": {name: {"unit_amount": plan["amount"], "currency": "usd", "interval": plan["interval"]} for name, plan in PLANS.items()},
              "status": "none", "cancel_at_period_end": False, "period_end": None}
    if user and _ready() and user.get("stripe_customer_id"):
        result.update(_sync_customer(_client(), user["stripe_customer_id"]))
        result["full_access"] = result["subscribed"] or _admin(user)
    return result


@router.post("/api/billing/checkout")
def create_checkout(request: Request, selection: CheckoutPlan):
    user = _user(request)
    client = _client()
    plan = selection.plan
    _validate_price(client, plan)
    users = _db().users
    now = datetime.now(timezone.utc)
    # Serialize a user's checkout creation, including requests from multiple tabs.
    locked = users.update_one({"_id": user["_id"], "$or": [
        {"billing_checkout_lock_until": {"$exists": False}}, {"billing_checkout_lock_until": {"$lt": now}}
    ]}, {"$set": {"billing_checkout_lock_until": now + timedelta(seconds=90)}})
    if not locked.modified_count:
        raise HTTPException(409, "Checkout is already opening. Please wait a moment and try again.")
    try:
        customer_id = _customer(client, user)
        subscriptions = _sync_customer(client, customer_id)
        if subscriptions["subscribed"]:
            raise HTTPException(409, "You already have a subscription. Use Manage subscription.")
        # Reuse an unfinished Checkout Session instead of creating parallel subscriptions.
        pending = user.get("stripe_checkout_session_id")
        if pending:
            session = _stripe_call(client.v1.checkout.sessions.retrieve, pending)
            if session.get("status") == "open" and session.get("customer") == customer_id and session.get("url"):
                if user.get("stripe_checkout_plan") == plan:
                    return {"url": session["url"]}
                _stripe_call(client.v1.checkout.sessions.expire, pending)
        user_id = str(user["_id"])
        attempt = user.get("stripe_checkout_attempt") if not pending else None
        attempt = attempt or secrets.token_urlsafe(18)
        users.update_one({"_id": user["_id"]}, {"$set": {"stripe_checkout_attempt": attempt}})
        session = _stripe_call(client.v1.checkout.sessions.create, {
            "mode": "subscription", "customer": customer_id,
            "payment_method_types": ["card"],
            "line_items": [{"price": _price_id(plan), "quantity": 1}],
            "client_reference_id": user_id,
            "metadata": {"app": APP_NAME, "user_id": user_id},
            "subscription_data": {"metadata": {"app": APP_NAME, "user_id": user_id}},
            "success_url": _base_url() + "/linkedin-search.html?billing=success",
            "cancel_url": _base_url() + "/linkedin-search.html?billing=cancelled",
        }, options={"idempotency_key": f"jd-checkout-{user_id}-{plan}-{attempt}"})
        users.update_one({"_id": user["_id"]}, {"$set": {"stripe_checkout_session_id": session["id"], "stripe_checkout_plan": plan}})
        _db().billing_events.update_one({"_id": "checkout-" + session["id"]}, {"$setOnInsert": {
            "type": "checkout.created", "processed_at": datetime.now(timezone.utc),
            "livemode": bool(session.get("livemode")), "is_owner": _owner(user), "plan": plan,
        }}, upsert=True)
        return {"url": session["url"]}
    finally:
        users.update_one({"_id": user["_id"]}, {"$unset": {"billing_checkout_lock_until": ""}})


@router.post("/api/billing/portal")
def customer_portal(request: Request):
    user = _user(request)
    client = _client()
    if not user.get("stripe_customer_id"):
        raise HTTPException(400, "You do not have a billing account yet.")
    # Use an app-specific portal configuration rather than changing shared account defaults.
    settings = _db().billing_settings.find_one({"_id": APP_NAME})
    configuration_id = os.getenv("STRIPE_PORTAL_CONFIGURATION_ID") or (settings or {}).get("portal_configuration_id")
    if os.getenv("STRIPE_PORTAL_CONFIGURATION_ID"):
        configuration = _stripe_call(client.v1.billing_portal.configurations.retrieve, configuration_id)
        if (configuration.get("metadata") or {}).get("app") != APP_NAME:
            raise HTTPException(503, "The JobDetector billing portal is not configured correctly.")
    if not configuration_id:
        configuration = _stripe_call(client.v1.billing_portal.configurations.create, {
            "business_profile": {"headline": "Manage your JobDetector subscription"},
            "features": {"invoice_history": {"enabled": True}, "payment_method_update": {"enabled": True},
                         "subscription_cancel": {"enabled": True, "mode": "at_period_end"}},
            "metadata": {"app": APP_NAME},
        }, options={"idempotency_key": "jd-portal-configuration-v1"})
        configuration_id = configuration["id"]
        _db().billing_settings.update_one({"_id": APP_NAME}, {"$set": {"portal_configuration_id": configuration_id}}, upsert=True)
    session = _stripe_call(client.v1.billing_portal.sessions.create, {
        "customer": user["stripe_customer_id"], "configuration": configuration_id,
        "return_url": _base_url() + "/linkedin-search.html",
    })
    return {"url": session["url"]}


def _process_event(event):
    event_type = event["type"]
    supported = {"checkout.session.completed", "checkout.session.async_payment_succeeded",
                 "checkout.session.async_payment_failed", "customer.subscription.created",
                 "customer.subscription.updated", "customer.subscription.deleted",
                 "invoice.paid", "invoice.payment_failed"}
    if event_type not in supported:
        return
    customer_id = event["data"]["object"].get("customer")
    if not isinstance(customer_id, str):
        return
    _sync_customer(_client(allow_disabled=True), customer_id)
    _db().billing_events.update_one({"_id": event["id"]}, {"$setOnInsert": {
        "type": event_type, "processed_at": datetime.now(timezone.utc),
    }}, upsert=True)


@router.post("/api/billing/webhook")
async def stripe_webhook(request: Request):
    if not _configured():
        raise HTTPException(503, "Billing is not configured.")
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(413, "Webhook payload too large.")
    import stripe
    try:
        event = stripe.Webhook.construct_event(body, request.headers.get("Stripe-Signature", ""),
                                                os.environ["STRIPE_WEBHOOK_SECRET"], tolerance=300)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(400, "Invalid webhook signature.") from None
    await run_in_threadpool(_process_event, event.to_dict())
    return {"received": True}


@lru_cache(maxsize=1)
def _catalog():
    return json.loads((Path(__file__).resolve().parent.parent / "data" / "linkedin_search_presets.json").read_text())


@router.get("/api/linkedin/presets")
def search_presets(request: Request, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    user = _user(request, required=False) if _enabled() else None
    full_access = access_for(user)
    catalog = _catalog()
    groups = [{**group, "total": len(group["items"]), "items": group["items"] if full_access else group["items"][:1]}
              for group in catalog["groups"]]
    return {"groups": groups, "signals": catalog["signals"] if full_access else [],
            "full_access": full_access, "total": sum(len(group["items"]) for group in catalog["groups"]) + len(catalog["signals"])}


@router.get("/api/billing/admin-summary")
def billing_summary(request: Request):
    user = _user(request)
    if not _owner(user):
        raise HTTPException(403, "Admin access required.")
    users = _db().users
    return {"active_subscriptions": users.count_documents({"billing.status": "active"}),
            "monthly_subscriptions": users.count_documents({"billing.status": "active", "billing.plan": "monthly"}),
            "annual_subscriptions": users.count_documents({"billing.status": "active", "billing.plan": "annual"}),
            "payment_issues": users.count_documents({"billing.status": "past_due"}),
            "cancel_at_period_end": users.count_documents({"billing.status": "active", "billing.cancel_at_period_end": True})}


@router.post("/api/billing/preflight")
def billing_preflight(request: Request):
    if not _owner(_user(request)):
        raise HTTPException(403, "Only Tuxy can check billing setup.")
    client = _client(allow_disabled=True)
    prices = {plan: _validate_price(client, plan) for plan in PLANS}
    return {"enabled": _enabled(), "mode": "live" if all(price.get("livemode") for price in prices.values()) else "test",
            "product": os.getenv("STRIPE_PRODUCT_ID", PRODUCT_ID), "webhook_secret_configured": bool(os.getenv("STRIPE_WEBHOOK_SECRET")),
            "plans": {plan: {"price_id": price["id"], "unit_amount": price["unit_amount"], "currency": price["currency"],
                             "interval": price["recurring"]["interval"]} for plan, price in prices.items()}}
