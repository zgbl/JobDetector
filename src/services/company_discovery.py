"""
Company discovery
=================

Finds companies that are **not yet in the database**, resolves which ATS they
use, and produces reviewable candidates.

The rest of the pipeline already existed (``ats_discovery`` resolves a domain →
ATS, ``prod_scraper`` scrapes → filters → dedupes → inserts). What was missing
was the very first step: nothing generated *new* company names. This module is
that step.

Sources
-------
``hn``  Hacker News "Ask HN: Who is hiring?" (Algolia API, no key required).
        Monthly threads, ~250 hiring posts each, engineering-heavy. Roughly 19%
        of posts link straight to their ATS board, which gives us the board
        token for free.
``yc``  The YC company directory (community mirror, no key required). Curated,
        filterable by batch / industry, and includes an ``isHiring`` flag.

Resolution order (cheapest and most reliable first)
---------------------------------------------------
1. ``post_link``      – the source post already contains an ATS URL.
2. ``slug_probe``     – probe the public board APIs with name/domain slugs.
3. ``careers_crawl``  – crawl the company site for a careers → ATS link.
4. unresolved         – kept as a candidate with no ATS, for manual review.

Nothing here writes to ``companies``. Candidates land in ``company_candidates``
with ``status="pending"`` so a human can approve them.
"""

from __future__ import annotations

import html as html_mod
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from src.services.source_verify import identify

logger = logging.getLogger(__name__)

USER_AGENT = "JobDetectorBot/1.0 (+https://jobdetector.blackrice.top)"
DEFAULT_TIMEOUT = 15

HN_API = "https://hn.algolia.com/api/v1"
YC_ALL_COMPANIES = "https://yc-oss.github.io/api/companies/all.json"

# --- board endpoints used for slug probing -------------------------------
BOARD_PROBES: Tuple[Tuple[str, str, str], ...] = (
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{token}/jobs", "json:jobs"),
    ("lever", "https://api.lever.co/v0/postings/{token}?mode=json", "json:list"),
    ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{token}", "json:jobs"),
    ("workable", "https://apply.workable.com/api/v1/widget/accounts/{token}", "json:jobs"),
    ("recruitee", "https://{token}.recruitee.com/api/offers/", "json:offers"),
    ("smartrecruiters", "https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=1", "json:content"),
    ("bamboohr", "https://{token}.bamboohr.com/careers/list", "json:result"),
)

# Public board home pages, used for the stored ``ats_url``.
BOARD_HOME: Dict[str, str] = {
    "greenhouse": "https://job-boards.greenhouse.io/{token}",
    "lever": "https://jobs.lever.co/{token}",
    "ashby": "https://jobs.ashbyhq.com/{token}",
    "workable": "https://apply.workable.com/{token}/",
    "recruitee": "https://{token}.recruitee.com",
    "smartrecruiters": "https://jobs.smartrecruiters.com/{token}",
    "bamboohr": "https://{token}.bamboohr.com/careers",
    "breezy": "https://{token}.breezy.hr",
    "personio": "https://{token}.jobs.personio.de",
    "teamtailor": "https://{token}.teamtailor.com/jobs",
    "workday": "https://{token}.myworkdayjobs.com",
}


def board_home(ats: str, token: str) -> str:
    template = BOARD_HOME.get(ats)
    if not template or not token:
        return ""
    return template.format(token=token)

# Sources that should never be treated as the company's own domain.
SKIP_DOMAINS = (
    "news.ycombinator.com",
    "ycombinator.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "github.com",
    "medium.com",
    "notion.site",
    "docs.google.com",
    "forms.gle",
    "youtube.com",
    "crunchbase.com",
    "wellfound.com",
    "angel.co",
    "indeed.com",
    "glassdoor.com",
    "wikipedia.org",
    "google.com",
)

# Phrases that mark a comment as "looking for work" rather than a job posting.
SEEKER_MARKERS = (
    "willing to relocate:",
    "right to work:",
    "availability:",
    "looking for work",
    "seeking a role",
    "resume:",
    "résumé:",
    "i am looking for",
)

# A coarse pre-filter tuned to the product's target track. The real ranking
# happens later in the digest; this only decides what is worth storing.
DEFAULT_RELEVANCE_KEYWORDS: Tuple[str, ...] = (
    "platform engineer",
    "infrastructure",
    "infra",
    "cloud",
    "devops",
    "sre",
    "site reliability",
    "kubernetes",
    "terraform",
    "distributed systems",
    "backend",
    "ai engineer",
    "ml engineer",
    "machine learning",
    "llm",
    "genai",
    "rag",
    "data platform",
    "solution architect",
    "staff engineer",
    "principal engineer",
    "founding engineer",
    "golang",
    "rust",
    "python",
)

SENIORITY_BONUS = ("staff", "principal", "lead", "architect", "senior", "founding")

PIPE_SPLIT_RE = re.compile(r"\s*[|·]\s*")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
HTML_URL_RE = re.compile(r'href="([^"]+)"', re.I)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@dataclass
class RawCandidate:
    """A company name harvested from an external source, before resolution."""

    name: str
    domain: str = ""
    source: str = ""
    source_url: str = ""
    source_title: str = ""
    source_context: str = ""
    roles_text: str = ""
    ats_urls: List[str] = field(default_factory=list)
    slug_hints: List[str] = field(default_factory=list)


@dataclass
class ResolvedCandidate:
    """A raw candidate plus whatever we could learn about its ATS."""

    name: str
    normalized_name: str = ""
    domain: str = ""
    source: str = ""
    source_url: str = ""
    source_title: str = ""
    source_context: str = ""
    roles_text: str = ""
    ats: str = ""
    ats_url: str = ""
    board_token: str = ""
    open_jobs: int = 0
    sample_titles: List[str] = field(default_factory=list)
    it_jobs: int = 0
    relevance_score: int = 0
    matched_keywords: List[str] = field(default_factory=list)
    resolve_method: str = ""
    confidence: float = 0.0
    warning: str = ""
    status: str = "pending"
    notes: str = ""
    fingerprint: str = ""
    discovered_at: str = ""
    resolved_at: str = ""
    reviewed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if not data["discovered_at"]:
            data["discovered_at"] = _now_iso()
        if not data["resolved_at"]:
            data["resolved_at"] = _now_iso()
        if not data["normalized_name"]:
            data["normalized_name"] = normalize_name(self.name)
        if not data["fingerprint"]:
            data["fingerprint"] = make_fingerprint(self)
        return data


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_name(name: str) -> str:
    """Lowercase, strip legal suffixes and punctuation — used for dedup."""
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", " ", str(name or "").lower())
    text = re.sub(
        r"\b(inc|llc|ltd|limited|corp|corporation|co|gmbh|plc|sa|ag|bv|oy|pte|holdings)\b",
        " ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def name_from_token(token: str) -> str:
    """'norm-ai' → 'Norm Ai', 'deeter_analytics' → 'Deeter Analytics'."""
    return re.sub(r"\s{2,}", " ", re.sub(r"[-_]+", " ", str(token or ""))).strip().title()


# Posts frequently lead with the work arrangement instead of the company name,
# so a "name" that is really a place must not be trusted.
_LOCATION_NAMES = {
    "nyc", "sf", "sfo", "la", "lax", "dc", "uk", "us", "usa", "eu", "emea", "apac",
    "remote", "onsite", "on-site", "hybrid", "anywhere", "worldwide", "global",
    "london", "berlin", "paris", "amsterdam", "dublin", "zurich", "munich",
    "toronto", "vancouver", "boston", "seattle", "austin", "denver", "chicago",
    "atlanta", "miami", "bangalore", "singapore", "sydney", "tokyo", "tel aviv",
    "san francisco", "new york", "los angeles", "san diego", "santa clara",
    "san jose", "palo alto", "mountain view", "new delhi", "hong kong",
}


def looks_like_location(name: str) -> bool:
    return normalize_name(name).strip() in _LOCATION_NAMES


_ACRONYM_EXPANSION_RE = re.compile(r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,4})\s*\(([A-Z]{2,5})\)")

# Leading tokens that are really a place, not part of the company name:
# "Bethesda MD Black Canyon Consulting (BCC)" → "Black Canyon Consulting".
_US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il",
    "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt",
    "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri",
    "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
}


def _strip_leading_location_words(name: str) -> str:
    """
    Strip a leading "City ST" pair ("Bethesda MD Black Canyon Consulting").

    Deliberately narrow: only the two-letter state pattern is unambiguous.
    Dropping bare city names would turn "Boston Consulting Group" into
    "Consulting Group".
    """
    words = name.split()
    changed = True
    while changed and len(words) > 3:
        changed = False
        if words[1].lower() in _US_STATES:
            words = words[2:]
            changed = True
    return " ".join(words)


def expand_acronym(name: str, text: str) -> str:
    """
    'BCC' plus the sentence "Black Canyon Consulting (BCC) is hiring" → the full
    name, which is far more useful than the acronym.
    """
    if not re.fullmatch(r"[A-Z]{2,5}", name or ""):
        return name
    match = _ACRONYM_EXPANSION_RE.search(text or "")
    if match and match.group(2) == name:
        full = _strip_leading_location_words(match.group(1).strip())
        if 2 <= len(full) <= 60:
            return full
    return name


def make_fingerprint(candidate: ResolvedCandidate) -> str:
    if candidate.ats and candidate.board_token:
        return f"{candidate.ats}|{candidate.board_token.lower()}"
    if candidate.domain:
        return f"domain|{candidate.domain.lower()}"
    return f"name|{normalize_name(candidate.name)}"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class CompanyDiscoveryService:
    """Harvest → resolve → score. Never writes to the database."""

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        relevance_keywords: Optional[Iterable[str]] = None,
        crawl_fallback: bool = True,
    ):
        self.timeout = timeout
        self.relevance_keywords = tuple(relevance_keywords or DEFAULT_RELEVANCE_KEYWORDS)
        self.crawl_fallback = crawl_fallback
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9,*/*;q=0.8"})

    # -- HTTP helper -------------------------------------------------------
    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        kwargs.setdefault("timeout", self.timeout)
        for attempt in range(2):
            try:
                return self.http.get(url, **kwargs)
            except requests.exceptions.SSLError:
                try:
                    return self.http.get(url, verify=False, **kwargs)
                except Exception:  # noqa: BLE001
                    pass
            except Exception as exc:  # noqa: BLE001
                logger.debug("GET failed %s: %s", url, exc)
            time.sleep(0.4 * (attempt + 1))
        return None

    # ==================================================================
    # Sources
    # ==================================================================
    def fetch_hn(self, months: int = 1, max_posts: int = 500) -> List[RawCandidate]:
        """Harvest companies from the latest N "Ask HN: Who is hiring?" threads."""
        thread_ids = self._hn_recent_thread_ids(months)
        out: List[RawCandidate] = []
        for thread_id, title in thread_ids:
            out.extend(self._hn_thread_candidates(thread_id, title, max_posts=max_posts))
            if len(out) >= max_posts:
                break
        return out[:max_posts]

    def _hn_recent_thread_ids(self, months: int) -> List[Tuple[str, str]]:
        resp = self._get(
            f"{HN_API}/search_by_date",
            params={"query": '"Ask HN: Who is hiring?"', "tags": "story", "hitsPerPage": 50},
        )
        if resp is None or resp.status_code != 200:
            logger.warning("HN thread lookup failed")
            return []
        try:
            hits = resp.json().get("hits", [])
        except ValueError:
            return []
        threads = [
            (str(h.get("objectID")), h.get("title") or "")
            for h in hits
            if re.match(r"^Ask HN: Who is hiring\?", h.get("title") or "")
        ]
        threads.sort(key=lambda item: item[0], reverse=True)  # objectID increases over time
        return threads[: max(1, months)]

    def _hn_thread_candidates(self, thread_id: str, title: str, max_posts: int) -> List[RawCandidate]:
        resp = self._get(
            f"{HN_API}/search",
            params={"tags": f"comment,story_{thread_id}", "hitsPerPage": 1000},
        )
        if resp is None or resp.status_code != 200:
            logger.warning("HN comment fetch failed for %s", thread_id)
            return []
        try:
            hits = resp.json().get("hits", [])
        except ValueError:
            return []

        out: List[RawCandidate] = []
        for hit in hits:
            # Top-level comments only: replies are discussion, not postings.
            if str(hit.get("parent_id")) != str(thread_id):
                continue
            raw_html = hit.get("comment_text") or ""
            candidate = parse_hn_posting(
                raw_html,
                thread_id=thread_id,
                thread_title=title,
                item_id=str(hit.get("objectID") or ""),
            )
            if candidate:
                out.append(candidate)
            if len(out) >= max_posts:
                break
        return out

    def fetch_yc(
        self,
        batches: Optional[Iterable[str]] = None,
        only_hiring: bool = True,
        industries: Optional[Iterable[str]] = None,
        limit: int = 400,
    ) -> List[RawCandidate]:
        """Harvest companies from the YC directory."""
        resp = self._get(YC_ALL_COMPANIES)
        if resp is None or resp.status_code != 200:
            logger.warning("YC directory fetch failed")
            return []
        try:
            companies = resp.json()
        except ValueError:
            return []
        if not isinstance(companies, list):
            return []

        batch_filter = {str(b).lower() for b in batches} if batches else None
        industry_filter = {str(i).lower() for i in industries} if industries else None

        out: List[RawCandidate] = []
        for company in companies:
            if not isinstance(company, dict):
                continue
            name = (company.get("name") or "").strip()
            website = (company.get("website") or "").strip()
            if not name or not website:
                continue
            if only_hiring and company.get("isHiring") is False:
                continue
            if company.get("status") and str(company["status"]).lower() not in ("active", ""):
                continue
            if batch_filter and str(company.get("batch") or "").lower() not in batch_filter:
                continue
            if industry_filter:
                inds = {str(i).lower() for i in (company.get("industries") or [])}
                if not (inds & industry_filter):
                    continue
            domain = urlparse(website if website.startswith("http") else f"https://{website}").netloc
            out.append(
                RawCandidate(
                    name=name,
                    domain=domain,
                    source="yc_directory",
                    source_url=company.get("url") or "",
                    source_title=company.get("batch") or "",
                    source_context=(company.get("one_liner") or "")[:400],
                    roles_text=" ".join(
                        [company.get("one_liner") or "", company.get("long_description") or ""]
                    )[:1500],
                    slug_hints=[s for s in (company.get("slug"),) if s],
                )
            )
            if len(out) >= limit:
                break
        return out

    # ==================================================================
    # Resolution
    # ==================================================================
    def resolve(self, raw: RawCandidate) -> ResolvedCandidate:
        """Turn a raw candidate into a resolved one. Never raises."""
        candidate = ResolvedCandidate(
            name=raw.name,
            domain=raw.domain,
            source=raw.source,
            source_url=raw.source_url,
            source_title=raw.source_title,
            source_context=raw.source_context,
            roles_text=raw.roles_text,
        )
        # Needed by _resolve_ats (greenhouse board-name cross-check) — set it first.
        candidate.normalized_name = normalize_name(candidate.name)
        try:
            self._resolve_ats(candidate, raw)
        except Exception as exc:  # noqa: BLE001
            logger.debug("resolve failed for %s: %s", raw.name, exc)
            candidate.notes = f"resolve error: {exc}"

        if candidate.ats and candidate.board_token:
            candidate.relevance_score, candidate.matched_keywords, candidate.it_jobs = self.score_relevance(
                candidate.sample_titles, candidate.roles_text
            )
        candidate.fingerprint = make_fingerprint(candidate)
        candidate.resolved_at = _now_iso()
        candidate.discovered_at = _now_iso()
        return candidate

    def _resolve_ats(self, candidate: ResolvedCandidate, raw: RawCandidate) -> None:
        # 1) The post already links to the board — the cheapest and most accurate.
        for url in raw.ats_urls:
            ref = identify(url)
            if ref.get("ats") in (None, "unknown") or not ref.get("token"):
                continue
            jobs, titles, board_name = self.validate_board(ref["ats"], ref["token"])
            if jobs > 0:
                self._accept(candidate, ref["ats"], ref["token"], url, jobs, titles,
                             method="post_link", confidence=0.95, board_name=board_name)
                return

        # 2) Probe the public board APIs with name / domain / YC-slug hints.
        for token, origin, confidence in self._token_candidates(raw):
            for ats, _template, _shape in BOARD_PROBES:
                jobs, titles, board_name = self.validate_board(ats, token)
                if jobs <= 0:
                    continue
                trust = confidence
                if ats == "greenhouse" and board_name:
                    # A board name match makes a guessed token far more trustworthy.
                    if normalize_name(board_name) == candidate.normalized_name or candidate.normalized_name in normalize_name(board_name):
                        trust = min(0.95, confidence + 0.25)
                    else:
                        trust = max(0.25, confidence - 0.25)
                url = board_home(ats, token)
                self._accept(candidate, ats, token, url, jobs, titles,
                             method=f"slug_probe:{origin}", confidence=trust, board_name=board_name)
                return

        # 3) Crawl the company site for a careers → ATS link.
        if self.crawl_fallback and raw.domain:
            found = self._crawl_for_ats(raw.domain)
            if found:
                ats, token, url = found
                jobs, titles, board_name = self.validate_board(ats, token)
                if jobs > 0:
                    self._accept(candidate, ats, token, url, jobs, titles,
                                 method="careers_crawl", confidence=0.8, board_name=board_name)
                    return

    def _token_candidates(self, raw: RawCandidate) -> List[Tuple[str, str, float]]:
        """(token, origin, confidence) — most trustworthy guesses first."""
        out: List[Tuple[str, str, float]] = []
        seen = set()
        domain_label = ""
        if raw.domain:
            domain_label = raw.domain.split(".")[0]

        for value, origin, confidence in (
            [(slugify(normalize_name(raw.name)), "name", 0.5)]
            + [(slugify(h), "source_hint", 0.6) for h in raw.slug_hints]
            + [(slugify(domain_label), "domain", 0.7)]
        ):
            if not value or value in seen:
                continue
            # A one-or-two character token would match far too much.
            if len(value) < 3:
                continue
            seen.add(value)
            out.append((value, origin, confidence))
        return out

    def validate_board(self, ats: str, token: str) -> Tuple[int, List[str], str]:
        """Return (open_jobs, sample_titles, board_name) for a board token."""
        if not token:
            return 0, [], ""
        template = next((t for a, t, _ in BOARD_PROBES if a == ats), None)
        if template is None:
            return 0, [], ""
        url = template.format(token=token)
        resp = self._get(url)
        if resp is None or resp.status_code != 200:
            return 0, [], ""
        try:
            data = resp.json()
        except ValueError:
            return 0, [], ""

        titles: List[str] = []
        board_name = ""
        if isinstance(data, dict):
            if isinstance(data.get("jobs"), list):
                titles = [str(j.get("title") or j.get("name") or "") for j in data["jobs"] if isinstance(j, dict)]
                if ats == "greenhouse":
                    board_name = str(data.get("name") or "")
            elif isinstance(data.get("offers"), list):
                titles = [str(o.get("title") or "") for o in data["offers"] if isinstance(o, dict)]
            elif isinstance(data.get("content"), list):
                titles = [str(o.get("name") or "") for o in data["content"] if isinstance(o, dict)]
            elif isinstance(data.get("result"), list):
                titles = [str(o.get("jobOpeningName") or o.get("title") or "")
                          for o in data["result"] if isinstance(o, dict)]
        elif isinstance(data, list):
            titles = [str(j.get("text") or j.get("title") or "") for j in data if isinstance(j, dict)]
        titles = [t for t in titles if t]
        return len(titles), titles[:15], board_name

    def _crawl_for_ats(self, domain: str) -> Optional[Tuple[str, str, str]]:
        """Reuse the existing site-crawling discovery service (async → sync)."""
        try:
            import asyncio

            from src.services.ats_discovery import ATSDiscoveryService

            result = asyncio.run(ATSDiscoveryService().discover_ats(domain))
        except Exception as exc:  # noqa: BLE001
            logger.debug("careers crawl failed for %s: %s", domain, exc)
            return None
        if not result:
            return None
        url, ats = result
        if not url or not ats:
            return None
        ref = identify(url)
        if ref.get("token"):
            return ats, ref["token"], url
        return None

    @staticmethod
    def _accept(candidate: ResolvedCandidate, ats: str, token: str, url: str,
                jobs: int, titles: List[str], method: str, confidence: float,
                board_name: str = "") -> None:
        candidate.ats = ats
        candidate.board_token = token
        candidate.ats_url = url
        candidate.open_jobs = jobs
        candidate.sample_titles = titles
        candidate.resolve_method = method
        candidate.confidence = round(confidence, 2)

        # The parsed name is sometimes a location ("NYC | ONSITE ... Norm Ai").
        # Once we know the board, prefer the board's own name, then the token.
        if looks_like_location(candidate.name):
            replacement = ""
            if board_name and not looks_like_location(board_name):
                replacement = board_name
            elif token:
                replacement = name_from_token(token)
            if replacement:
                candidate.notes = f"name corrected from '{candidate.name}' to '{replacement}'"
                candidate.name = replacement
                candidate.normalized_name = normalize_name(replacement)

        # A name and a board token that share nothing are a review smell: either
        # the post named a different entity, or the probe matched someone else.
        if candidate.name and token:
            name_slug = slugify(candidate.normalized_name or candidate.name)
            token_slug = slugify(token)
            if name_slug and token_slug and name_slug not in token_slug and token_slug not in name_slug:
                candidate.warning = (
                    f"名称 '{candidate.name}' 与 board token '{token}' 不一致，请确认是否同一家公司"
                )
                candidate.confidence = round(max(0.2, candidate.confidence - 0.2), 2)

    # ==================================================================
    # Scoring
    # ==================================================================
    def score_relevance(self, titles: List[str], text: str) -> Tuple[int, List[str], int]:
        """
        Coarse 0–10 relevance score + matched keywords + IT-role count.

        Signals: target-track keywords in the job titles, seniority markers, and
        how many of the board's roles look like IT/engineering roles at all.
        """
        joined = " ".join(titles).lower()
        blob = f"{joined} {text[:1200].lower()}"

        matched = [kw for kw in self.relevance_keywords if kw in blob]
        title_hits = [kw for kw in self.relevance_keywords if kw in joined]

        score = min(6, len(title_hits))  # titles matter most
        score += min(2, len(matched) // 4)
        if any(s in joined for s in SENIORITY_BONUS):
            score += 1
        if len(titles) >= 5:
            score += 1

        it_jobs = 0
        try:
            from src.services.language_filter import LanguageFilterService

            for title in titles:
                is_it, _ = LanguageFilterService.is_it_role(title, is_title=True)
                if is_it:
                    it_jobs += 1
        except Exception:  # noqa: BLE001
            it_jobs = len(titles)

        if it_jobs == 0 and titles:
            score = max(0, score - 3)

        return min(10, score), matched[:8], it_jobs

    # ==================================================================
    # Dedup
    # ==================================================================
    def mark_duplicates(self, candidates: List[ResolvedCandidate], db) -> Tuple[List[ResolvedCandidate], int]:
        """
        Flag candidates that already exist in ``companies`` (or earlier in this
        batch). Duplicates keep ``status="duplicate"`` so they are visible but
        never re-imported.
        """
        known_names: Dict[str, str] = {}
        known_domains: Dict[str, str] = {}
        known_boards: Dict[str, str] = {}
        if db is not None:
            try:
                for doc in db.companies.find({}, {"name": 1, "domain": 1, "ats_url": 1}):
                    if doc.get("name"):
                        known_names[normalize_name(doc["name"])] = doc["name"]
                    if doc.get("domain"):
                        known_domains[str(doc["domain"]).lower()] = doc["name"]
                    ref = identify(str(doc.get("ats_url") or ""))
                    if ref.get("token") and ref.get("ats") not in (None, "unknown"):
                        known_boards[f"{ref['ats']}|{ref['token'].lower()}"] = doc["name"]
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not load known companies: %s", exc)

        seen_batch: Dict[str, str] = {}
        seen_names: Dict[str, str] = {}
        duplicates = 0
        for candidate in candidates:
            if candidate.status != "pending":
                continue
            reason = ""
            board_key = f"{candidate.ats}|{candidate.board_token.lower()}" if candidate.ats and candidate.board_token else ""
            if board_key and board_key in known_boards:
                reason = f"already tracked as {known_boards[board_key]}"
            elif candidate.normalized_name and candidate.normalized_name in known_names:
                reason = f"company name already exists ({known_names[candidate.normalized_name]})"
            elif candidate.domain and candidate.domain.lower() in known_domains:
                reason = f"domain already exists ({known_domains[candidate.domain.lower()]})"

            if not reason and candidate.fingerprint in seen_batch:
                reason = f"duplicate of {seen_batch[candidate.fingerprint]} in this batch"
            # The same company often posts twice with different links/domains.
            if not reason and candidate.normalized_name and candidate.normalized_name in seen_names:
                reason = f"same company as {seen_names[candidate.normalized_name]} in this batch"

            if reason:
                candidate.status = "duplicate"
                candidate.notes = reason
                duplicates += 1
            else:
                seen_batch[candidate.fingerprint] = candidate.name
                if candidate.normalized_name:
                    seen_names[candidate.normalized_name] = candidate.name
        return candidates, duplicates


# ---------------------------------------------------------------------------
# HN post parsing (pure functions — unit tested)
# ---------------------------------------------------------------------------
def strip_html(raw_html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw_html or "")
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", html_mod.unescape(text)).strip()


def extract_urls(raw_html: str) -> List[str]:
    urls = [html_mod.unescape(u) for u in HTML_URL_RE.findall(raw_html or "")]
    urls += [html_mod.unescape(u) for u in URL_RE.findall(strip_html(raw_html))]
    out: List[str] = []
    for url in urls:
        cleaned = url.rstrip(".,);:'\"")
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def is_job_seeker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in SEEKER_MARKERS)


def extract_company_name(text: str) -> str:
    """Pull the hiring company out of the many shapes these posts take."""
    head = text[:400]

    # Shape A: "Company | Role | Location ..." (the most common table format)
    first_line = head.split("\n", 1)[0]
    if "|" in first_line:
        name = PIPE_SPLIT_RE.split(first_line)[0]
        cleaned = _clean_company(name)
        if cleaned:
            return cleaned

    # Shape B: "At Tether ( https://tether.io/ ) we're hiring!"
    match = re.search(r"\bAt\s+([A-Z][\w&.\-']*(?:\s+[A-Z][\w&.\-']*){0,3})\s*\(", head)
    if match:
        cleaned = _clean_company(match.group(1))
        if cleaned:
            return cleaned

    # Shape C: "We're hiring at Langfuse — ..." / "X is hiring"
    match = re.search(r"hiring at\s+([A-Z][\w&.\-']*(?:\s+[A-Z][\w&.\-']*){0,3})", head, re.I)
    if match:
        cleaned = _clean_company(match.group(1))
        if cleaned:
            return cleaned
    match = re.search(r"^([A-Z][\w&.\-']*(?:\s+[A-Z][\w&.\-']*){0,3})\s+is hiring", head)
    if match:
        cleaned = _clean_company(match.group(1))
        if cleaned:
            return cleaned

    # Shape D: "Company (YC S26) — ..."
    match = re.match(r"^([A-Z][\w&.\-']*(?:\s+[A-Z][\w&.\-']*){0,3})\s*\((?:YC|https?://)", head)
    if match:
        cleaned = _clean_company(match.group(1))
        if cleaned:
            return cleaned

    return ""


def _clean_company(value: str) -> str:
    name = PIPE_SPLIT_RE.split(value or "")[0].strip()
    # Drop parentheticals carrying a URL, a YC batch, or a funding stage.
    name = re.sub(
        r"\s*\(\s*(?:YC[^)]*|https?://[^)]*|[^)]*(?:series|backed|seed|round|funding)[^)]*)\s*\)",
        "",
        name,
        flags=re.I,
    )
    name = re.sub(r"^(at|we(?:'| a)?re hiring at|hiring at)\s+", "", name, flags=re.I)
    name = _strip_location_prefix(name)
    name = re.sub(r"\.(com|io|ai|co|net|org|dev|app)$", "", name, flags=re.I)
    name = name.strip(" -–—:,.•*")
    name = re.sub(r"\s{2,}", " ", name)
    if not name or len(name) < 2 or len(name) > 60:
        return ""
    if name.lower() in ("we", "the", "our", "remote", "location", "company"):
        return ""
    if not re.search(r"[A-Za-z]", name):
        return ""
    return name


# Posts often lead with the work arrangement instead of the company name:
# "Remote (US) Close ( https://close.com ) | Senior Backend Engineer".
_LOCATION_PREFIX_RE = re.compile(
    r"^(?:remote|onsite|on-?site|hybrid|anywhere|worldwide|us|eu|uk|emea|global)"
    r"(?:\s*\([^)]*\))?(?:\s*[-–—/,]\s*|\s+)+",
    re.I,
)


def _strip_location_prefix(name: str) -> str:
    previous = None
    current = name.strip()
    # Repeat: "Remote (US) Onsite Acme" should lose both prefixes.
    while current != previous:
        previous = current
        current = _LOCATION_PREFIX_RE.sub("", current, count=1).strip()
    return current or name


def extract_domain(urls: List[str]) -> str:
    for url in urls:
        try:
            host = urlparse(url).netloc.lower()
        except ValueError:
            continue
        if not host:
            continue
        host = host.split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        # Drop IDN/punycode labels: "xn--xp5a.anterior.app" and "電.anterior.app"
        # are not the domain we want to crawl.
        labels = [
            label for label in host.split(".")
            if label and not label.startswith("xn--") and re.fullmatch(r"[a-z0-9-]+", label)
        ]
        if len(labels) < 2:
            continue
        host = ".".join(labels)
        if any(host == d or host.endswith("." + d) for d in SKIP_DOMAINS):
            continue
        if identify(url).get("ats") not in (None, "unknown"):
            continue  # that's the ATS, not the company domain
        return host
    return ""


def extract_roles_text(text: str) -> str:
    """Everything after the company name on the first table row + first lines."""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    head = lines[0] if lines else ""
    segments = PIPE_SPLIT_RE.split(head)[1:]
    extra = " ".join(lines[:6])
    return (" | ".join(segments) + " " + extra)[:1200]


def parse_hn_posting(raw_html: str, thread_id: str, thread_title: str, item_id: str) -> Optional[RawCandidate]:
    """Parse one HN comment into a candidate, or None if it is not a posting."""
    text = strip_html(raw_html)
    if len(text) < 40:
        return None
    if is_job_seeker(text):
        return None

    name = extract_company_name(text)
    if not name:
        return None
    name = expand_acronym(name, text)

    urls = extract_urls(raw_html)
    ats_urls = [u for u in urls if identify(u).get("ats") not in (None, "unknown")]

    return RawCandidate(
        name=name,
        domain=extract_domain(urls),
        source="hn_whoishiring",
        source_url=f"https://news.ycombinator.com/item?id={item_id}",
        source_title=thread_title,
        source_context=text[:400],
        roles_text=extract_roles_text(text),
        ats_urls=ats_urls,
    )
