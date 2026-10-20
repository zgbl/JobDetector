from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import subscriptions_admin as admin


def sub(sid='sub_one', price='price_month', **kw):
    return {'id':sid,'customer':{'id':'cus_one','email':'stripe@example.test','name':'Member'},
            'status':'active','created':100,'livemode':True,
            'items':{'data':[{'price':{'id':price,'currency':'usd','unit_amount':999 if price=='price_year' else 100},
                              'quantity':1,'current_period_start':100,'current_period_end':2000}]},
            'latest_invoice':{'id':'in_one','status':'paid','amount_paid':100,'total':100,'currency':'usd',
                              'status_transitions':{'paid_at':101}},**kw}


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('STRIPE_MONTHLY_PRICE_ID','price_month');monkeypatch.setenv('STRIPE_ANNUAL_PRICE_ID','price_year')
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_live_placeholder')
    db=MagicMock();db.users.find.return_value=[{'stripe_customer_id':'cus_one','email':'site@example.test','username':'TuxyMember'}]
    client=MagicMock();client.v1.subscriptions.list.return_value.auto_paging_iter.return_value=[sub()]
    monkeypatch.setattr(admin,'_db',lambda:db);monkeypatch.setattr(admin,'_client',lambda **kw:client)
    def owner(request):
        if request.headers.get('Authorization')!='Bearer owner':raise HTTPException(403,'Owner only')
    monkeypatch.setattr(admin,'require_owner',owner)
    app=FastAPI();app.include_router(admin.router)
    return SimpleNamespace(http=TestClient(app),stripe=client,db=db,headers={'Authorization':'Bearer owner'})


def test_owner_boundary_and_private_cache(setup):
    assert setup.http.get('/api/billing/admin/subscriptions').status_code==403
    assert setup.http.get('/api/billing/admin/subscriptions/sub_one/invoices').status_code==403
    setup.stripe.v1.subscriptions.list.assert_not_called()
    response=setup.http.get('/api/billing/admin/subscriptions',headers=setup.headers)
    assert response.status_code==200
    assert response.headers['cache-control']=='private, no-store'
    row=response.json()['rows'][0]
    assert row['email']=='site@example.test' and row['registered']
    assert row['period_end']==2000 and row['latest_invoice']['amount_paid']==100
    assert response.json()['summary']['mrr_cents']==100


def test_matches_jobdetector_prices_even_dashboard_created_excludes_other_products(setup):
    setup.stripe.v1.subscriptions.list.return_value.auto_paging_iter.return_value=[sub(),sub('sub_other','price_tensugo')]
    data=setup.http.get('/api/billing/admin/subscriptions',headers=setup.headers).json()
    assert len(data['rows'])==1 and data['rows'][0]['id']=='sub_one'


def test_annual_revenue_cancellation_and_unpaid_are_not_treated_as_cash_or_access(setup):
    setup.stripe.v1.subscriptions.list.return_value.auto_paging_iter.return_value=[sub(),sub('sub_year','price_year'),
        sub('sub_cancel',cancel_at_period_end=True,cancel_at=1500),sub('sub_unpaid',status='past_due')]
    data=setup.http.get('/api/billing/admin/subscriptions',headers=setup.headers).json()
    assert data['summary']['active']==3 and data['summary']['ending']==1
    assert data['summary']['payment_issues']==1 and data['summary']['mrr_cents']==183
    rows={r['id']:r for r in data['rows']}
    assert rows['sub_cancel']['period_end']==1500 and rows['sub_cancel']['has_access']
    assert not rows['sub_unpaid']['has_access']


def test_sdk_objects_and_scan_limit_are_explicit(setup, monkeypatch):
    import stripe
    monkeypatch.setattr(admin,'SCAN_LIMIT',1)
    setup.stripe.v1.subscriptions.list.return_value.auto_paging_iter.return_value=[stripe.StripeObject.construct_from(sub(),'key'),sub('sub_two')]
    data=setup.http.get('/api/billing/admin/subscriptions',headers=setup.headers).json()
    assert data['truncated'] and data['rows'][0]['id']=='sub_one'


def test_invoice_scope_pagination_and_invalid_ids(setup):
    setup.stripe.v1.subscriptions.retrieve.return_value=sub(price='price_tensugo')
    assert setup.http.get('/api/billing/admin/subscriptions/sub_other/invoices',headers=setup.headers).status_code==404
    setup.stripe.v1.invoices.list.assert_not_called()
    setup.stripe.v1.subscriptions.retrieve.return_value=sub()
    setup.stripe.v1.invoices.list.return_value={'data':[{'id':'in_one','amount_paid':100,'status':'paid'}],'has_more':True}
    data=setup.http.get('/api/billing/admin/subscriptions/sub_one/invoices?starting_after=in_prev',headers=setup.headers).json()
    assert data['next_cursor']=='in_one' and data['has_more']
    assert setup.stripe.v1.invoices.list.call_args.args[0]=={'subscription':'sub_one','limit':20,'starting_after':'in_prev'}
    assert setup.http.get('/api/billing/admin/subscriptions/sub_one/invoices?starting_after=bad',headers=setup.headers).status_code==400


def test_real_owner_policy_rejects_other_admin(setup,monkeypatch):
    from api import traffic
    monkeypatch.setattr(admin,'require_owner',traffic.require_owner)
    monkeypatch.setenv('ADMIN_EMAIL','tuxy@example.test')
    monkeypatch.setattr(traffic,'_user',lambda req:{'email':'other@example.test','is_admin':True})
    assert setup.http.get('/api/billing/admin/subscriptions',headers=setup.headers).status_code==403
    setup.stripe.v1.subscriptions.list.assert_not_called()


def test_trial_members_are_owner_only_paginated_and_never_require_stripe(setup):
    assert setup.http.get('/api/billing/admin/trials').status_code==403
    setup.db.users.count_documents.return_value=51
    setup.db.users.find.return_value=MagicMock()
    setup.db.users.find.return_value.sort.return_value.skip.return_value.limit.return_value=[]
    response=setup.http.get('/api/billing/admin/trials?page=2',headers=setup.headers)
    assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
    assert response.json()['page']==2 and not response.json()['has_more']
    setup.db.users.find.return_value.sort.return_value.skip.assert_called_with(50)
    setup.stripe.v1.subscriptions.list.assert_not_called()
