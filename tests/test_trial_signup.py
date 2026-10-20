"""Exercise the real registration/verification routes without email or database I/O."""
import importlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def signup(monkeypatch):
    monkeypatch.setenv('MONGODB_URI','mongodb://127.0.0.1:27017')
    monkeypatch.setattr('pymongo.MongoClient',MagicMock())
    api=importlib.import_module('api.index')
    users=MagicMock();db=SimpleNamespace(users=users)
    users.find_one.return_value=None
    monkeypatch.setattr(api,'get_db',lambda:db)
    monkeypatch.setattr(api,'get_password_hash',lambda password:'test_hash')
    mail=MagicMock();mail.send_verification_email.return_value=True
    monkeypatch.setattr(api,'get_email_service',lambda:mail)
    async def skip_limit(*args,**kwargs):pass
    monkeypatch.setattr(api,'check_rate_limit',skip_limit)
    return SimpleNamespace(client=TestClient(api.app),users=users,mail=mail)


def test_registration_verification_grants_seven_days_without_payment(signup):
    result=signup.client.post('/api/auth/register',json={'email':'new@example.test','password':'example-password',
        'full_name':'New member','signup_source':'linkedin-search','vip_lifetime':True,'is_owner':True})
    assert result.status_code==200
    saved=signup.users.insert_one.call_args.args[0]
    assert not saved['is_verified'] and 'plus_trial_started_at' not in saved
    assert 'vip_lifetime' not in saved and 'is_owner' not in saved
    assert saved['verification_redirect']=='/linkedin-search.html'
    signup.users.find_one.return_value={**saved,'_id':'new_user'}
    response=signup.client.get('/api/auth/verify-email?token='+saved['verification_token'],follow_redirects=False)
    assert response.status_code==302 and response.headers['location']=='/linkedin-search.html?verified=true'
    writes=signup.users.update_one.call_args_list
    grant=writes[-1].args
    assert grant[0]['plus_trial_started_at']=={'$exists':False}
    dates=grant[1]['$set']
    assert dates['plus_trial_ends_at']-dates['plus_trial_started_at']==timedelta(days=7)
    assert 'stripe_customer_id' not in dates
    signup.mail.send_verification_email.assert_called_once()


def test_expired_verification_cannot_start_trial(signup):
    signup.users.find_one.return_value={'_id':'expired','verification_token_expires':datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(seconds=1)}
    assert signup.client.get('/api/auth/verify-email?token=expired',follow_redirects=False).status_code==400
    signup.users.update_one.assert_not_called()
