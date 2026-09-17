"""
Source-of-truth ATS verification engine
=======================================

Given a job URL (an ATS link, or the "Apply on company site" target harvested
from Indeed / LinkedIn), determine whether the *original posting* is still live
on the employer's own applicant tracking system.

The whole point is to bypass the middleman (Indeed / LinkedIn / aggregators)
and ask the primary source: "is this requisition still open?"

Statuses
--------
- ``open``    : the posting exists on the source ATS right now
- ``closed``  : the ATS authoritatively says it is gone (404 / re-listed board
                without the requisition / expired)
- ``unknown`` : we could not reach or could not interpret the source

Design notes
------------
* Pure ``requests`` (sync). Call it from a threadpool in async contexts.
* Every handler returns a :class:`VerifyResult`; no handler may raise.
* ``confidence`` expresses how strongly we trust the verdict, which lets the UI
  render "源头已关闭（高置信）" vs "疑似已关闭".
* No API keys are required: all of the endpoints below are the public boards
  that the ATS vendors use to render their own job pages.
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 JobDetectorBot/1.0"
)

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"
STATUS_UNKNOWN = "unknown"

DEFAULT_TIMEOUT = 12

# Phrases that mean "this requisition is gone" on a generic careers page.
CLOSED_PHRASES = (
    "no longer accepting applications",
    "this position has been filled",
    "position has been filled",
    "this job has been filled",
    "job posting has expired",
    "this posting has expired",
    "this job is no longer available",
    "this position is no longer available",
    "the job you are looking for",
    "job not found",
    "no longer available",
    "position closed",
    "posting is closed",
    "applications are closed",
    "this role has been closed",
)

OPEN_PHRASES = (
    "apply for this job",
    "apply now",
    "submit application",
    "apply for this position",
)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------
@dataclass
class VerifyResult:
    """Outcome of a single source verification."""

    input_url: str = ""
    status: str = STATUS_UNKNOWN
    ats: str = "unknown"
    confidence: float = 0.0
    reason: str = ""
    reason_en: str = ""
    canonical_url: str = ""
    apply_url: str = ""
    matched_title: str = ""
    company: str = ""
    location: str = ""
    posted_at: str = ""
    http_status: Optional[int] = None
    checked_at: str = ""
    elapsed_ms: int = 0
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if not data.get("checked_at"):
            data["checked_at"] = _now_iso()
        if not data.get("reason_en"):
            data["reason_en"] = to_english_reason(data.get("reason", ""))
        return data

    @property
    def is_open(self) -> bool:
        return self.status == STATUS_OPEN

    @property
    def is_closed(self) -> bool:
        return self.status == STATUS_CLOSED


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Reason localisation
# ---------------------------------------------------------------------------
# The engine is used by two front-ends: the Chinese browser extension and the
# English website.  ``reason`` stays Chinese (extension contract, unchanged);
# ``reason_en`` is derived here so the English site never renders Chinese.
# ``tests/test_source_verify.py`` scans this module for every reason literal and
# fails if one of them has no rule — keep the two in sync.
_REASON_EN_RULES: List[Tuple[str, str]] = [
    # -- Greenhouse --------------------------------------------------------
    (r"^无法从 URL 解析 Greenhouse board token$",
     "Could not extract a Greenhouse board token from the URL"),
    (r"^Greenhouse 源头 API 返回该岗位仍在招$",
     "Greenhouse source API confirms this posting is still open"),
    (r"^岗位详情 API 404，但在 board 列表中仍存在（unlisted job post）$",
     "Detail API returned 404, but the job id is still in the board list (unlisted job post)"),
    (r"^Greenhouse 源头已下架该岗位（详情 404 且 board 列表无此 ID）$",
     "Greenhouse has taken this posting down (detail 404 and the job id is gone from the board list)"),
    (r"^岗位详情 404，但无法读取 board 列表二次确认（board token 可能不匹配）$",
     "Detail returned 404 but the board list could not be read to confirm (the board token may be wrong)"),
    (r"^Greenhouse board 未公开或拒绝访问$", "The Greenhouse board is private or refused access"),
    (r"^Greenhouse board 不存在（400/404）$", "The Greenhouse board does not exist (400/404)"),

    # -- Lever -------------------------------------------------------------
    (r"^无法从 URL 解析 Lever board token$",
     "Could not extract a Lever board token from the URL"),
    (r"^Lever 源头 API 返回该岗位仍在招$",
     "Lever source API confirms this posting is still open"),
    (r"^详情接口 404，但 board 列表中仍存在该岗位$",
     "Detail endpoint returned 404, but the posting is still in the board list"),
    (r"^Lever 源头已下架该岗位（详情 404 且 board 无此 ID）$",
     "Lever has taken this posting down (detail 404 and the id is gone from the board list)"),
    (r"^岗位详情 404，但无法读取 Lever board 列表二次确认$",
     "Detail returned 404 but the Lever board list could not be read to confirm"),
    (r"^Lever board 未公开或拒绝访问$", "The Lever board is private or refused access"),
    (r"^Lever board 不存在$", "The Lever board does not exist"),

    # -- Ashby -------------------------------------------------------------
    (r"^无法从 URL 解析 Ashby organization slug$",
     "Could not extract an Ashby organization slug from the URL"),
    (r"^Ashby organization 不存在$", "The Ashby organization does not exist"),
    (r"^Ashby 源头 board 中仍存在该岗位$",
     "The posting is still present on the Ashby source board"),
    (r"^岗位在 Ashby 中仍存在但已取消公开列出（isListed=false）$",
     "Still present in Ashby but no longer publicly listed (isListed=false)"),
    (r"^Ashby 源头 board 已无此岗位（当前在招 (\d+) 个）$",
     r"Ashby no longer lists this posting (\1 roles currently open)"),

    # -- Workable ----------------------------------------------------------
    (r"^无法解析 Workable account token$", "Could not resolve the Workable account token"),
    (r"^Workable 已将岗位短链重定向到失效页 \(/oops\)$",
     "Workable redirects this short link to its expired-posting page (/oops)"),
    (r"^Workable account 不存在$", "The Workable account does not exist"),
    (r"^Workable 源头仍在招该岗位$", "Workable still lists this posting as open"),
    (r"^Workable 源头已无此岗位（当前在招 (\d+) 个）$",
     r"Workable no longer lists this posting (\1 roles currently open)"),

    # -- SmartRecruiters ---------------------------------------------------
    (r"^缺少 SmartRecruiters company 或 posting id$",
     "Missing the SmartRecruiters company or posting id"),
    (r"^SmartRecruiters 源头 API 返回该岗位仍在招$",
     "SmartRecruiters source API confirms this posting is still open"),
    (r"^SmartRecruiters 源头已下架该岗位 \(404\)$",
     "SmartRecruiters has taken this posting down (404)"),
    (r"^SmartRecruiters 拒绝访问 \(HTTP (\d+)\)$",
     r"SmartRecruiters denied access (HTTP \1)"),
    (r"^SmartRecruiters 请求异常 \(HTTP (\d+)\)$",
     r"SmartRecruiters request failed (HTTP \1)"),

    # -- Workday -----------------------------------------------------------
    (r"^Workday URL 缺少 site 或 job 路径，无法精确定位$",
     "The Workday URL has no site or job path, so the posting cannot be located"),
    (r"^Workday 源头 API 返回该岗位仍在招$",
     "Workday source API confirms this posting is still open"),
    (r"^Workday 岗位截止日期已过 \((.+)\)$",
     r"The Workday closing date has passed (\1)"),
    (r"^Workday 源头已下架该岗位 \(404\)$",
     "Workday has taken this posting down (404)"),

    # -- Breezy / Recruitee / Personio / Teamtailor ------------------------
    (r"^无法解析 Breezy 子域名$", "Could not resolve the Breezy subdomain"),
    (r"^无法解析 BambooHR 子域名$", "Could not resolve the BambooHR subdomain"),
    (r"^BambooHR board 不存在$", "The BambooHR board does not exist"),
    (r"^BambooHR 源头仍在招该岗位$", "BambooHR still lists this posting as open"),
    (r"^BambooHR 源头已无此岗位（当前在招 (\d+) 个）$",
     r"BambooHR no longer lists this posting (\1 roles currently open)"),
    (r"^仅校验到 BambooHR board 存在（(\d+) 个在招岗位）$",
     r"BambooHR board exists (\1 open roles)"),
    (r"^无法解析 Recruitee 子域名$", "Could not resolve the Recruitee subdomain"),
    (r"^无法解析 Personio 子域名$", "Could not resolve the Personio subdomain"),
    (r"^无法解析 Teamtailor 子域名$", "Could not resolve the Teamtailor subdomain"),
    (r"^Breezy 源头仍在招该岗位$", "Breezy still lists this posting as open"),
    (r"^Recruitee 源头仍在招该岗位$", "Recruitee still lists this posting as open"),
    (r"^Personio 源头 XML feed 中仍存在该岗位$",
     "The posting is still present in the Personio XML feed"),
    (r"^Teamtailor 源头仍存在该岗位$", "The posting still exists on Teamtailor"),
    (r"^Breezy 源头已无此岗位（当前在招 (\d+) 个）$",
     r"Breezy no longer lists this posting (\1 roles currently open)"),
    (r"^Recruitee 源头已无此岗位（当前在招 (\d+) 个）$",
     r"Recruitee no longer lists this posting (\1 roles currently open)"),
    (r"^Personio 源头 feed 已无此岗位（当前 (\d+) 个）$",
     r"The Personio feed no longer lists this posting (\1 roles in total)"),
    (r"^Teamtailor 源头已无此岗位（当前 (\d+) 个）$",
     r"Teamtailor no longer lists this posting (\1 roles in total)"),
    (r"^Breezy board 不存在$", "The Breezy board does not exist"),
    (r"^Recruitee board 不存在$", "The Recruitee board does not exist"),
    (r"^Breezy 请求异常 \(HTTP (\d+)\)$", r"Breezy request failed (HTTP \1)"),
    (r"^Recruitee 请求异常 \(HTTP (\d+)\)$", r"Recruitee request failed (HTTP \1)"),
    (r"^Personio feed 请求异常 \(HTTP (\d+)\)$", r"Personio feed request failed (HTTP \1)"),

    # -- Board-only checks -------------------------------------------------
    (r"^仅校验到 board 存在（(\d+) 个在招岗位），缺少 job id 无法判定单岗$",
     r"Board exists (\1 open roles), but without a job id this posting cannot be judged"),
    (r"^仅校验到 board 存在（(\d+) 个在招岗位），缺少 job id$",
     r"Board exists (\1 open roles), but no job id was provided"),
    (r"^仅校验到 Ashby board 存在（(\d+) 个在招岗位），缺少 job id$",
     r"Ashby board exists (\1 open roles), but no job id was provided"),
    (r"^仅校验到 Breezy board 存在（(\d+) 个在招岗位）$",
     r"Breezy board exists (\1 open roles)"),
    (r"^仅校验到 Recruitee board 存在（(\d+) 个在招岗位）$",
     r"Recruitee board exists (\1 open roles)"),
    (r"^仅校验到 Workable account 存在（(\d+) 个在招岗位）$",
     r"Workable account exists (\1 open roles)"),
    (r"^仅校验到 Personio board 存在（(\d+) 个岗位）$",
     r"Personio board exists (\1 roles)"),
    (r"^仅校验到 Teamtailor site 存在（(\d+) 个岗位）$",
     r"Teamtailor site exists (\1 roles)"),

    # -- Generic careers page ---------------------------------------------
    (r"^页面存在有效的 JobPosting 结构化数据（Google 索引用）$",
     "The page carries valid JobPosting structured data (used for Google indexing)"),
    (r"^原岗位 URL 被重定向到列表/首页，岗位详情页已不存在$",
     "The original URL redirects to a listing/home page — the detail page is gone"),
    (r"^页面仍包含申请入口文案，但无结构化数据佐证$",
     "The page still shows an apply entry point, but nothing structured backs it up"),
    (r"^页面可访问但未找到明确的在招/失效信号（可能是 JS 渲染页面）$",
     "The page loads but shows no clear open/closed signal (it may be JavaScript-rendered)"),
    (r"^无法访问该页面（网络错误/超时）$",
     "The page could not be reached (network error or timeout)"),
    (r"^源页面返回 HTTP (\d+)，岗位页面已不存在$",
     r"The source page returned HTTP \1 — the posting page no longer exists"),
    (r"^源页面拒绝访问 \(HTTP (\d+)\)，需登录或反爬$",
     r"The source page denied access (HTTP \1) — login or bot protection"),
    (r"^源站异常 \(HTTP (\d+)\)$", r"The source site errored (HTTP \1)"),
    (r"^源页面返回空内容 \(HTTP (\d+)\)$", r"The source page returned an empty body (HTTP \1)"),
    (r"^页面出现失效提示文案: “(.+)”$",
     r"The page shows an expired-posting notice: \"\1\""),
    (r"^结构化数据 validThrough 已过期 \((.+)\)$",
     r"Structured data marks validThrough as passed (\1)"),
    (r"^岗位申请截止日期已过 \((.+)\)$",
     r"The application deadline has passed (\1)"),

    # -- Generic ATS request failures (keep last: broadest patterns) -------
    (r"^(\w[\w ]*?) 详情请求异常 \(HTTP (\d+)\)$", r"\1 detail request failed (HTTP \2)"),
    (r"^(\w[\w ]*?) board 请求异常 \(HTTP (\d+)\)$", r"\1 board request failed (HTTP \2)"),
    (r"^(\w[\w ]*?) API 请求异常 \(HTTP (\d+)\)$", r"\1 API request failed (HTTP \2)"),
    (r"^(\w[\w ]*?) 请求异常 \(HTTP (\d+)\)$", r"\1 request failed (HTTP \2)"),

    # -- Internal error ----------------------------------------------------
    (r"^校验过程异常: (.+)$", r"Verification raised an error: \1"),
]


def to_english_reason(reason: str) -> str:
    """
    Translate an engine reason string into English.

    Falls back to the input unchanged when no rule matches — the unit test
    ``test_every_reason_has_an_english_rule`` scans the module source and fails
    in that case, so a missing rule is caught in CI rather than in production.
    """
    if not reason:
        return ""
    for pattern, replacement in _REASON_EN_RULES:
        if re.match(pattern, reason):
            return re.sub(pattern, replacement, reason)
    return reason


# ---------------------------------------------------------------------------
# Source identification
# ---------------------------------------------------------------------------
GREENHOUSE_RE = re.compile(
    r"(?:boards|job-boards|boards-api)\.greenhouse\.io", re.I
)
LEVER_RE = re.compile(r"(?:jobs|api|hire)\.lever\.co", re.I)
ASHBY_RE = re.compile(r"(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com)", re.I)
WORKABLE_RE = re.compile(r"(?:apply|jobs)\.workable\.com", re.I)
SMARTRECRUITERS_RE = re.compile(r"(?:jobs|careers)\.smartrecruiters\.com", re.I)
WORKDAY_RE = re.compile(r"\.(?:wd\d+)\.myworkdayjobs\.com", re.I)
BREEZY_RE = re.compile(r"\.breezy\.hr", re.I)
RECRUITEE_RE = re.compile(r"\.recruitee\.com", re.I)
PERSONIO_RE = re.compile(r"\.jobs\.personio\.(?:de|com)", re.I)
TEAMTAILOR_RE = re.compile(r"\.teamtailor\.com", re.I)
BAMBOOHR_RE = re.compile(r"\.bamboohr\.com", re.I)


REDIRECT_PARAMS = ("url", "u", "target", "redirect", "redirect_url", "dest", "destination", "to")
_ANY_ATS_RE = re.compile(
    "|".join([
        r"(?:boards|job-boards|boards-api)\.greenhouse\.io",
        r"(?:jobs|api|hire)\.lever\.co",
        r"(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com)",
        r"(?:apply|jobs)\.workable\.com",
        r"(?:jobs|careers|api)\.smartrecruiters\.com",
        r"\.wd\d+\.myworkdayjobs\.com",
        r"\.breezy\.hr",
        r"\.recruitee\.com",
        r"\.jobs\.personio\.(?:de|com)",
        r"\.teamtailor\.com",
        r"\.bamboohr\.com",
    ]),
    re.I,
)


def unwrap_redirect(url: str, depth: int = 2) -> str:
    """
    Unwrap aggregator redirect wrappers.

    LinkedIn uses ``/redir/redirect?url=https%3A%2F%2Fjobs.lever.co%2F...``.
    Returns the inner URL when it points at a known ATS, else the input.
    """
    current = url
    for _ in range(max(0, depth)):
        if not current:
            return current
        try:
            # Test the host only: a wrapper URL may contain the target host in a
            # percent-encoded query value.
            if _ANY_ATS_RE.search(urlparse(current).netloc or ""):
                return current
            query = parse_qs(urlparse(current).query)
        except Exception:  # noqa: BLE001
            return current
        found = None
        for key in REDIRECT_PARAMS:
            value = (query.get(key) or [None])[0]
            if not value:
                continue
            candidate = value
            if not candidate.startswith(("http://", "https://")):
                try:
                    from urllib.parse import unquote

                    candidate = unquote(candidate)
                except Exception:  # noqa: BLE001
                    pass
            if candidate.startswith(("http://", "https://")):
                found = candidate
                break
        if not found:
            return current
        current = found
    return current


def identify(url: str) -> Dict[str, Any]:
    """
    Classify a URL and pull out the identifiers needed to query the ATS.

    Returns a dict with at least ``{"ats": str, "url": str}``. Values may be
    ``None`` when the URL does not carry enough information.
    """
    ref: Dict[str, Any] = {
        "ats": "unknown",
        "url": url,
        "token": None,
        "job_id": None,
        "host": "",
        "path": "",
    }
    if not url:
        return ref

    normalized = url.strip()
    if not normalized.startswith(("http://", "https://")):
        normalized = "https://" + normalized.lstrip("/")
    normalized = unwrap_redirect(normalized)
    ref["url"] = normalized

    parsed = urlparse(normalized)
    ref["host"] = parsed.netloc.lower()
    ref["path"] = parsed.path
    query = parse_qs(parsed.query)

    # --- Greenhouse -------------------------------------------------------
    # Many companies expose their Greenhouse board behind their own domain,
    # e.g. https://stripe.com/jobs/search?gh_jid=8172487 . The board token is
    # then unknown, so the caller may inject one via ``token_hint``.
    if "gh_jid" in query and not GREENHOUSE_RE.search(ref["host"]):
        ref["ats"] = "greenhouse"
        ref["job_id"] = (query.get("gh_jid") or [None])[0]
        ref["token"] = (query.get("for") or [None])[0]
        return ref

    if GREENHOUSE_RE.search(ref["host"]):
        ref["ats"] = "greenhouse"
        # embed form: /embed/job_app?for=TOKEN&token=JOBID
        if "for" in query:
            ref["token"] = (query.get("for") or [None])[0]
            ref["job_id"] = (query.get("token") or query.get("job_id") or [None])[0]
            return ref
        parts = [p for p in parsed.path.split("/") if p]
        if parts and parts[0] in ("v1",) and len(parts) >= 3 and parts[1] == "boards":
            parts = parts[2:]
        if parts:
            ref["token"] = parts[0]
        if "jobs" in parts:
            idx = parts.index("jobs")
            if len(parts) > idx + 1 and parts[idx + 1].isdigit():
                ref["job_id"] = parts[idx + 1]
        return ref

    # --- Lever ------------------------------------------------------------
    if LEVER_RE.search(ref["host"]):
        ref["ats"] = "lever"
        parts = [p for p in parsed.path.split("/") if p]
        if parts and parts[0] == "v0" and len(parts) > 1 and parts[1] == "postings":
            parts = parts[2:]
        if parts:
            ref["token"] = parts[0]
        if len(parts) > 1:
            ref["job_id"] = parts[1]
        return ref

    # --- Ashby ------------------------------------------------------------
    if ASHBY_RE.search(ref["host"]):
        ref["ats"] = "ashby"
        parts = [p for p in parsed.path.split("/") if p]
        if parts and parts[0] == "posting-api":
            ref["token"] = parts[-1]
        else:
            if parts:
                ref["token"] = parts[0]
            if len(parts) > 1:
                ref["job_id"] = parts[1]
        return ref

    # --- Workable ---------------------------------------------------------
    if WORKABLE_RE.search(ref["host"]):
        ref["ats"] = "workable"
        parts = [p for p in parsed.path.split("/") if p]
        if ref["host"].startswith("jobs."):
            # jobs.workable.com/view/{id}/{slug} — no board token available
            if len(parts) > 1 and parts[0] == "view":
                ref["job_id"] = parts[1]
            return ref
        if parts and parts[0] == "j":
            # apply.workable.com/j/{SHORTCODE}
            ref["job_id"] = parts[1] if len(parts) > 1 else None
            return ref
        if parts:
            ref["token"] = parts[0]
        if len(parts) > 2 and parts[1] == "j":
            ref["job_id"] = parts[2]
        elif len(parts) > 1:
            ref["job_id"] = parts[1]
        return ref

    # --- SmartRecruiters --------------------------------------------------
    if SMARTRECRUITERS_RE.search(ref["host"]):
        ref["ats"] = "smartrecruiters"
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            ref["token"] = parts[0]
        if len(parts) > 1:
            ref["job_id"] = parts[1].split("-")[0]
        # api.smartrecruiters.com/v1/companies/{token}/postings/{id}
        if "companies" in parts:
            idx = parts.index("companies")
            if len(parts) > idx + 1:
                ref["token"] = parts[idx + 1]
            if len(parts) > idx + 3:
                ref["job_id"] = parts[idx + 3]
        return ref

    # --- Workday ----------------------------------------------------------
    if WORKDAY_RE.search(ref["host"]):
        ref["ats"] = "workday"
        ref["token"] = ref["host"].split(".")[0]
        parts = [p for p in parsed.path.split("/") if p]
        if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
            parts = parts[1:]
        if parts:
            ref["site"] = parts[0]
        if "job" in parts:
            idx = parts.index("job")
            ref["job_id"] = "/".join(parts[idx:])
        return ref

    # --- Breezy -----------------------------------------------------------
    if BREEZY_RE.search(ref["host"]):
        ref["ats"] = "breezy"
        ref["token"] = ref["host"].split(".")[0]
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) > 1 and parts[0] in ("p", "positions"):
            ref["job_id"] = parts[1]
        return ref

    # --- Recruitee --------------------------------------------------------
    if RECRUITEE_RE.search(ref["host"]):
        ref["ats"] = "recruitee"
        ref["token"] = ref["host"].split(".")[0]
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) > 1 and parts[0] == "o":
            ref["job_id"] = parts[1]
        return ref

    # --- Personio ---------------------------------------------------------
    if PERSONIO_RE.search(ref["host"]):
        ref["ats"] = "personio"
        ref["token"] = ref["host"].split(".")[0]
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) > 1 and parts[0] == "job":
            ref["job_id"] = parts[1]
        return ref

    # --- BambooHR ---------------------------------------------------------
    if BAMBOOHR_RE.search(ref["host"]):
        ref["ats"] = "bamboohr"
        ref["token"] = ref["host"].split(".")[0]
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) > 1 and parts[0] in ("careers", "jobs"):
            ref["job_id"] = parts[1]
        elif "id" in query:
            ref["job_id"] = (query.get("id") or [None])[0]
        return ref

    # --- Teamtailor -------------------------------------------------------
    if TEAMTAILOR_RE.search(ref["host"]):
        ref["ats"] = "teamtailor"
        ref["token"] = ref["host"].split(".")[0]
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) > 1 and parts[0] == "jobs":
            ref["job_id"] = parts[1]
        return ref

    return ref


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
class _Http:
    """Tiny resilient HTTP client (retries once without SSL verification)."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("allow_redirects", True)
        try:
            return self.session.request(method, url, **kwargs)
        except requests.exceptions.SSLError:
            try:
                return self.session.request(method, url, verify=False, **kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.debug("SSL retry failed for %s: %s", url, exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Request failed for %s: %s", url, exc)
        return None

    def get_json(self, url: str, **kwargs) -> Tuple[Optional[Any], Optional[int]]:
        resp = self.request("GET", url, **kwargs)
        if resp is None:
            return None, None
        if resp.status_code >= 400:
            return None, resp.status_code
        try:
            return resp.json(), resp.status_code
        except ValueError:
            return None, resp.status_code

    def get_text(self, url: str, **kwargs) -> Tuple[Optional[str], Optional[int], str]:
        resp = self.request("GET", url, **kwargs)
        if resp is None:
            return None, None, url
        return resp.text, resp.status_code, str(resp.url)


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------
class SourceVerifier:
    """Verify job postings against their primary ATS."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.http = _Http(timeout=timeout)

    # -- public API --------------------------------------------------------
    def verify(
        self,
        url: str,
        hint_title: str = "",
        hint_company: str = "",
        token_hint: Optional[str] = None,
    ) -> VerifyResult:
        """Verify a single URL. Never raises.

        ``token_hint`` lets the caller supply a board token that the URL itself
        does not carry (e.g. a company careers page using ``?gh_jid=``). Pass
        either a bare token string or ``{"ats": ..., "token": ...}``; the dict
        form is only applied when the ATS matches (or is still unknown).
        """
        started = time.time()
        result = VerifyResult(input_url=url, checked_at=_now_iso())
        try:
            ref = identify(url)
            _apply_token_hint(ref, token_hint)
            result.ats = ref.get("ats", "unknown")
            handler = getattr(self, f"_check_{result.ats}", None)
            if handler is None:
                self._check_generic(ref, result, hint_title=hint_title)
            else:
                handler(ref, result, hint_title=hint_title, hint_company=hint_company)
        except Exception as exc:  # noqa: BLE001
            logger.warning("verify(%s) crashed: %s", url, exc)
            result.status = STATUS_UNKNOWN
            result.confidence = 0.0
            result.reason = f"校验过程异常: {exc}"
        if not result.apply_url:
            result.apply_url = result.canonical_url or result.input_url
        result.elapsed_ms = int((time.time() - started) * 1000)
        return result

    def verify_many(
        self,
        urls: Iterable[str],
        hint_title: str = "",
        hint_company: str = "",
        token_hint: Optional[str] = None,
    ) -> List[VerifyResult]:
        return [
            self.verify(u, hint_title=hint_title, hint_company=hint_company, token_hint=token_hint)
            for u in urls
            if u
        ]

    def best(self, results: Iterable[VerifyResult]) -> Optional[VerifyResult]:
        """Pick the most informative result (open > closed > unknown, by confidence)."""
        ranked = sorted(
            results,
            key=lambda r: (
                {STATUS_OPEN: 2, STATUS_CLOSED: 1}.get(r.status, 0),
                r.confidence,
            ),
            reverse=True,
        )
        return ranked[0] if ranked else None

    # -- Greenhouse --------------------------------------------------------
    def _check_greenhouse(self, ref: Dict[str, Any], out: VerifyResult, **_: Any) -> None:
        token, job_id = ref.get("token"), ref.get("job_id")
        if not token:
            out.reason = "无法从 URL 解析 Greenhouse board token"
            return
        base = f"https://boards-api.greenhouse.io/v1/boards/{token}"
        out.canonical_url = (
            f"https://job-boards.greenhouse.io/{token}/jobs/{job_id}" if job_id else f"https://job-boards.greenhouse.io/{token}"
        )

        if job_id:
            data, code = self.http.get_json(f"{base}/jobs/{job_id}")
            out.http_status = code
            if code == 200 and isinstance(data, dict):
                out.status = STATUS_OPEN
                out.confidence = 0.98
                out.reason = "Greenhouse 源头 API 返回该岗位仍在招"
                out.matched_title = data.get("title", "")
                loc = data.get("location") or {}
                out.location = loc.get("name", "") if isinstance(loc, dict) else str(loc)
                out.posted_at = data.get("updated_at") or data.get("first_published") or ""
                out.apply_url = data.get("absolute_url") or out.canonical_url
                self._flag_deadline(data, out)
                return
            if code in (404, 410):
                # A 404 can also mean "job post" (unlisted) — confirm with the board list
                listed = self._greenhouse_listed(base, job_id)
                if listed is True:
                    out.status = STATUS_OPEN
                    out.confidence = 0.75
                    out.reason = "岗位详情 API 404，但在 board 列表中仍存在（unlisted job post）"
                elif listed is False:
                    out.status = STATUS_CLOSED
                    out.confidence = 0.97
                    out.reason = "Greenhouse 源头已下架该岗位（详情 404 且 board 列表无此 ID）"
                else:
                    # Board list unreachable → the token itself may be wrong.
                    # Never claim "closed" without a second confirmation.
                    out.status = STATUS_UNKNOWN
                    out.confidence = 0.3
                    out.reason = "岗位详情 404，但无法读取 board 列表二次确认（board token 可能不匹配）"
                return
            if code in (401, 403):
                out.reason = "Greenhouse board 未公开或拒绝访问"
                return
            out.reason = f"Greenhouse 详情请求异常 (HTTP {code})"
            return

        # Board-only URL: report board health
        data, code = self.http.get_json(f"{base}/jobs")
        out.http_status = code
        if code == 200 and isinstance(data, dict):
            out.status = STATUS_OPEN
            out.confidence = 0.4
            out.reason = f"仅校验到 board 存在（{len(data.get('jobs', []))} 个在招岗位），缺少 job id 无法判定单岗"
        elif code in (404, 410):
            out.status = STATUS_CLOSED
            out.confidence = 0.8
            out.reason = "Greenhouse board 不存在（400/404）"
        else:
            out.reason = f"Greenhouse board 请求异常 (HTTP {code})"

    def _greenhouse_listed(self, base: str, job_id: str) -> Optional[bool]:
        data, code = self.http.get_json(f"{base}/jobs")
        if code != 200 or not isinstance(data, dict):
            return None
        ids = {str(j.get("id")) for j in data.get("jobs", []) if isinstance(j, dict)}
        return str(job_id) in ids

    @staticmethod
    def _flag_deadline(data: Dict[str, Any], out: VerifyResult) -> None:
        """Greenhouse sometimes exposes an application deadline."""
        deadline = data.get("application_deadline")
        if not deadline:
            return
        try:
            dt = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < datetime.now(timezone.utc):
                out.status = STATUS_CLOSED
                out.confidence = 0.9
                out.reason = f"岗位申请截止日期已过 ({deadline})"
        except Exception:  # noqa: BLE001
            pass

    # -- Lever -------------------------------------------------------------
    def _check_lever(self, ref: Dict[str, Any], out: VerifyResult, **_: Any) -> None:
        token, job_id = ref.get("token"), ref.get("job_id")
        if not token:
            out.reason = "无法从 URL 解析 Lever board token"
            return
        out.canonical_url = (
            f"https://jobs.lever.co/{token}/{job_id}" if job_id else f"https://jobs.lever.co/{token}"
        )
        if job_id:
            data, code = self.http.get_json(
                f"https://api.lever.co/v0/postings/{token}/{job_id}"
            )
            out.http_status = code
            if code == 200 and isinstance(data, dict):
                out.status = STATUS_OPEN
                out.confidence = 0.97
                out.reason = "Lever 源头 API 返回该岗位仍在招"
                out.matched_title = data.get("text", "")
                categories = data.get("categories") or {}
                out.location = categories.get("location", "") if isinstance(categories, dict) else ""
                created = data.get("createdAt")
                if created:
                    try:
                        out.posted_at = datetime.fromtimestamp(
                            created / 1000.0, tz=timezone.utc
                        ).isoformat()
                    except Exception:  # noqa: BLE001
                        pass
                out.apply_url = data.get("applyUrl") or data.get("hostedUrl") or out.canonical_url
                return
            if code in (404, 410):
                data, code2 = self.http.get_json(
                    f"https://api.lever.co/v0/postings/{token}?mode=json"
                )
                if code2 == 200 and isinstance(data, list):
                    ids = {str(j.get("id")) for j in data if isinstance(j, dict)}
                    if str(job_id) in ids:
                        out.status = STATUS_OPEN
                        out.confidence = 0.7
                        out.reason = "详情接口 404，但 board 列表中仍存在该岗位"
                    else:
                        out.status = STATUS_CLOSED
                        out.confidence = 0.97
                        out.reason = "Lever 源头已下架该岗位（详情 404 且 board 无此 ID）"
                else:
                    out.status = STATUS_UNKNOWN
                    out.confidence = 0.3
                    out.reason = "岗位详情 404，但无法读取 Lever board 列表二次确认"
                return
            if code in (401, 403):
                out.reason = "Lever board 未公开或拒绝访问"
                return
            out.reason = f"Lever 详情请求异常 (HTTP {code})"
            return

        data, code = self.http.get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
        out.http_status = code
        if code == 200 and isinstance(data, list):
            out.status = STATUS_OPEN
            out.confidence = 0.4
            out.reason = f"仅校验到 board 存在（{len(data)} 个在招岗位），缺少 job id"
        elif code in (404, 410):
            out.status = STATUS_CLOSED
            out.confidence = 0.75
            out.reason = "Lever board 不存在"
        else:
            out.reason = f"Lever board 请求异常 (HTTP {code})"

    # -- Ashby -------------------------------------------------------------
    def _check_ashby(self, ref: Dict[str, Any], out: VerifyResult, **_: Any) -> None:
        token, job_id = ref.get("token"), ref.get("job_id")
        if not token:
            out.reason = "无法从 URL 解析 Ashby organization slug"
            return
        out.canonical_url = (
            f"https://jobs.ashbyhq.com/{token}/{job_id}" if job_id else f"https://jobs.ashbyhq.com/{token}"
        )
        data, code = self.http.get_json(
            f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
        )
        out.http_status = code
        if code != 200 or not isinstance(data, dict):
            if code in (404, 410):
                out.status = STATUS_CLOSED
                out.confidence = 0.7
                out.reason = "Ashby organization 不存在"
            else:
                out.reason = f"Ashby board API 请求异常 (HTTP {code})"
            return

        jobs = data.get("jobs") or []
        if not job_id:
            out.status = STATUS_OPEN
            out.confidence = 0.4
            out.reason = f"仅校验到 Ashby board 存在（{len(jobs)} 个在招岗位），缺少 job id"
            return

        match = next(
            (j for j in jobs if isinstance(j, dict) and str(j.get("id")) == str(job_id)), None
        )
        if match:
            out.status = STATUS_OPEN
            out.confidence = 0.97
            out.reason = "Ashby 源头 board 中仍存在该岗位"
            out.matched_title = match.get("title", "")
            out.location = match.get("location", "") or ""
            out.posted_at = match.get("publishedAt") or match.get("updatedAt") or ""
            out.apply_url = match.get("jobUrl") or match.get("applyUrl") or out.canonical_url
            if match.get("isListed") is False:
                out.confidence = 0.6
                out.reason = "岗位在 Ashby 中仍存在但已取消公开列出（isListed=false）"
            return

        out.status = STATUS_CLOSED
        out.confidence = 0.95
        out.reason = f"Ashby 源头 board 已无此岗位（当前在招 {len(jobs)} 个）"

    # -- Workable ----------------------------------------------------------
    def _check_workable(self, ref: Dict[str, Any], out: VerifyResult, **_: Any) -> None:
        token, job_id = ref.get("token"), ref.get("job_id")
        if not token and job_id:
            token = self._resolve_workable_token(job_id)
            if token:
                ref["token"] = token
        if not token:
            # Last resort: the /j/{shortcode} page 302s to /oops when dead
            if job_id:
                resp = self.http.request(
                    "GET", f"https://apply.workable.com/j/{job_id}", allow_redirects=False
                )
                if resp is not None:
                    out.http_status = resp.status_code
                    location = resp.headers.get("Location", "")
                    if resp.status_code in (301, 302, 307, 308) and "/oops" in location:
                        out.status = STATUS_CLOSED
                        out.confidence = 0.9
                        out.reason = "Workable 已将岗位短链重定向到失效页 (/oops)"
                        return
            out.reason = "无法解析 Workable account token"
            return

        out.canonical_url = (
            f"https://apply.workable.com/{token}/j/{job_id}/" if job_id else f"https://apply.workable.com/{token}/"
        )
        data, code = self.http.get_json(
            f"https://apply.workable.com/api/v1/widget/accounts/{token}?details=true"
        )
        out.http_status = code
        if code != 200 or not isinstance(data, dict):
            if code in (404, 410):
                out.status = STATUS_CLOSED
                out.confidence = 0.7
                out.reason = "Workable account 不存在"
            else:
                out.reason = f"Workable API 请求异常 (HTTP {code})"
            return

        jobs = data.get("jobs") or []
        if not job_id:
            out.status = STATUS_OPEN
            out.confidence = 0.4
            out.reason = f"仅校验到 Workable account 存在（{len(jobs)} 个在招岗位）"
            return
        match = next(
            (j for j in jobs if isinstance(j, dict) and str(j.get("shortcode")) == str(job_id)), None
        )
        if match:
            out.status = STATUS_OPEN
            out.confidence = 0.95
            out.reason = "Workable 源头仍在招该岗位"
            out.matched_title = match.get("title", "")
            loc = match.get("city") or match.get("location") or ""
            out.location = loc if isinstance(loc, str) else str(loc)
            out.posted_at = match.get("published_on") or match.get("created_at") or ""
            out.apply_url = match.get("url") or out.canonical_url
            return
        out.status = STATUS_CLOSED
        out.confidence = 0.93
        out.reason = f"Workable 源头已无此岗位（当前在招 {len(jobs)} 个）"

    def _resolve_workable_token(self, shortcode: str) -> Optional[str]:
        resp = self.http.request(
            "GET", f"https://apply.workable.com/j/{shortcode}", allow_redirects=False
        )
        if resp is None:
            return None
        location = resp.headers.get("Location", "")
        match = re.search(r"apply\.workable\.com/([^/]+)/j/", location)
        return match.group(1) if match else None

    # -- SmartRecruiters ---------------------------------------------------
    def _check_smartrecruiters(self, ref: Dict[str, Any], out: VerifyResult, **_: Any) -> None:
        token, job_id = ref.get("token"), ref.get("job_id")
        if not token or not job_id:
            out.reason = "缺少 SmartRecruiters company 或 posting id"
            return
        out.canonical_url = f"https://jobs.smartrecruiters.com/{token}/{job_id}"
        data, code = self.http.get_json(
            f"https://api.smartrecruiters.com/v1/companies/{token}/postings/{job_id}"
        )
        out.http_status = code
        if code == 200 and isinstance(data, dict):
            out.status = STATUS_OPEN
            out.confidence = 0.95
            out.reason = "SmartRecruiters 源头 API 返回该岗位仍在招"
            out.matched_title = data.get("name", "")
            loc = data.get("location") or {}
            if isinstance(loc, dict):
                out.location = ", ".join(
                    str(v) for v in (loc.get("city"), loc.get("region"), loc.get("country")) if v
                )
            out.posted_at = data.get("releasedDate") or ""
            out.apply_url = f"https://jobs.smartrecruiters.com/{token}/{job_id}"
            return
        if code in (404, 410):
            out.status = STATUS_CLOSED
            out.confidence = 0.93
            out.reason = "SmartRecruiters 源头已下架该岗位 (404)"
            return
        if code in (400, 401, 403):
            out.reason = f"SmartRecruiters 拒绝访问 (HTTP {code})"
            return
        out.reason = f"SmartRecruiters 请求异常 (HTTP {code})"

    # -- Workday -----------------------------------------------------------
    def _check_workday(self, ref: Dict[str, Any], out: VerifyResult, **_: Any) -> None:
        tenant = ref.get("token")
        site = ref.get("site")
        job_path = ref.get("job_id")
        host = ref.get("host")
        if not job_path or not site:
            out.status = STATUS_UNKNOWN
            out.confidence = 0.2
            out.reason = "Workday URL 缺少 site 或 job 路径，无法精确定位"
            return
        job_path = "/" + str(job_path).lstrip("/")
        base = f"https://{host}"
        out.canonical_url = f"{base}/{site}{job_path}"
        url = f"{base}/wday/cxs/{tenant}/{site}{job_path}"
        data, code = self.http.get_json(url)
        out.http_status = code
        if code == 200 and isinstance(data, dict):
            info = data.get("jobPostingInfo") or {}
            out.status = STATUS_OPEN
            out.confidence = 0.95
            out.reason = "Workday 源头 API 返回该岗位仍在招"
            out.matched_title = info.get("title", "")
            out.location = info.get("location", "") or info.get("additionalLocations", "")
            out.posted_at = info.get("startDate") or info.get("postedOn") or ""
            out.apply_url = info.get("externalUrl") or out.canonical_url
            deadline = info.get("endDate")
            if deadline:
                try:
                    dt = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < datetime.now(timezone.utc):
                        out.status = STATUS_CLOSED
                        out.confidence = 0.85
                        out.reason = f"Workday 岗位截止日期已过 ({deadline})"
                except Exception:  # noqa: BLE001
                    pass
            return
        if code in (404, 410):
            out.status = STATUS_CLOSED
            out.confidence = 0.9
            out.reason = "Workday 源头已下架该岗位 (404)"
            return
        out.reason = f"Workday 详情请求异常 (HTTP {code})"

    # -- Breezy ------------------------------------------------------------
    def _check_breezy(self, ref: Dict[str, Any], out: VerifyResult, **_: Any) -> None:
        token, job_id = ref.get("token"), ref.get("job_id")
        if not token:
            out.reason = "无法解析 Breezy 子域名"
            return
        board = f"https://{token}.breezy.hr"
        out.canonical_url = f"{board}/p/{job_id}" if job_id else board
        data, code = self.http.get_json(f"{board}/json")
        out.http_status = code
        if code == 200 and isinstance(data, list):
            if not job_id:
                out.status = STATUS_OPEN
                out.confidence = 0.4
                out.reason = f"仅校验到 Breezy board 存在（{len(data)} 个在招岗位）"
                return
            ids = set()
            for j in data:
                if not isinstance(j, dict):
                    continue
                ids.add(str(j.get("id") or j.get("_id") or ""))
                furl = str(j.get("url") or j.get("absolute_url") or "")
                ids.add(furl.rstrip("/").split("/")[-1])
            if str(job_id) in ids:
                out.status = STATUS_OPEN
                out.confidence = 0.9
                out.reason = "Breezy 源头仍在招该岗位"
                match = next(
                    (j for j in data if str(j.get("id")) == str(job_id) or str(j.get("_id")) == str(job_id)),
                    {},
                )
                out.matched_title = match.get("name", "")
                out.location = (match.get("location") or {}).get("name", "") if isinstance(match.get("location"), dict) else ""
                return
            out.status = STATUS_CLOSED
            out.confidence = 0.9
            out.reason = f"Breezy 源头已无此岗位（当前在招 {len(data)} 个）"
            return
        if code in (404, 410):
            out.status = STATUS_CLOSED
            out.confidence = 0.75
            out.reason = "Breezy board 不存在"
            return
        out.reason = f"Breezy 请求异常 (HTTP {code})"

    # -- Recruitee ---------------------------------------------------------
    def _check_recruitee(self, ref: Dict[str, Any], out: VerifyResult, **_: Any) -> None:
        token, job_id = ref.get("token"), ref.get("job_id")
        if not token:
            out.reason = "无法解析 Recruitee 子域名"
            return
        out.canonical_url = f"https://{token}.recruitee.com/o/{job_id}" if job_id else f"https://{token}.recruitee.com"
        data, code = self.http.get_json(f"https://{token}.recruitee.com/api/offers/")
        out.http_status = code
        if code == 200 and isinstance(data, dict):
            offers = data.get("offers") or []
            if not job_id:
                out.status = STATUS_OPEN
                out.confidence = 0.4
                out.reason = f"仅校验到 Recruitee board 存在（{len(offers)} 个在招岗位）"
                return
            match = next(
                (o for o in offers if isinstance(o, dict) and str(o.get("slug") or o.get("id")) == str(job_id)),
                None,
            )
            if match:
                out.status = STATUS_OPEN
                out.confidence = 0.9
                out.reason = "Recruitee 源头仍在招该岗位"
                out.matched_title = match.get("title", "")
                out.location = match.get("location", "") or ""
                out.posted_at = match.get("published_at") or ""
                return
            out.status = STATUS_CLOSED
            out.confidence = 0.9
            out.reason = f"Recruitee 源头已无此岗位（当前在招 {len(offers)} 个）"
            return
        if code in (404, 410):
            out.status = STATUS_CLOSED
            out.confidence = 0.7
            out.reason = "Recruitee board 不存在"
            return
        out.reason = f"Recruitee 请求异常 (HTTP {code})"

    # -- Personio ----------------------------------------------------------
    def _check_personio(self, ref: Dict[str, Any], out: VerifyResult, **_: Any) -> None:
        token, job_id = ref.get("token"), ref.get("job_id")
        if not token:
            out.reason = "无法解析 Personio 子域名"
            return
        candidates = [
            f"https://{token}.jobs.personio.de/xml?language=en",
            f"https://{token}.jobs.personio.com/xml?language=en",
        ]
        text, code = None, None
        for url in candidates:
            text, code, _ = self.http.get_text(url)
            if code == 200 and text:
                break
        out.http_status = code
        if code == 200 and text:
            ids = set(re.findall(r"<id>(\d+)</id>", text))
            titles = re.findall(r"<name>([^<]+)</name>", text)
            if job_id and str(job_id) in ids:
                out.status = STATUS_OPEN
                out.confidence = 0.8
                out.reason = "Personio 源头 XML feed 中仍存在该岗位"
                out.matched_title = titles[0] if titles else ""
                return
            if job_id:
                out.status = STATUS_CLOSED
                out.confidence = 0.8
                out.reason = f"Personio 源头 feed 已无此岗位（当前 {len(ids)} 个）"
                return
            out.status = STATUS_OPEN
            out.confidence = 0.4
            out.reason = f"仅校验到 Personio board 存在（{len(ids)} 个岗位）"
            return
        out.reason = f"Personio feed 请求异常 (HTTP {code})"

    # -- BambooHR ----------------------------------------------------------
    def _check_bamboohr(self, ref: Dict[str, Any], out: VerifyResult, **_: Any) -> None:
        token, job_id = ref.get("token"), ref.get("job_id")
        if not token:
            out.reason = "无法解析 BambooHR 子域名"
            return
        board = f"https://{token}.bamboohr.com"
        out.canonical_url = f"{board}/careers/{job_id}" if job_id else f"{board}/careers"
        data, code = self.http.get_json(f"{board}/careers/list")
        out.http_status = code
        if code != 200 or not isinstance(data, dict):
            if code in (404, 410):
                out.status = STATUS_CLOSED
                out.confidence = 0.75
                out.reason = "BambooHR board 不存在"
            else:
                out.reason = f"BambooHR 请求异常 (HTTP {code})"
            return

        jobs = data.get("result") or []
        if not isinstance(jobs, list):
            jobs = []
        if not job_id:
            out.status = STATUS_OPEN
            out.confidence = 0.4
            out.reason = f"仅校验到 BambooHR board 存在（{len(jobs)} 个在招岗位）"
            return
        match = next(
            (j for j in jobs if isinstance(j, dict) and str(j.get("id")) == str(job_id)), None
        )
        if match:
            out.status = STATUS_OPEN
            out.confidence = 0.9
            out.reason = "BambooHR 源头仍在招该岗位"
            out.matched_title = str(match.get("jobOpeningName") or "")
            location = match.get("location") or {}
            if isinstance(location, dict):
                out.location = ", ".join(
                    str(v) for v in (location.get("city"), location.get("state"), location.get("country")) if v
                )
            out.apply_url = f"{board}/careers/{job_id}"
            return
        out.status = STATUS_CLOSED
        out.confidence = 0.9
        out.reason = f"BambooHR 源头已无此岗位（当前在招 {len(jobs)} 个）"

    # -- Teamtailor --------------------------------------------------------
    def _check_teamtailor(self, ref: Dict[str, Any], out: VerifyResult, **_: Any) -> None:
        token, job_id = ref.get("token"), ref.get("job_id")
        if not token:
            out.reason = "无法解析 Teamtailor 子域名"
            return
        out.canonical_url = (
            f"https://{token}.teamtailor.com/jobs/{job_id}" if job_id else f"https://{token}.teamtailor.com/jobs"
        )
        # Teamtailor exposes a JSON feed of the career site
        data, code = self.http.get_json(
            f"https://{token}.teamtailor.com/jobs.json",
            headers={"Accept": "application/json"},
        )
        out.http_status = code
        if code == 200 and data is not None:
            jobs = data.get("jobs") if isinstance(data, dict) else data
            if isinstance(jobs, list):
                if not job_id:
                    out.status = STATUS_OPEN
                    out.confidence = 0.4
                    out.reason = f"仅校验到 Teamtailor site 存在（{len(jobs)} 个岗位）"
                    return
                ids = {str(j.get("id")) for j in jobs if isinstance(j, dict)}
                if str(job_id) in ids:
                    out.status = STATUS_OPEN
                    out.confidence = 0.85
                    out.reason = "Teamtailor 源头仍存在该岗位"
                    return
                out.status = STATUS_CLOSED
                out.confidence = 0.85
                out.reason = f"Teamtailor 源头已无此岗位（当前 {len(ids)} 个）"
                return
        # JSON feed unavailable → fall back to the generic page probe
        self._check_generic(ref, out)

    # -- Generic / careers page -------------------------------------------
    def _check_generic(
        self, ref: Dict[str, Any], out: VerifyResult, hint_title: str = "", **_: Any
    ) -> None:
        """HTTP status + closed-phrase + JSON-LD probe for non-mainstream ATS."""
        url = ref.get("url") or out.input_url
        out.ats = out.ats if out.ats != "unknown" else "careers_page"
        html, code, final_url = self.http.get_text(url)
        out.http_status = code
        out.canonical_url = final_url or url
        if code is None:
            out.reason = "无法访问该页面（网络错误/超时）"
            return
        if code in (404, 410):
            out.status = STATUS_CLOSED
            out.confidence = 0.7
            out.reason = f"源页面返回 HTTP {code}，岗位页面已不存在"
            return
        if code in (401, 403):
            out.reason = f"源页面拒绝访问 (HTTP {code})，需登录或反爬"
            return
        if code >= 500:
            out.reason = f"源站异常 (HTTP {code})"
            return

        if not html:
            out.reason = f"源页面返回空内容 (HTTP {code})"
            return

        # Redirect collapsed to a listing/home page usually means the job is gone
        if self._collapsed_to_root(url, final_url):
            out.status = STATUS_CLOSED
            out.confidence = 0.5
            out.reason = "原岗位 URL 被重定向到列表/首页，岗位详情页已不存在"
            return

        lower = html.lower()
        phrase = next((p for p in CLOSED_PHRASES if p in lower), None)
        if phrase:
            out.status = STATUS_CLOSED
            out.confidence = 0.75
            out.reason = f"页面出现失效提示文案: “{phrase}”"
            return

        jobposting = self._extract_jsonld_jobposting(html)
        if jobposting:
            out.matched_title = jobposting.get("title", "") or out.matched_title
            out.posted_at = jobposting.get("datePosted", "") or out.posted_at
            valid_through = jobposting.get("validThrough")
            if valid_through:
                try:
                    dt = datetime.fromisoformat(str(valid_through).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < datetime.now(timezone.utc):
                        out.status = STATUS_CLOSED
                        out.confidence = 0.7
                        out.reason = f"结构化数据 validThrough 已过期 ({valid_through})"
                        return
                except Exception:  # noqa: BLE001
                    pass
            out.status = STATUS_OPEN
            out.confidence = 0.75
            out.reason = "页面存在有效的 JobPosting 结构化数据（Google 索引用）"
            return

        if any(p in lower for p in OPEN_PHRASES):
            out.status = STATUS_OPEN
            out.confidence = 0.5
            out.reason = "页面仍包含申请入口文案，但无结构化数据佐证"
            return

        out.status = STATUS_UNKNOWN
        out.confidence = 0.25
        out.reason = "页面可访问但未找到明确的在招/失效信号（可能是 JS 渲染页面）"

    @staticmethod
    def _collapsed_to_root(original: str, final: str) -> bool:
        if not final:
            return False
        try:
            o, f = urlparse(original), urlparse(final)
        except Exception:  # noqa: BLE001
            return False
        if o.netloc != f.netloc:
            return False
        o_parts = [p for p in o.path.split("/") if p]
        f_parts = [p for p in f.path.split("/") if p]
        return len(o_parts) >= 2 and len(f_parts) <= 1

    @staticmethod
    def _extract_jsonld_jobposting(html: str) -> Optional[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("script", type="application/ld+json"):
            raw = tag.string or tag.get_text() or ""
            if "JobPosting" not in raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
            for node in _walk_json(data):
                if isinstance(node, dict) and "JobPosting" in str(node.get("@type", "")):
                    return node
        return None


def _walk_json(node: Any) -> Iterable[Any]:
    """Yield every dict/list node in a nested JSON structure."""
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk_json(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json(item)


def _apply_token_hint(ref: Dict[str, Any], token_hint: Any) -> None:
    """Merge a caller-supplied board token into an identified reference."""
    if not token_hint or ref.get("token"):
        return
    if isinstance(token_hint, dict):
        hint_ats = (token_hint.get("ats") or "").lower() or None
        hint_token = token_hint.get("token")
        if not hint_token:
            return
        if ref.get("ats") in (None, "unknown"):
            if hint_ats:
                ref["ats"] = hint_ats
        elif hint_ats and ref["ats"] != hint_ats:
            return
        ref["token"] = hint_token
        return
    ref["token"] = str(token_hint)


def board_ref_from_urls(*urls: Optional[str]) -> Optional[Dict[str, str]]:
    """Extract ``{"ats", "token"}`` from the first URL that carries both."""
    for url in urls:
        if not url:
            continue
        try:
            ref = identify(str(url))
        except Exception:  # noqa: BLE001
            continue
        if ref.get("ats") and ref["ats"] != "unknown" and ref.get("token"):
            return {"ats": ref["ats"], "token": ref["token"]}
    return None


_DERIVABLE_ATS = {
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "smartrecruiters",
    "breezy",
    "recruitee",
}


def board_ref_from_company(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Derive ``{"ats", "token", "derived"}`` from a JobDetector company document.

    Prefers the stored ``ats_url`` / ``api_endpoint``; when a company only has a
    declared ATS type (no URL) it guesses the token from the name/domain and
    marks it ``derived=True`` so callers can treat it as lower confidence.
    """
    if not isinstance(doc, dict):
        return None
    ats_system = doc.get("ats_system") or {}
    endpoint = ats_system.get("api_endpoint") if isinstance(ats_system, dict) else None
    declared = str(ats_system.get("type") or "").strip().lower() if isinstance(ats_system, dict) else ""
    ref = board_ref_from_urls(doc.get("ats_url"), endpoint)
    if ref:
        ref["derived"] = False
        return ref
    if declared and declared in _DERIVABLE_ATS:
        for token in (
            re.sub(r"[^a-z0-9]", "", str(doc.get("name") or "").lower()),
            re.sub(r"[^a-z0-9]", "", str(doc.get("domain") or "").split(".")[0].lower()),
        ):
            if token:
                return {"ats": declared, "token": token, "derived": True}
    return None


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------
def verify_url(url: str, hint_title: str = "", hint_company: str = "") -> Dict[str, Any]:
    """Verify one URL and return a plain dict."""
    return SourceVerifier().verify(url, hint_title=hint_title, hint_company=hint_company).to_dict()


def extract_ats_urls(urls: Iterable[str]) -> List[str]:
    """Filter a list of links down to the ones that point at a known ATS."""
    known = {
        "greenhouse",
        "lever",
        "ashby",
        "workable",
        "smartrecruiters",
        "workday",
        "breezy",
        "recruitee",
        "personio",
        "teamtailor",
    }
    out = []
    for u in urls or []:
        try:
            if identify(u).get("ats") in known:
                out.append(u)
        except Exception:  # noqa: BLE001
            continue
    return out
