from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from api import billing, linkedin_catalog as catalog
from scripts.add_software_search_group import add_group


class Directory:
    def __init__(self): self.doc = None; self.writes = 0
    def find_one(self, query): return deepcopy(self.doc)
    def update_one(self, query, change, **kwargs):
        self.writes += 1
        if self.doc is None: self.doc = deepcopy(change['$setOnInsert'])


def test_catalog_bootstrap_is_idempotent_and_database_edits_are_canonical():
    directory = Directory(); db = SimpleNamespace(linkedin_search_catalog=directory)
    first = catalog.get_catalog(db)
    assert sum(len(g['items']) for g in first['groups']) + len(first['signals']) == 155
    assert directory.writes == 1
    directory.doc['groups'][0]['name'] = 'Centrally edited name'
    assert catalog.get_catalog(db)['groups'][0]['name'] == 'Centrally edited name'
    assert directory.writes == 1


def test_software_board_migration_preserves_existing_central_edits():
    initial = catalog.seed_document()
    initial['groups'].pop(0)
    initial['groups'][0]['name'] = 'Centrally edited FDE'
    initial['revision'] = 'old-revision'

    class MutableDirectory:
        doc = initial

        def find_one(self, query):
            return deepcopy(self.doc)

        def update_one(self, query, change):
            if query['revision'] != self.doc['revision']:
                return SimpleNamespace(modified_count=0)
            self.doc.update(deepcopy(change['$set']))
            return SimpleNamespace(modified_count=1)

    directory = MutableDirectory()
    db = SimpleNamespace(linkedin_search_catalog=directory)
    preview = add_group(db)
    assert not preview['changed'] and len(directory.doc['groups']) == 10
    result = add_group(db, apply=True)
    assert result['changed'] and result['total'] == 155
    assert directory.doc['groups'][0]['id'] == 'software'
    assert directory.doc['groups'][1]['name'] == 'Centrally edited FDE'
    assert not add_group(db, apply=True)['changed']


@pytest.fixture
def service(monkeypatch):
    directory=Directory(); directory.doc=catalog.seed_document()
    users={'one':{'_id':'one','email':'one@example.test','is_owner':True}, 'two':{'_id':'two','email':'two@example.test','is_owner':True}}
    db=SimpleNamespace(linkedin_search_catalog=directory,users=MagicMock())
    def update(query,change): users[query['_id']].update(change['$set'])
    db.users.update_one.side_effect=update
    def auth(request, required=True):
        user=users.get(request.headers.get('Authorization','').removeprefix('Bearer '))
        if not user and required: raise HTTPException(401,'Sign in')
        return user
    for module in (billing,catalog):
        monkeypatch.setattr(module,'_db',lambda:db);monkeypatch.setattr(module,'_user',auth)
    monkeypatch.setattr(billing,'_enabled',lambda:True)
    app=FastAPI();app.include_router(billing.router);app.include_router(catalog.router)
    return TestClient(app),users,directory


def test_subscription_choices_are_per_account_and_empty_is_preserved(service):
    client,users,directory=service
    one={'Authorization':'Bearer one'};two={'Authorization':'Bearer two'}
    assert client.get('/api/linkedin/subscriptions').status_code==401
    initial=client.get('/api/linkedin/subscriptions',headers=one).json()
    assert len(initial['groups'])==12 and not initial['customized']
    saved=client.put('/api/linkedin/subscriptions',headers=one,json={'groups':['data','bi','data']})
    assert saved.status_code==200 and saved.json()['groups']==['data','bi']
    assert users['one']['linkedin_desktop_groups']==['data','bi']
    assert not client.get('/api/linkedin/subscriptions',headers=two).json()['customized']
    assert client.put('/api/linkedin/subscriptions',headers=one,json={'groups':['not-a-section']}).status_code==422
    assert client.put('/api/linkedin/subscriptions',headers=one,json={'groups':[]}).status_code==200
    assert client.get('/api/linkedin/subscriptions',headers=one).json()['groups']==[]
    assert saved.headers['cache-control']=='private, no-store'


def test_existing_console_api_reads_central_catalog_without_changing_shape(service):
    client,users,directory=service
    result=client.get('/api/linkedin/presets',headers={'Authorization':'Bearer one'}).json()
    assert result['total']==155 and result['full_access']
    assert result['revision']==directory.doc['revision']
    directory.doc['groups'][0]['items'][0][2]='"Central DB role" hiring'
    fresh=client.get('/api/linkedin/presets',headers={'Authorization':'Bearer one'}).json()
    assert fresh['groups'][0]['items'][0][2]=='"Central DB role" hiring'
