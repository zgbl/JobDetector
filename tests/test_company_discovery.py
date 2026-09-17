"""Offline unit tests for the company-discovery parser and helpers.

All fixtures are real shapes taken from HN "Who is hiring?" posts and board
payloads, so a parser regression fails here instead of silently producing
garbage company names.

Run: ``pytest tests/test_company_discovery.py -q``
"""
from __future__ import annotations

from src.services.company_discovery import (
    CompanyDiscoveryService,
    ResolvedCandidate,
    RawCandidate,
    board_home,
    expand_acronym,
    extract_company_name,
    extract_domain,
    extract_urls,
    is_job_seeker,
    looks_like_location,
    make_fingerprint,
    name_from_token,
    normalize_name,
    parse_hn_posting,
    slugify,
    strip_html,
)


# ---------------------------------------------------------------------------
# Company name extraction — every case is a real HN post opening line
# ---------------------------------------------------------------------------
def test_extract_company_name_real_shapes():
    cases = [
        ("Freeform ( http://freeform.co ) | Software Engineers | Full-time | Onsite | Hawthorne, CA", "Freeform"),
        ("Remote (US) Close ( https://close.com ) | Senior/Staff Backend Engineer", "Close"),
        ("Anterior (Sequoia-backed, Series B) | Senior Member of Technical Staff | On-Site", "Anterior"),
        ("Pango (YC S26) | Founding Software Engineer | On-site (hybrid) in Stockholm", "Pango"),
        ("At Tether ( https://tether.io/ ) we're hiring!", "Tether"),
        ("Lumen Labs | Robotics / Hardware Engineer | San Francisco, CA | ONSITE", "Lumen Labs"),
        ("We're hiring at Langfuse — now part of ClickHouse.", "Langfuse"),
        ("Ours Privacy | Senior Platform Engineer | Remote (US) | Full-time", "Ours Privacy"),
        ("Seeq is hiring a Senior Software Engineer", "Seeq"),
        ("NYC | ONSITE (hybrid) Norm Ai, the agentic law company", "NYC"),
    ]
    for text, expected in cases:
        assert extract_company_name(text) == expected, text


def test_extract_company_name_strips_domain_suffix():
    assert extract_company_name("Oscilar.com | Sr/Staff Software Engineers") == "Oscilar"


def test_extract_company_name_rejects_junk():
    for text in ("", "| | |", "Remote | ONSITE", "  ", "!!! ###"):
        assert extract_company_name(text) == "", text


def test_expand_acronym_prefers_full_name():
    text = "BCC | Platform Systems Engineers | Bethesda MD Black Canyon Consulting (BCC) is hiring"
    assert expand_acronym("BCC", text) == "Black Canyon Consulting"
    # No expansion when the acronym does not match
    assert expand_acronym("BCC", "Some Other Co (XYZ) is hiring") == "BCC"
    # Only short all-caps tokens are candidates
    assert expand_acronym("Black Canyon", "Black Canyon (BC) is hiring") == "Black Canyon"
    # A bare city name must NOT be stripped — these are real company names
    assert expand_acronym("BCG", "Boston Consulting Group (BCG) is hiring") == "Boston Consulting Group"
    assert expand_acronym("BCC", "Bethesda MD Black Canyon Consulting (BCC) is hiring") == "Black Canyon Consulting"


# ---------------------------------------------------------------------------
# Domain extraction
# ---------------------------------------------------------------------------
def test_extract_domain_skips_non_company_urls():
    urls = [
        "https://news.ycombinator.com/item?id=1",
        "https://twitter.com/acme",
        "https://www.linkedin.com/company/acme",
        "https://jobs.ashbyhq.com/acme/1234",
        "https://www.acme.com/careers",
    ]
    assert extract_domain(urls) == "acme.com"


def test_extract_domain_drops_idn_and_punycode_labels():
    assert extract_domain(["https://電.anterior.app/"]) == "anterior.app"
    assert extract_domain(["https://xn--xp5a.anterior.app/"]) == "anterior.app"


def test_extract_domain_empty_when_nothing_usable():
    assert extract_domain([]) == ""
    assert extract_domain(["https://github.com/foo"]) == ""


def test_extract_urls_from_html_and_text():
    raw = 'See <a href="https://acme.com/careers">acme</a> or https://jobs.lever.co/acme/abc-123.'
    urls = extract_urls(raw)
    assert "https://acme.com/careers" in urls
    assert any("jobs.lever.co/acme" in u for u in urls)
    # trailing punctuation is trimmed
    assert not any(u.endswith(".") for u in urls)


# ---------------------------------------------------------------------------
# Post classification / parsing
# ---------------------------------------------------------------------------
def test_is_job_seeker():
    assert is_job_seeker("Location: London, UK\nWilling to relocate: No\nSoftware Engineer")
    assert is_job_seeker("Availability: Immediately, seeking a role in platform engineering")
    assert not is_job_seeker("Acme | Senior Platform Engineer | Remote | Full-time")


def test_strip_html_handles_hn_markup():
    raw = "<p>Acme is hiring<br>Remote role</p><p>Apply now</p>"
    text = strip_html(raw)
    assert "Acme is hiring" in text
    assert "<" not in text


def test_parse_hn_posting_extracts_candidate():
    raw = (
        '<p>Langfuse (YC W23) | Senior Platform Engineer | Remote (EU) | Full-time</p>'
        '<p>We build LLM observability tooling. Apply: '
        '<a href="https://jobs.ashbyhq.com/langfuse/abc-123">jobs.ashbyhq.com</a></p>'
    )
    candidate = parse_hn_posting(raw, thread_id="1", thread_title="Ask HN: Who is hiring?", item_id="42")
    assert candidate is not None
    assert candidate.name == "Langfuse"
    assert candidate.source == "hn_whoishiring"
    assert candidate.source_url == "https://news.ycombinator.com/item?id=42"
    assert candidate.ats_urls == ["https://jobs.ashbyhq.com/langfuse/abc-123"]


def test_parse_hn_posting_skips_seekers_and_short_posts():
    seeker = "<p>Location: Berlin, Germany<br>Willing to relocate: Yes<br>Senior Backend Engineer</p>"
    assert parse_hn_posting(seeker, "1", "t", "2") is None
    assert parse_hn_posting("<p>+1</p>", "1", "t", "2") is None


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def test_normalize_and_slugify():
    assert normalize_name("Acme Inc.") == "acme"
    assert normalize_name("Hugging Face") == "hugging face"
    assert slugify("Hugging Face") == "huggingface"
    # slugify is a pure slugifier; legal-suffix stripping is normalize_name's job
    assert slugify("Norm Ai, Inc.") == "normaiinc"
    assert slugify(normalize_name("Norm Ai, Inc.")) == "normai"


def test_name_from_token():
    assert name_from_token("norm-ai") == "Norm Ai"
    assert name_from_token("deeter_analytics") == "Deeter Analytics"
    assert name_from_token("") == ""


def test_looks_like_location():
    for value in ("NYC", "Remote", "London", "EMEA", "San Francisco"):
        assert looks_like_location(value), value
    for value in ("Anterior", "Langfuse", "Close"):
        assert not looks_like_location(value), value


def test_board_home_urls():
    assert board_home("greenhouse", "stripe") == "https://job-boards.greenhouse.io/stripe"
    assert board_home("ashby", "langfuse") == "https://jobs.ashbyhq.com/langfuse"
    assert board_home("bamboohr", "endlessaccess") == "https://endlessaccess.bamboohr.com/careers"
    assert board_home("unknown_ats", "x") == ""


def test_fingerprint_prefers_board_identity():
    with_board = ResolvedCandidate(name="Acme", ats="ashby", board_token="Acme", domain="acme.com")
    assert make_fingerprint(with_board) == "ashby|acme"
    domain_only = ResolvedCandidate(name="Acme", domain="Acme.com")
    assert make_fingerprint(domain_only) == "domain|acme.com"
    name_only = ResolvedCandidate(name="Acme Inc")
    assert make_fingerprint(name_only) == "name|acme"


# ---------------------------------------------------------------------------
# Relevance scoring & dedup (no network)
# ---------------------------------------------------------------------------
def test_score_relevance_rewards_target_track_titles():
    service = CompanyDiscoveryService()
    hot, matched, it_jobs = service.score_relevance(
        ["Senior Platform Engineer", "Staff Infrastructure Engineer", "Kubernetes SRE"],
        "We run Kubernetes and Terraform",
    )
    cold, _, _ = service.score_relevance(
        ["Sales Director", "Account Executive", "Office Manager"], "Sell things"
    )
    assert hot > cold
    assert hot >= 5
    assert "platform engineer" in matched or "infrastructure" in matched
    assert it_jobs >= 2


def test_mark_duplicates_flags_known_and_repeated_companies():
    service = CompanyDiscoveryService()
    candidates = [
        ResolvedCandidate(name="Fresh Co", ats="ashby", board_token="fresh", domain="fresh.com"),
        # same company again in the same batch, different link shape
        ResolvedCandidate(name="Fresh Co Inc", ats="greenhouse", board_token="freshco", domain="freshco.com"),
        # would be a duplicate by name of the first
        ResolvedCandidate(name="fresh", domain="fresh.io"),
        ResolvedCandidate(name="Other Co", ats="lever", board_token="other", domain="other.com"),
    ]
    for candidate in candidates:
        candidate.normalized_name = normalize_name(candidate.name)
        candidate.fingerprint = make_fingerprint(candidate)

    marked, duplicates = service.mark_duplicates(candidates, db=None)
    statuses = {c.name: c.status for c in marked}
    assert statuses["Fresh Co"] == "pending"
    assert statuses["Fresh Co Inc"] == "duplicate"  # same normalized name
    assert statuses["fresh"] == "duplicate"
    assert statuses["Other Co"] == "pending"
    assert duplicates == 2


def test_prioritize_interleaves_classes():
    from scripts.discover_companies import prioritize

    raw = [
        RawCandidate(name="A", domain="a.com"),
        RawCandidate(name="B", ats_urls=["https://jobs.ashbyhq.com/b"]),
        RawCandidate(name="C"),
        RawCandidate(name="D", ats_urls=["https://jobs.lever.co/d"]),
        RawCandidate(name="E", domain="e.com"),
    ]
    order = [c.name for c in prioritize(raw)]
    # The first three must cover all three classes, not just the easy ones.
    assert order[:3] == ["B", "A", "C"]
    assert set(order) == {"A", "B", "C", "D", "E"}
