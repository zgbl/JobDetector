from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import billing, traffic


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('ADMIN_EMAIL','tuxy@example.test')
    user={'email':'someone@example.test','is_admin':True,'is_active':True,'is_verified':True}
    db=MagicMock()
    db.traffic_events.aggregate.return_value=[]
    db.traffic_events.distinct.return_value=[]
    db.traffic_events.find_one.return_value=None
    db.traffic_events.count_documents.return_value=0
    db.billing_events.count_documents.return_value=0
    db.users.count_documents.return_value=0
    monkeypatch.setattr(traffic,'_user',lambda request: user if request.headers.get('Authorization')=='Bearer valid' else (_ for _ in ()).throw(traffic.HTTPException(401,'Sign in')))
    monkeypatch.setattr(traffic,'_db',lambda:db)
    app=FastAPI();app.include_router(traffic.router)
    return SimpleNamespace(client=TestClient(app),user=user,db=db,headers={'Authorization':'Bearer valid'})


def test_analytics_rejects_anonymous_and_other_admins(setup):
    assert setup.client.get('/api/traffic/admin').status_code==401
    assert setup.client.get('/api/traffic/admin',headers=setup.headers).status_code==403
    setup.db.traffic_events.aggregate.assert_not_called()


def test_owner_report_excludes_internal_activity_and_test_payments(setup):
    setup.user['email']='tuxy@example.test'
    response=setup.client.get('/api/traffic/admin?days=7',headers=setup.headers)
    assert response.status_code==200
    assert len(response.json()['daily'])==7
    assert setup.db.traffic_events.count_documents.call_args_list[0].args[0]['is_owner']=={'$ne':True}
    assert setup.db.billing_events.count_documents.call_args.args[0]['livemode'] is True
    assert setup.client.get('/api/traffic/admin?days=999',headers=setup.headers).status_code==422


def test_event_stores_only_sanitized_attribution(setup):
    event={'event_id':'11111111-1111-4111-8111-111111111111','visitor_id':'22222222-2222-4222-8222-222222222222','session_id':'33333333-3333-4333-8333-333333333333','event':'page_view','page':'/linkedin-search.html','referrer':'https://source.test/page?private=value'}
    assert setup.client.post('/api/traffic/event',json=event).status_code==202
    saved=setup.db.traffic_events.insert_one.call_args.args[0]
    assert saved['source']=='source.test'
    assert 'ip_address' not in saved and 'user_email' not in saved
    assert setup.client.post('/api/traffic/event',json={**event,'page':'/?token=secret'}).status_code==422
    assert setup.client.post('/api/traffic/event',json={**event,'event':'paid'}).status_code==422
