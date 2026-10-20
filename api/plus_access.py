"""Server-clock seven-day welcome access; granted once after email verification."""
from datetime import datetime, timedelta, timezone

TRIAL_DAYS = 7


def as_utc(value):
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def trial_status(user, now=None):
    now = now or datetime.now(timezone.utc)
    end = as_utc((user or {}).get('plus_trial_ends_at'))
    start = as_utc((user or {}).get('plus_trial_started_at'))
    eligible = bool(user and user.get('is_verified') and start and end)
    return {'trial_active': bool(eligible and start <= now < end),
            'trial_expired': bool(eligible and now >= end),
            'trial_started_at': int(start.timestamp()) if start else None,
            'trial_ends_at': int(end.timestamp()) if end else None}


def grant_welcome_trial(users, user, now=None):
    """A conditional database write prevents token retries from renewing the trial."""
    if user.get('plus_trial_started_at') or user.get('vip_lifetime') is True or user.get('is_owner') is True:
        return
    now = now or datetime.now(timezone.utc)
    users.update_one({'_id': user['_id'], 'plus_trial_started_at': {'$exists': False}},
                     {'$set': {'plus_trial_started_at': now, 'plus_trial_ends_at': now + timedelta(days=TRIAL_DAYS)}})
