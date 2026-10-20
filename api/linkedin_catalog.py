"""Shared MongoDB search directory and per-account desktop section subscriptions."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from api.billing import _db, _user

router = APIRouter()
CATALOG_ID = 'linkedin-search-v1'
SEED = Path(__file__).resolve().parent.parent / 'data' / 'linkedin_search_presets.json'


def seed_document():
    content = json.loads(SEED.read_text())
    revision = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]
    return {'_id': CATALOG_ID, 'revision': revision, **content,
            'updated_at': datetime.now(timezone.utc)}


def get_catalog(db):
    document = db.linkedin_search_catalog.find_one({'_id': CATALOG_ID})
    if document is None:
        # A unique _id makes concurrent cold starts idempotent. Never overwrite
        # a centrally edited directory with the bundled bootstrap file.
        db.linkedin_search_catalog.update_one({'_id': CATALOG_ID}, {'$setOnInsert': seed_document()}, upsert=True)
        document = db.linkedin_search_catalog.find_one({'_id': CATALOG_ID})
    if not isinstance(document, dict) or not isinstance(document.get('groups'), list):
        raise HTTPException(503, '搜索目录暂时不可用，请稍后同步。')
    return document


def section_ids(catalog):
    return [group['id'] for group in catalog['groups']] + ['signals']


class Subscriptions(BaseModel):
    groups: list[str] = Field(..., max_length=40)


@router.get('/api/linkedin/subscriptions')
def subscriptions(request: Request, response: Response):
    user = _user(request)
    response.headers['Cache-Control'] = 'private, no-store'
    available = section_ids(get_catalog(_db()))
    stored = user.get('linkedin_desktop_groups')
    groups = [key for key in stored if key in available] if isinstance(stored, list) else available
    return {'groups': groups, 'customized': isinstance(stored, list)}


@router.put('/api/linkedin/subscriptions')
def update_subscriptions(data: Subscriptions, request: Request, response: Response):
    user = _user(request)
    available = section_ids(get_catalog(_db()))
    if any(key not in available for key in data.groups):
        raise HTTPException(422, '订阅中包含不存在的搜索板块，请先同步目录。')
    groups = list(dict.fromkeys(data.groups))
    _db().users.update_one({'_id': user['_id']}, {'$set': {'linkedin_desktop_groups': groups}})
    response.headers['Cache-Control'] = 'private, no-store'
    return {'groups': groups, 'customized': True}
