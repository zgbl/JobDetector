"""Owner-only subscription ledger read directly from Stripe."""
import re
import os
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Request, Response

from api.billing import PLANS, _client, _db, _price_id, _stripe_call
from api.traffic import require_owner

router = APIRouter()
SCAN_LIMIT = 2000


def _dict(value):
    return value if isinstance(value, dict) else value.to_dict()


def _items(sub):
    prices = {_price_id(name): name for name in PLANS}
    return [(item, prices[item['price']['id']]) for item in (sub.get('items') or {}).get('data', [])
            if isinstance(item.get('price'), dict) and item['price'].get('id') in prices]


def _invoice(row):
    return {key: row.get(key) for key in ('id', 'number', 'status', 'currency', 'total', 'amount_paid',
                                         'amount_remaining', 'created', 'due_date', 'hosted_invoice_url', 'invoice_pdf')} | {
        'paid_at': (row.get('status_transitions') or {}).get('paid_at')}


def _row(sub, users):
    items = _items(sub)
    customer = sub.get('customer') or {}
    customer = customer if isinstance(customer, dict) else {'id': customer}
    user = users.get(customer.get('id'), {})
    item, plan = items[0]
    price = item['price']
    amount = sum((i['price'].get('unit_amount') or 0) * (i.get('quantity') or 1) for i, _ in items)
    period_end = min((i.get('current_period_end') or sub.get('current_period_end') or 0 for i, _ in items), default=0)
    period_start = min((i.get('current_period_start') or sub.get('current_period_start') or 0 for i, _ in items), default=0)
    cancel_at = sub.get('cancel_at')
    renewal_off = bool(sub.get('cancel_at_period_end') or cancel_at)
    end = min(period_end, cancel_at) if period_end and cancel_at else cancel_at or period_end
    invoice = sub.get('latest_invoice')
    return {
        'id': sub['id'], 'customer_id': customer.get('id'),
        'email': user.get('email') or customer.get('email') or '',
        'name': user.get('full_name') or user.get('name') or user.get('username') or customer.get('name') or '',
        'registered': bool(user), 'plan': plan, 'unit_amount': amount,
        'currency': price.get('currency', 'usd'), 'status': sub.get('status'),
        'created': sub.get('created'), 'period_start': period_start or None,
        'period_end': end or None, 'cancel_at_period_end': renewal_off,
        'ended_at': sub.get('ended_at'), 'canceled_at': sub.get('canceled_at'),
        'has_access': sub.get('status') == 'active', 'livemode': bool(sub.get('livemode')),
        'latest_invoice': _invoice(invoice) if isinstance(invoice, dict) else None,
    }


@router.get('/api/billing/admin/subscriptions')
def subscriptions(request: Request, response: Response):
    require_owner(request)
    response.headers['Cache-Control'] = 'private, no-store'
    client = _client(allow_disabled=True)
    page = _stripe_call(client.v1.subscriptions.list, {'status': 'all', 'limit': 100,
                        'expand': ['data.customer', 'data.latest_invoice']})

    def collect():
        result = []
        scanned = 0
        truncated = False
        for value in page.auto_paging_iter():
            if scanned >= SCAN_LIMIT:
                truncated = True
                break
            scanned += 1
            sub = _dict(value)
            if _items(sub):
                result.append(sub)
        return result, truncated

    raw, truncated = _stripe_call(collect)
    ids = [s['customer']['id'] if isinstance(s.get('customer'), dict) else s.get('customer') for s in raw]
    users = {u['stripe_customer_id']: u for u in _db().users.find(
        {'stripe_customer_id': {'$in': ids}}, {'email': 1, 'full_name': 1, 'name': 1, 'username': 1, 'stripe_customer_id': 1})} if ids else {}
    rows = [_row(s, users) for s in raw]
    now = int(datetime.now(timezone.utc).timestamp())
    active = [r for r in rows if r['status'] == 'active']
    recurring = [r for r in active if not r['cancel_at_period_end']]
    mrr = sum((Decimal(r['unit_amount']) / (12 if r['plan'] == 'annual' else 1) for r in recurring), Decimal(0))
    summary = {
        'total': len(rows), 'active': len(active),
        'monthly': sum(r['plan'] == 'monthly' for r in active),
        'annual': sum(r['plan'] == 'annual' for r in active),
        'ending': sum(r['cancel_at_period_end'] for r in active),
        'due_soon': sum(now <= (r['period_end'] or 0) <= now + 7 * 86400 for r in active),
        'payment_issues': sum(r['status'] in ('past_due', 'unpaid', 'incomplete', 'paused') for r in rows),
        'mrr_cents': int(mrr.quantize(Decimal('1'))),
    }
    rows.sort(key=lambda r: r['created'] or 0, reverse=True)
    return {'rows': rows, 'summary': summary, 'truncated': truncated,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'mode': 'live' if os.getenv('STRIPE_SECRET_KEY', '').startswith(('sk_live_', 'rk_live_')) else 'test'}


@router.get('/api/billing/admin/subscriptions/{subscription_id}/invoices')
def subscription_invoices(subscription_id: str, request: Request, response: Response,
                          starting_after: str = Query('', max_length=120)):
    require_owner(request)
    response.headers['Cache-Control'] = 'private, no-store'
    if not re.fullmatch(r'sub_[A-Za-z0-9]+', subscription_id):
        raise HTTPException(400, 'Invalid subscription ID.')
    if starting_after and not re.fullmatch(r'in_[A-Za-z0-9]+', starting_after):
        raise HTTPException(400, 'Invalid invoice cursor.')
    client = _client(allow_disabled=True)
    sub = _stripe_call(client.v1.subscriptions.retrieve, subscription_id)
    if not _items(sub):
        raise HTTPException(404, 'JobDetector subscription not found.')
    params = {'subscription': subscription_id, 'limit': 20}
    if starting_after:
        params['starting_after'] = starting_after
    page = _stripe_call(client.v1.invoices.list, params)
    data = page if isinstance(page, dict) else page.to_dict()
    rows = [_invoice(row) for row in data['data']]
    return {'rows': rows, 'has_more': bool(data['has_more']),
            'next_cursor': rows[-1]['id'] if rows and data['has_more'] else None}


@router.get('/api/billing/admin/trials')
def trial_members(request: Request, response: Response, page: int = Query(1, ge=1, le=100000)):
    from api.plus_access import trial_status
    require_owner(request)
    response.headers['Cache-Control'] = 'private, no-store'
    users = _db().users
    query = {'is_verified': True, 'plus_trial_started_at': {'$exists': True}, 'vip_lifetime': {'$ne': True}, 'is_owner': {'$ne': True}}
    now = datetime.now(timezone.utc)
    total = users.count_documents(query)
    cursor = users.find(query, {'email': 1, 'full_name': 1, 'plus_trial_started_at': 1, 'plus_trial_ends_at': 1, 'is_verified': 1, 'billing.status': 1}).sort('plus_trial_started_at', -1).skip((page-1)*50).limit(50)
    rows = [{'email': user.get('email', ''), 'name': user.get('full_name', ''),
             **trial_status(user, now), 'converted': (user.get('billing') or {}).get('status') == 'active'} for user in cursor]
    return {'rows': rows, 'total': total, 'page': page, 'has_more': page*50 < total,
            'active': users.count_documents({**query, 'plus_trial_ends_at': {'$gt': now}}),
            'expired': users.count_documents({**query, 'plus_trial_ends_at': {'$lte': now}})}
