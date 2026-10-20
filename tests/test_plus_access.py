from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from api.plus_access import grant_welcome_trial, trial_status


def test_trial_exact_boundary_uses_server_time_and_supports_mongo_naive_utc():
    now=datetime(2026,10,20,tzinfo=timezone.utc)
    user={'is_verified':True,'plus_trial_started_at':now.replace(tzinfo=None),'plus_trial_ends_at':(now+timedelta(days=7)).replace(tzinfo=None)}
    assert trial_status(user,now)['trial_active']
    assert trial_status(user,now+timedelta(days=7)-timedelta(microseconds=1))['trial_active']
    assert trial_status(user,now+timedelta(days=7))['trial_expired']
    assert not trial_status(user,now-timedelta(seconds=1))['trial_active']
    assert not trial_status({**user,'is_verified':False},now)['trial_active']


def test_trial_grant_is_once_and_never_overwrites_existing_dates():
    users=MagicMock();now=datetime(2026,10,20,tzinfo=timezone.utc)
    grant_welcome_trial(users,{'_id':'u'},now)
    query,change=users.update_one.call_args.args
    assert query=={'_id':'u','plus_trial_started_at':{'$exists':False}}
    assert change['$set']['plus_trial_ends_at']==now+timedelta(days=7)
    users.reset_mock()
    grant_welcome_trial(users,{'_id':'u','plus_trial_started_at':now},now+timedelta(days=2))
    grant_welcome_trial(users,{'_id':'owner','vip_lifetime':True},now)
    users.update_one.assert_not_called()
