"""Offline unit tests for the ATS source-verification engine.

No network access is required: these tests cover URL identification, redirect
unwrapping, token hints, JSON-LD parsing and the generic-page heuristics.
Live ATS behaviour is exercised by ``scripts/verify_source_smoke.py``.

Run: ``pytest tests/test_source_verify.py -q``
"""
from __future__ import annotations

import re

import pytest

from src.services.source_verify import (
    SourceVerifier,
    board_ref_from_company,
    board_ref_from_urls,
    identify,
    unwrap_redirect,
    to_english_reason,
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


# ---------------------------------------------------------------------------
# Localisation
# ---------------------------------------------------------------------------
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# Sample values substituted into the engine's f-string placeholders so the
# translation rules can be exercised without running a real verification.
PLACEHOLDER_SAMPLES = {
    "{code}": "404",
    "{deadline}": "2026-01-01",
    "{exc}": "boom",
    "{phrase}": "no longer accepting applications",
    "{valid_through}": "2026-01-01",
}


def _fill_placeholders(template: str) -> str:
    out = template
    for key, value in PLACEHOLDER_SAMPLES.items():
        out = out.replace(key, value)
    # any remaining {len(...)} / {n} style placeholder → 3
    return re.sub(r"\{[^{}]*\}", "3", out)


def test_every_reason_has_an_english_rule():
    """
    Every Chinese reason literal in the engine must translate to English.

    This is the guard that keeps the English website from rendering Chinese:
    a newly added ``out.reason = "..."`` without a matching rule fails here.
    """
    import pathlib

    from src.services import source_verify

    source = pathlib.Path(source_verify.__file__).read_text(encoding="utf-8")
    templates = {
        m.group(1)
        for m in re.finditer(r'\.reason\s*=\s*f?"([^"]*)"', source)
    }
    assert templates, "no reason literals found — did the regex stop matching?"

    untranslated = []
    for template in sorted(templates):
        if not CJK_RE.search(template):
            continue  # already English
        sample = _fill_placeholders(template)
        english = to_english_reason(sample)
        if english == sample or CJK_RE.search(english):
            untranslated.append(template)

    assert not untranslated, "missing English rules for:\n" + "\n".join(untranslated)


@pytest.mark.parametrize(
    "reason,expected_fragment",
    [
        ("Greenhouse 源头已下架该岗位（详情 404 且 board 列表无此 ID）",
         "Greenhouse has taken this posting down"),
        ("Lever 源头 API 返回该岗位仍在招", "Lever source API confirms"),
        ("Ashby 源头 board 已无此岗位（当前在招 346 个）", "346 roles currently open"),
        ("Workday 详情请求异常 (HTTP 500)", "Workday detail request failed (HTTP 500)"),
        ("无法访问该页面（网络错误/超时）", "could not be reached"),
        ("校验过程异常: boom", "Verification raised an error: boom"),
    ],
)
def test_to_english_reason(reason, expected_fragment):
    english = to_english_reason(reason)
    assert expected_fragment.lower() in english.lower()
    assert not CJK_RE.search(english)


def test_verify_result_dict_carries_reason_en():
    from src.services.source_verify import VerifyResult

    result = VerifyResult(reason="Greenhouse 源头 API 返回该岗位仍在招")
    data = result.to_dict()
    assert data["reason"].startswith("Greenhouse 源头")
    assert "still open" in data["reason_en"]
    assert not CJK_RE.search(data["reason_en"])


def test_to_english_reason_is_idempotent_for_english_input():
    assert to_english_reason("Already English") == "Already English"
    assert to_english_reason("") == ""
