"""Offline unit tests for the ATS source-verification engine.

No network access is required: these tests cover URL identification, redirect
unwrapping, token hints, JSON-LD parsing and the generic-page heuristics.
Live ATS behaviour is exercised by ``scripts/verify_source_smoke.py``.

Run: ``pytest tests/test_source_verify.py -q``
"""
from __future__ import annotations

import pytest

from src.services.source_verify import (
    SourceVerifier,
    board_ref_from_company,
    board_ref_from_urls,
    identify,
    unwrap_redirect,
    STATUS_CLOSED,
    STATUS_OPEN,
)


@pytest.mark.parametrize(
    "url,ats,token,job_id",
    [
        ("https://boards.greenhouse.io/stripe/jobs/8172487", "greenhouse", "stripe", "8172487"),
        ("https://job-boards.greenhouse.io/figma/jobs/5458801004?gh_jid=5458801004",
         "greenhouse", "figma", "5458801004"),
        ("https://boards.greenhouse.io/embed/job_app?for=stripe&token=8172487",
         "greenhouse", "stripe", "8172487"),
        ("https://stripe.com/jobs/search?gh_jid=8172487", "greenhouse", None, "8172487"),
        ("https://jobs.lever.co/palantir/1a2b3c4d-0000-0000-0000-000000000000",
         "lever", "palantir", "1a2b3c4d-0000-0000-0000-000000000000"),
        ("https://api.lever.co/v0/postings/mistral?mode=json", "lever", "mistral", None),
        ("https://jobs.ashbyhq.com/snowflake/abc-123", "ashby", "snowflake", "abc-123"),
        ("https://apply.workable.com/huggingface/j/F4C096B22E", "workable", "huggingface", "F4C096B22E"),
        ("https://apply.workable.com/j/F4C096B22E", "workable", None, "F4C096B22E"),
        ("https://jobs.smartrecruiters.com/Visa/744000000000000-senior-engineer",
         "smartrecruiters", "Visa", "744000000000000"),
        ("https://sailpoint.wd1.myworkdayjobs.com/en-US/SailPoint/job/United-States/Eng_R014152",
         "workday", "sailpoint", "job/United-States/Eng_R014152"),
        ("https://chime.breezy.hr/p/abc123", "breezy", "chime", "abc123"),
        ("https://channable.recruitee.com/o/senior-engineer", "recruitee", "channable", "senior-engineer"),
        ("https://acme.jobs.personio.de/job/123456", "personio", "acme", "123456"),
        ("https://acme.teamtailor.com/jobs/998877", "teamtailor", "acme", "998877"),
        ("https://careers.example.com/openings/42", "unknown", None, None),
        ("", "unknown", None, None),
    ],
)
def test_identify(url, ats, token, job_id):
    ref = identify(url)
    assert ref["ats"] == ats
    assert ref["token"] == token
    assert ref["job_id"] == job_id


def test_identify_workday_site():
    ref = identify("https://sailpoint.wd1.myworkdayjobs.com/en-US/SailPoint/job/United-States/Eng_R014152")
    assert ref["site"] == "SailPoint"
    assert ref["host"] == "sailpoint.wd1.myworkdayjobs.com"


@pytest.mark.parametrize(
    "wrapped,expected",
    [
        (
            "https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fjobs.lever.co%2Fpalantir%2Fabc-123&urlhash=x",
            "https://jobs.lever.co/palantir/abc-123",
        ),
        (
            "https://tracking.example.com/r?dest=https%3A%2F%2Fjobs.ashbyhq.com%2Fsnowflake%2Fabc",
            "https://jobs.ashbyhq.com/snowflake/abc",
        ),
        # Already an ATS URL → untouched (never unwrap our own target)
        ("https://job-boards.greenhouse.io/stripe/jobs/1", "https://job-boards.greenhouse.io/stripe/jobs/1"),
        # Unknown wrapper → untouched
        ("https://www.indeed.com/rc/clk?jk=abc", "https://www.indeed.com/rc/clk?jk=abc"),
    ],
)
def test_unwrap_redirect(wrapped, expected):
    assert unwrap_redirect(wrapped) == expected


def test_identify_unwraps_redirect():
    ref = identify(
        "https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fjobs.lever.co%2Fpalantir%2Fabc-123"
    )
    assert (ref["ats"], ref["token"], ref["job_id"]) == ("lever", "palantir", "abc-123")


def test_token_hint_applied_for_gh_jid():
    """A custom-domain ?gh_jid= URL needs an injected board token."""
    verifier = SourceVerifier()
    captured = {}

    def fake_check_greenhouse(ref, out, **kwargs):
        captured.update(ref)
        out.status = STATUS_OPEN
        out.confidence = 1.0

    verifier._check_greenhouse = fake_check_greenhouse  # type: ignore[assignment]
    verifier.verify("https://stripe.com/jobs/search?gh_jid=8172487", token_hint="stripe")
    assert captured["token"] == "stripe"

    verifier2 = SourceVerifier()
    captured.clear()
    verifier2._check_greenhouse = fake_check_greenhouse  # type: ignore[assignment]
    verifier2.verify("https://stripe.com/jobs/search?gh_jid=8172487",
                     token_hint={"ats": "lever", "token": "nope"})
    assert captured["token"] is None  # a mismatched ATS hint is ignored


def test_token_hint_fills_unknown_ats():
    verifier = SourceVerifier()
    captured = {}

    def fake_check_greenhouse(ref, out, **kwargs):
        captured.update(ref)
        out.status = STATUS_OPEN

    verifier._check_greenhouse = fake_check_greenhouse  # type: ignore[assignment]
    verifier.verify("https://careers.example.com/job/1?gh_jid=42",
                    token_hint={"ats": "greenhouse", "token": "example"})
    assert captured["token"] == "example"


def test_board_ref_from_urls_and_company():
    assert board_ref_from_urls("", "https://jobs.lever.co/acme") == {"ats": "lever", "token": "acme"}
    assert board_ref_from_urls("https://example.com/careers") is None
    # Declared ATS type with no URL → derived from the company name
    ref = board_ref_from_company({"name": "Hugging Face", "ats_system": {"type": "workable"}})
    assert ref == {"ats": "workable", "token": "huggingface", "derived": True}
    # Stored URL wins over the derived guess
    ref = board_ref_from_company({
        "name": "Snowflake",
        "ats_url": "https://jobs.ashbyhq.com/snowflake",
        "ats_system": {"type": "ashby"},
    })
    assert ref == {"ats": "ashby", "token": "snowflake", "derived": False}


def test_collapsed_to_root():
    assert SourceVerifier._collapsed_to_root(
        "https://acme.com/careers/job/123", "https://acme.com/careers"
    )
    assert not SourceVerifier._collapsed_to_root(
        "https://acme.com/careers/job/123", "https://acme.com/careers/job/123"
    )
    assert not SourceVerifier._collapsed_to_root(
        "https://acme.com/careers/job/123", "https://other.com/careers"
    )


def test_extract_jsonld_jobposting():
    html = """
    <html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting","title":"Platform Engineer",
     "datePosted":"2026-01-02","validThrough":"2026-02-01"}
    </script></head><body>ok</body></html>
    """
    node = SourceVerifier._extract_jsonld_jobposting(html)
    assert node and node["title"] == "Platform Engineer"


def test_extract_jsonld_jobposting_in_graph():
    html = """
    <script type="application/ld+json">
    {"@context":"https://schema.org","@graph":[
      {"@type":"Organization","name":"Acme"},
      {"@type":"JobPosting","title":"SRE"}]}
    </script>
    """
    node = SourceVerifier._extract_jsonld_jobposting(html)
    assert node and node["title"] == "SRE"


def test_verify_never_raises_on_garbage():
    verifier = SourceVerifier()
    result = verifier.verify("not a url at all")
    assert result.status in ("open", "closed", "unknown")


def test_best_picks_open_over_closed():
    from src.services.source_verify import VerifyResult

    verifier = SourceVerifier()
    closed = VerifyResult(status=STATUS_CLOSED, confidence=0.99)
    opened = VerifyResult(status=STATUS_OPEN, confidence=0.6)
    unknown = VerifyResult(status="unknown", confidence=0.1)
    assert verifier.best([closed, unknown, opened]) is opened
