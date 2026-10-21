from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import research_lab as lab
from src.services import research_fetch as fetch


def test_jobposting_jsonld_compensation_is_available_as_grounded_evidence():
    html = '''<script type="application/ld+json">{"@graph":[
      {"@type":"Organization","name":"Acme"},
      {"@type":"JobPosting","baseSalary":{"@type":"MonetaryAmount","currency":"USD",
       "value":{"@type":"QuantitativeValue","minValue":150000,"maxValue":190000,"unitText":"YEAR"}},
       "incentiveCompensation":"Equity eligible","jobBenefits":"Health insurance"}
    ]}</script>'''
    text = fetch.jobposting_compensation(BeautifulSoup(html, 'html.parser'))
    assert '150000' in text and '190000' in text and 'USD' in text
    assert 'Equity eligible' in text and 'Health insurance' in text
    assert 'Acme' not in text
    source = [{'id':'S2','kind':'web','text':text,'title':'job','url':'https://example.test/job'}]
    raw = {'fields':{'salary':{'value':'USD 150,000–190,000 / year; equity eligible; health insurance',
             'status':'confirmed','evidence':[{'source_id':'S2','quote':'"minValue":150000,"maxValue":190000'}]}}}
    result = lab.grounded_report(raw, source)
    assert result['fields']['salary']['status'] == 'confirmed'
    assert 'equity eligible' in result['fields']['salary']['value']


def test_private_addresses_and_mixed_dns_records_are_rejected(monkeypatch):
    for records in [[('127.0.0.1',443)],[('169.254.169.254',443)],[('93.184.216.34',443),('10.0.0.1',443)]]:
        monkeypatch.setattr(fetch.socket,'getaddrinfo',lambda *a, records=records, **kw:[(2,1,6,'',ip) for ip in records])
        with pytest.raises(ValueError):fetch.checked_target('https://example.test/private')
    for url in ['http://example.test','https://u:secret@example.test','https://example.test:8080','https://[::1]/']:
        with pytest.raises(ValueError):fetch.checked_target(url)


def test_every_redirect_is_validated_before_connecting(monkeypatch):
    monkeypatch.setattr(fetch.socket,'getaddrinfo',lambda host,*a,**kw:[(2,1,6,'',('127.0.0.1' if host=='private.test' else '93.184.216.34',443))])
    connection=MagicMock();response=connection.getresponse.return_value;response.status=302;response.getheader.return_value='https://private.test/metadata'
    factory=MagicMock(return_value=connection);monkeypatch.setattr(fetch,'PinnedHTTPS',factory)
    with pytest.raises(ValueError):fetch.fetch_evidence('https://example.test/')
    assert factory.call_count==1
    connection.close.assert_called_once()


def test_unmatched_quotes_and_capture_claims_cannot_become_verified_facts():
    sources=[{'id':'S1','kind':'capture','text':"Director, Software Engineering. I'm hiring!",'title':'post','url':''},
             {'id':'S2','kind':'web','text':'Remote in the United States. $136,908 - $210,000 a year.','title':'job','url':'https://example.test/job'}]
    raw={'fields':{'poster_role':{'value':'Direct HM','status':'confirmed','evidence':[{'source_id':'S1','quote':'Director, Software Engineering'}]},
        'salary':{'value':'$500,000','status':'confirmed','evidence':[{'source_id':'S2','quote':'Pays $500,000'}]},
        'location':{'value':'United States remote','status':'confirmed','evidence':[{'source_id':'S2','quote':'Remote in the United States.'}]},
        'company_type':{'value':'Direct employer','status':'confirmed','evidence':[{'source_id':'S1','quote':"I'm hiring!"}]}},
         'summary':'Do not trust this ungrounded generated overview','questions':[], 'outreach_draft':'I have ten years of experience at Basis.'}
    result=lab.grounded_report(raw,sources)
    assert result['fields']['salary']['status']=='unknown' and '$500,000' not in result['fields']['salary']['value']
    assert result['fields']['poster_role']['status']!='confirmed'
    assert result['fields']['company_type']['status']=='reported'
    assert result['fields']['location']['status']=='confirmed'
    assert 'ungrounded' not in result['summary']
    assert 'ten years' not in result['outreach_draft']


def test_sources_are_only_provided_links_and_the_ats_employer_homepage(monkeypatch):
    pages={'https://jobs.lever.co/acme/job':{'url':'https://jobs.lever.co/acme/job','title':'job','text':'Job details','links':[{'label':'Acme Home Page','url':'https://acme.test/'}]},'https://acme.test/':{'url':'https://acme.test/','title':'Acme','text':'Software company','links':[]}}
    mock=MagicMock(side_effect=lambda url,**kw:pages[url]);monkeypatch.setattr(lab,'fetch_evidence',mock)
    capture=lab.Capture(text='This is an example job posting with enough text to research.',job_urls=['https://jobs.lever.co/acme/job'])
    sources,warnings=lab.collect_sources(capture)
    assert [s['url'] for s in sources[1:]]==list(pages)
    assert not warnings


@pytest.fixture
def api(monkeypatch):
    user={'_id':'member','email':'member@example.test','is_verified':True};db=MagicMock();db.research_usage.find_one_and_update.return_value={'attempts':1}
    def auth(request):
        if request.headers.get('Authorization')!='Bearer member':raise HTTPException(401,'Sign in')
        return user
    monkeypatch.setattr(lab,'_user',auth);monkeypatch.setattr(lab,'_db',lambda:db);monkeypatch.setattr(lab,'access_for',lambda u:True)
    monkeypatch.setattr(lab,'research',lambda data:{'summary':'report'})
    app=FastAPI();app.include_router(lab.router)
    return SimpleNamespace(client=TestClient(app),db=db,headers={'Authorization':'Bearer member'},monkeypatch=monkeypatch)


def test_api_enforces_membership_quota_and_never_caches_reports(api):
    data={'text':'A sufficiently long job post with a job description here.'}
    assert api.client.post('/api/research-lab/analyze',json=data).status_code==401
    api.monkeypatch.setattr(lab,'access_for',lambda u:False)
    assert api.client.post('/api/research-lab/analyze',headers=api.headers,json=data).status_code==403
    api.monkeypatch.setattr(lab,'access_for',lambda u:True)
    api.db.research_usage.find_one_and_update.return_value={'attempts':6}
    assert api.client.post('/api/research-lab/analyze',headers=api.headers,json=data).status_code==429
    api.db.research_usage.find_one_and_update.return_value={'attempts':1}
    response=api.client.post('/api/research-lab/analyze',headers=api.headers,json=data)
    assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
    assert api.client.post('/api/research-lab/analyze',headers=api.headers,json={'text':'short'}).status_code==422


def test_tailor_uses_saved_resume_facts_and_marks_post_only_scope(api):
    api.monkeypatch.setenv('DEEPSEEK_API_KEY','test-key')
    original='Software Engineer at Example Corp from 2021 to 2025. Built Python APIs and improved service reliability. '*2
    sources=[{'kind':'capture','title':'Selected LinkedIn post','text':'Hiring a Backend Engineer to build Python APIs.'}]
    model=MagicMock()
    model.json.return_value={'choices':[{'message':{'content':__import__('json').dumps({'resume_markdown':original,'changes':['Moved Python work first'],'gaps':['Kubernetes not evidenced']})}}]}
    model.raise_for_status.return_value=None
    api.monkeypatch.setattr(lab.requests,'post',lambda *a,**kw:model)
    payload={'resume_text':original,'resume_name':'Backend','job_title':'Backend Engineer','sources':sources}
    assert api.client.post('/api/research-lab/tailor',json=payload).status_code==401
    api.monkeypatch.setattr(lab,'access_for',lambda u:False)
    assert api.client.post('/api/research-lab/tailor',headers=api.headers,json=payload).status_code==403
    api.monkeypatch.setattr(lab,'access_for',lambda u:True)
    response=api.client.post('/api/research-lab/tailor',headers=api.headers,json=payload)
    assert response.status_code==200
    assert '仅根据 LinkedIn' in response.json()['scope']
    assert response.headers['cache-control']=='private, no-store'
    model.json.return_value={'choices':[{'message':{'content':__import__('json').dumps({'resume_markdown':original+' Grew revenue 99%.','changes':[],'gaps':[]})}}]}
    assert api.client.post('/api/research-lab/tailor',headers=api.headers,json=payload).status_code==502


def test_tailored_docx_exports_a_real_word_file(api):
    text='# Example Candidate\n## Experience\n- Built Python services and improved reliability for a software team. '*3
    response=api.client.post('/api/research-lab/export-docx',headers=api.headers,json={'resume_markdown':text})
    assert response.status_code==200
    assert response.content.startswith(b'PK')
    assert 'wordprocessingml.document' in response.headers['content-type']
