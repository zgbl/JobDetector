import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import billing


@pytest.fixture
def setup(monkeypatch):
    for name, value in {"BILLING_ENABLED": "true", "STRIPE_SECRET_KEY": "sk_test_placeholder",
                        "STRIPE_MONTHLY_PRICE_ID": "price_month", "STRIPE_ANNUAL_PRICE_ID": "price_year",
                        "STRIPE_WEBHOOK_SECRET": "whsec_test", "ADMIN_EMAIL": "owner@example.test"}.items():
        monkeypatch.setenv(name, value)
    user = {"_id": "user1", "email": "member@example.test", "is_verified": True, "is_active": True,
            "stripe_customer_id": "cus_member"}
    db = MagicMock()
    from api.linkedin_catalog import seed_document
    db.linkedin_search_catalog.find_one.return_value = seed_document()
    db.users.find_one.return_value = user
    db.users.update_one.return_value = SimpleNamespace(modified_count=1)
    db.billing_settings.find_one.return_value = None
    stripe = MagicMock()
    stripe.v1.subscriptions.list.return_value.auto_paging_iter.return_value = []
    stripe.v1.checkout.sessions.create.return_value = {"id": "cs_new", "url": "https://checkout.stripe.com/test", "livemode": False}
    stripe.v1.billing_portal.configurations.create.return_value = {"id": "bpc_jobdetector"}
    stripe.v1.prices.retrieve.side_effect = lambda price: {"id": price, "active": True, "product": billing.PRODUCT_ID, "currency": "usd", "unit_amount": 100 if price == "price_month" else 999,
        "recurring": {"interval": "month" if price == "price_month" else "year", "interval_count": 1, "usage_type": "licensed"}}
    monkeypatch.setattr(billing, "_db", lambda: db)
    monkeypatch.setattr(billing, "_client", lambda **kwargs: stripe)
    monkeypatch.setattr(billing, "decode_access_token", lambda token: {"sub": user["email"]} if token == "valid" else None)
    app = FastAPI(); app.include_router(billing.router)
    return SimpleNamespace(client=TestClient(app), db=db, stripe=stripe, user=user, headers={"Authorization": "Bearer valid"})


def subscription(status="active", price="price_month", **kwargs):
    return {"id": "sub_one", "status": status, "created": 1, "customer": "cus_member", "livemode": True,
            "metadata": {"app": billing.APP_NAME}, "items": {"data": [{"price": {"id": price}, "current_period_end": 9999999999}]}, **kwargs}


def test_free_preview_does_not_return_locked_queries(setup):
    result = setup.client.get('/api/linkedin/presets').json()
    assert result['full_access'] is False
    assert result['total'] == 155
    assert sum(len(group['items']) for group in result['groups']) == 11
    assert result['signals'] == []
    assert 'Senior Data Engineer' not in json.dumps(result)


def test_rollout_disabled_keeps_existing_full_library(setup, monkeypatch):
    monkeypatch.setenv('BILLING_ENABLED', 'false')
    result = setup.client.get('/api/linkedin/presets').json()
    assert result['full_access']
    assert sum(len(group['items']) for group in result['groups']) + len(result['signals']) == 155


def test_checkout_requires_auth_and_valid_plan(setup):
    assert setup.client.post('/api/billing/checkout', json={'plan':'monthly'}).status_code == 401
    assert setup.client.post('/api/billing/checkout', headers=setup.headers, json={'plan':'free'}).status_code == 422
    assert setup.client.get('/api/linkedin/presets?paid=true', headers={'Authorization':'Bearer forged'}).status_code == 401
    setup.stripe.v1.checkout.sessions.create.assert_not_called()


@pytest.mark.parametrize('plan,price', [('monthly','price_month'),('annual','price_year')])
def test_checkout_price_and_customer_come_from_server(setup, plan, price):
    response = setup.client.post('/api/billing/checkout', headers=setup.headers,
                                 json={'plan':plan,'amount':1,'customer':'cus_attacker','success_url':'https://attacker.test'})
    assert response.status_code == 200
    params = setup.stripe.v1.checkout.sessions.create.call_args.args[0]
    assert params['mode'] == 'subscription'
    assert 'payment_method_types' not in params
    assert params['integration_identifier'] == 'jobdetector_checkout_qsnxvdra'
    assert setup.stripe.v1.checkout.sessions.create.call_args.kwargs['options']['idempotency_key'].startswith('jd-checkout-v2-')
    assert params['line_items'] == [{'price':price,'quantity':1}]
    assert params['customer'] == 'cus_member'
    assert params['success_url'].endswith('/linkedin-search.html?billing=success')
    assert params['subscription_data']['metadata']['user_id'] == 'user1'


def test_misconfigured_price_cannot_charge(setup):
    setup.stripe.v1.prices.retrieve.side_effect = None
    setup.stripe.v1.prices.retrieve.return_value = {'active':True,'currency':'usd','unit_amount':9999,'recurring':{'interval':'month','interval_count':1,'usage_type':'licensed'}}
    assert setup.client.post('/api/billing/checkout', headers=setup.headers,json={'plan':'monthly'}).status_code == 503
    setup.stripe.v1.checkout.sessions.create.assert_not_called()


def test_stripe_sdk_resources_are_converted_before_using_dict_methods(setup):
    import stripe
    price = setup.stripe.v1.prices.retrieve('price_month')
    setup.stripe.v1.prices.retrieve.side_effect = None
    setup.stripe.v1.prices.retrieve.return_value = stripe.Price.construct_from(price, 'sk_test_placeholder')
    setup.stripe.v1.subscriptions.list.return_value.auto_paging_iter.return_value = [stripe.Subscription.construct_from(subscription(), 'sk_test_placeholder')]
    assert setup.client.get('/api/billing/status',headers=setup.headers).json()['full_access']
    assert billing._validate_price(setup.stripe,'monthly')['unit_amount'] == 100


def test_active_subscription_blocks_double_checkout(setup):
    setup.stripe.v1.subscriptions.list.return_value.auto_paging_iter.return_value = [subscription()]
    assert setup.client.post('/api/billing/checkout', headers=setup.headers,json={'plan':'annual'}).status_code == 409
    setup.stripe.v1.checkout.sessions.create.assert_not_called()


def test_pending_checkout_reused_or_expired_when_changing_plan(setup):
    setup.user.update(stripe_checkout_session_id='cs_pending', stripe_checkout_plan='monthly')
    setup.stripe.v1.checkout.sessions.retrieve.return_value = {'status':'open','customer':'cus_member','url':'https://checkout.stripe.com/pending'}
    assert setup.client.post('/api/billing/checkout', headers=setup.headers,json={'plan':'monthly'}).json()['url'].endswith('/pending')
    setup.stripe.v1.checkout.sessions.create.assert_not_called()
    assert setup.client.post('/api/billing/checkout', headers=setup.headers,json={'plan':'annual'}).status_code == 200
    setup.stripe.v1.checkout.sessions.expire.assert_called_once_with('cs_pending')


@pytest.mark.parametrize('state,access', [('active',True),('past_due',False),('canceled',False),('incomplete',False),('unpaid',False)])
def test_access_tracks_current_stripe_status(setup,state,access):
    setup.stripe.v1.subscriptions.list.return_value.auto_paging_iter.return_value = [subscription(state,price='price_year',cancel_at_period_end=True)]
    result = setup.client.get('/api/billing/status',headers=setup.headers).json()
    assert result['full_access'] == access
    assert result['plan'] == 'annual'
    assert result['cancel_at_period_end'] is True
    if access:
        assert setup.client.get('/api/linkedin/presets',headers=setup.headers).json()['full_access']


def test_unrelated_subscription_cannot_unlock(setup):
    setup.stripe.v1.subscriptions.list.return_value.auto_paging_iter.return_value = [subscription(price='price_unrelated')]
    assert not setup.client.get('/api/billing/status',headers=setup.headers).json()['full_access']


def test_portal_uses_authenticated_customers_id(setup):
    setup.stripe.v1.billing_portal.sessions.create.return_value = {'url':'https://billing.stripe.com/session'}
    assert setup.client.post('/api/billing/portal',headers=setup.headers).status_code == 200
    assert setup.stripe.v1.billing_portal.sessions.create.call_args.args[0]['customer'] == 'cus_member'
    assert setup.stripe.v1.billing_portal.sessions.create.call_args.args[0]['configuration'] == 'bpc_jobdetector'
    assert setup.stripe.v1.billing_portal.configurations.create.call_args.args[0]['metadata']['app'] == billing.APP_NAME
    assert setup.client.post('/api/billing/portal').status_code == 401


def test_webhook_rejects_forged_and_expired_signatures(setup):
    body = json.dumps({'id':'evt_1','type':'invoice.paid','data':{'object':{'customer':'cus_member'}}}).encode()
    for signature in ['forged', sign(body,int(time.time())-1000)]:
        assert setup.client.post('/api/billing/webhook',content=body,headers={'Stripe-Signature':signature}).status_code == 400


def sign(body,timestamp):
    signature=hmac.new(b'whsec_test',str(timestamp).encode()+b'.'+body,hashlib.sha256).hexdigest()
    return f't={timestamp},v1={signature}'


def test_verified_webhook_uses_current_state_and_is_replay_safe(setup):
    # A late paid event cannot re-enable a subscription that Stripe now says is canceled.
    setup.stripe.v1.subscriptions.list.return_value.auto_paging_iter.return_value = [subscription('canceled')]
    body=json.dumps({'id':'evt_paid','type':'invoice.paid','data':{'object':{'customer':'cus_member'}}}).encode()
    for _ in range(2):
        assert setup.client.post('/api/billing/webhook',content=body,headers={'Stripe-Signature':sign(body,int(time.time()))}).status_code == 200
    updates=[call.args[1]['$set']['billing'] for call in setup.db.users.update_one.call_args_list if 'billing' in call.args[1].get('$set',{})]
    assert updates and all(not update['subscribed'] for update in updates)


def test_report_requires_specific_owner_not_any_admin(setup):
    setup.user['is_admin']=True
    assert setup.client.get('/api/billing/admin-summary',headers=setup.headers).status_code == 403


def test_owner_can_validate_both_prices_without_creating_payment(setup, monkeypatch):
    assert setup.client.post('/api/billing/preflight',headers=setup.headers).status_code == 403
    setup.user['email']='owner@example.test'
    monkeypatch.setenv('BILLING_ENABLED','false')
    response=setup.client.post('/api/billing/preflight',headers=setup.headers)
    assert response.status_code==200
    assert response.json()['plans']['annual']['unit_amount']==999
    assert response.json()['plans']['monthly']['unit_amount']==100
    setup.stripe.v1.checkout.sessions.create.assert_not_called()


def test_lifetime_vip_unlocks_without_stripe_and_cannot_be_charged(setup):
    setup.user['vip_lifetime'] = True
    setup.user['stripe_customer_id'] = 'cus_existing'
    response = setup.client.get('/api/billing/status', headers=setup.headers)
    assert response.status_code == 200
    assert response.json()['vip_lifetime'] and response.json()['full_access']
    assert not response.json()['subscribed'] and response.json()['period_end'] is None
    catalog = setup.client.get('/api/linkedin/presets', headers=setup.headers).json()
    assert sum(len(g['items']) for g in catalog['groups']) + len(catalog['signals']) == 155
    assert setup.client.post('/api/billing/checkout', headers=setup.headers, json={'plan':'monthly'}).status_code == 409
    setup.stripe.v1.subscriptions.list.assert_not_called()
    setup.stripe.v1.checkout.sessions.create.assert_not_called()


def test_persisted_owner_gets_vip_without_owner_email_environment(setup, monkeypatch):
    monkeypatch.delenv('ADMIN_EMAIL', raising=False)
    setup.user['is_owner'] = True
    result = setup.client.get('/api/billing/status', headers=setup.headers).json()
    assert result['is_owner'] and result['vip_lifetime'] and result['full_access']
    setup.stripe.v1.subscriptions.list.assert_not_called()


def test_display_name_or_string_flags_do_not_grant_vip(setup):
    setup.user.update({'full_name':'tuxy','username':'tuxy','vip_lifetime':'true','is_owner':'true'})
    result = setup.client.get('/api/billing/status', headers=setup.headers).json()
    assert not result['vip_lifetime'] and not result['is_owner'] and not result['full_access']


def test_verified_trial_unlocks_and_checkout_waits_until_expiry(setup):
    from datetime import datetime, timedelta, timezone
    now=datetime.now(timezone.utc)
    setup.user.update({'plus_trial_started_at':now,'plus_trial_ends_at':now+timedelta(days=7)})
    status=setup.client.get('/api/billing/status',headers=setup.headers).json()
    assert status['trial_active'] and status['full_access'] and not status['subscribed']
    catalog=setup.client.get('/api/linkedin/presets',headers=setup.headers).json()
    assert sum(len(g['items']) for g in catalog['groups'])+len(catalog['signals'])==155
    assert setup.client.post('/api/billing/checkout',headers=setup.headers,json={'plan':'annual'}).status_code==409
    setup.stripe.v1.subscriptions.list.assert_not_called()
    setup.stripe.v1.checkout.sessions.create.assert_not_called()


def test_expired_trial_returns_preview_and_allows_paid_checkout(setup):
    from datetime import datetime, timedelta, timezone
    now=datetime.now(timezone.utc)
    setup.user.update({'plus_trial_started_at':now-timedelta(days=8),'plus_trial_ends_at':now-timedelta(days=1)})
    status=setup.client.get('/api/billing/status',headers=setup.headers).json()
    assert status['trial_expired'] and not status['trial_active'] and not status['full_access']
    assert not setup.client.get('/api/linkedin/presets',headers=setup.headers).json()['full_access']
    assert setup.client.post('/api/billing/checkout',headers=setup.headers,json={'plan':'monthly'}).status_code==200


def test_paid_membership_takes_over_after_trial_expiry(setup):
    from datetime import datetime, timedelta, timezone
    now=datetime.now(timezone.utc)
    setup.user.update({'plus_trial_started_at':now-timedelta(days=8),'plus_trial_ends_at':now-timedelta(days=1)})
    setup.stripe.v1.subscriptions.list.return_value.auto_paging_iter.return_value=[subscription()]
    result=setup.client.get('/api/billing/status',headers=setup.headers).json()
    assert result['trial_expired'] and result['subscribed'] and result['full_access']
