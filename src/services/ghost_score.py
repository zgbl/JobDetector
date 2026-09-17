"""
Ghost Job scoring engine
========================

Two inputs make a posting suspicious:

1. **Source status** (from :mod:`src.services.source_verify`) — the hard signal.
   If the employer's own ATS no longer has the requisition, the listing on
   Indeed / LinkedIn is unambiguously a ghost. No LLM required.
2. **Content heuristics + LLM judgement** — for everything that is technically
   still live but smells like an evergreen pipeline / agency scrape: age,
   missing source traceability, template language, "talent pool" wording.

Localisation
------------
Both front-ends are served from here: ``lang="en"`` (the website) and
``lang="zh"`` (default, kept for Chinese consumers). Every heuristic reason and
every LLM prompt exists in both languages, and ``recommendation_code`` is a
stable machine-readable enum (``apply`` / ``verify`` / ``ignore``) so a client
never has to pattern-match translated text.

The LLM chain is env-driven and mirrors ``scripts/personal_digest.py``:

    AI_PROVIDER = openrouter | deepseek | gemini | keyword

Every path degrades to a deterministic heuristic score, so this module never
depends on an API key being present.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_ZH = """你是一个专业的招聘行业数据分析师和求职防诈骗专家。你的任务是分析给定的职位描述（Job Description）及元数据，评估该岗位是否为"Ghost Job（幽灵岗位/虚假挂单）"或"中介二次抓取防失效岗位"。

评估标准（扣分制，累加后截断到 0-100）：
1. 发布时间（Post Age）：超过 30 天且无更新标识 +30；超过 60 天 +50。
2. 源头追溯性（Source Traceability）：无明确 ATS 跳转链接、仅平台内一键投递、或第三方中介抓取 +20。
3. JD 泛化程度（JD Vagueness）：充斥模板化套话（如 "fast-paced environment"、"do all assigned tasks"），缺乏具体团队、产品架构、明确技术栈要求 +20。
4. 招聘常设性（Evergreen Listing）：包含 "continuous talent pipeline"、"talent pool"、"general application"、"evergreen"、"always hiring" 等收集简历特征词 +30。
5. 源头状态（Source Status）：若已知源头 ATS 已下架该岗位，ghost_score 直接 >= 95。

只输出严格的 JSON，不要 markdown 代码块，不要解释：
{
  "ghost_score": 0-100 的整数,
  "is_ghost_job": true/false,
  "risk_factors": ["最多 3 条具体扣分原因"],
  "recommendation_code": "apply" | "verify" | "ignore",
  "one_liner": "不超过 2 句话的直白评语，直接点出痛点，不要废话"
}"""

SYSTEM_PROMPT_EN = """You are a recruiting-industry data analyst and job-scam specialist. Analyse the given job posting and its metadata, and judge whether it is a "ghost job" (a stale or fake listing) or a listing that was merely re-scraped by an agency.

Scoring (points are added, then clamped to 0-100):
1. Post age: older than 30 days with no update marker +30; older than 60 days +50.
2. Source traceability: no direct ATS apply link, platform-only one-click apply, or third-party agency scrape +20.
3. JD vagueness: heavy template language ("fast-paced environment", "do all assigned tasks") with no concrete team, product or tech-stack detail +20.
4. Evergreen listing: contains "continuous talent pipeline", "talent pool", "general application", "evergreen", "always hiring" and similar résumé-harvesting wording +30.
5. Source status: if the employer's own ATS has already taken the posting down, ghost_score must be >= 95.

Output strict JSON only — no markdown code fence, no explanation:
{
  "ghost_score": integer 0-100,
  "is_ghost_job": true/false,
  "risk_factors": ["at most 3 concrete reasons"],
  "recommendation_code": "apply" | "verify" | "ignore",
  "one_liner": "a blunt one-to-two sentence verdict that names the problem directly"
}"""

EVERGREEN_PATTERNS = (
    "talent pool",
    "talent pipeline",
    "continuous talent",
    "evergreen",
    "always hiring",
    "general application",
    "open application",
    "spontaneous application",
    "future opportunities",
    "speculative application",
    "人才库",
    "长期招聘",
)

VAGUE_PATTERNS = (
    "fast-paced environment",
    "fast paced environment",
    "do all assigned tasks",
    "other duties as assigned",
    "wear many hats",
    "self-starter",
    "rockstar",
    "ninja",
    "work hard play hard",
    "competitive salary",
    "excellent communication skills",
    "team player",
)

SPECIFIC_PATTERNS = (
    "kubernetes",
    "terraform",
    "postgres",
    "python",
    "golang",
    "typescript",
    "react",
    "aws",
    "azure",
    "gcp",
    "grpc",
    "kafka",
    "spark",
    "llm",
    "rag",
    "vector database",
    "on-call",
    "sla",
    "roadmap",
    "quarter",
)

AGENCY_PATTERNS = (
    "our client",
    "our client is",
    "client of ours",
    "on behalf of our client",
    "staffing agency",
    "recruitment agency",
    "recruiting firm",
    "consultancy is looking",
    "职位由",
    "猎头",
    "代招",
)

ATS_SOURCES = (
    "direct_ats",
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
    "careers_page",
)

# ---------------------------------------------------------------------------
# Localisation tables
# ---------------------------------------------------------------------------
# Every heuristic reason is produced from a stable code, so a missing
# translation is a KeyError in tests rather than Chinese leaking into the
# English UI.
FACTOR_TEXT: Dict[str, Dict[str, str]] = {
    "age_over_60": {
        "zh": "挂单已 {days} 天，远超 60 天红线",
        "en": "Posted {days} days ago — well past the 60-day red line",
    },
    "age_over_30": {
        "zh": "挂单已 {days} 天，超过 30 天警戒线",
        "en": "Posted {days} days ago — past the 30-day warning line",
    },
    "agency_scrape": {
        "zh": "疑似中介/聚合站二次抓取，无雇主直招入口",
        "en": "Looks like an agency or aggregator re-scrape — no direct employer apply path",
    },
    "no_ats_entry": {
        "zh": "无明确源头 ATS 投递入口，仅平台内一键投递",
        "en": "No clear source-ATS apply entry — platform-only one-click apply",
    },
    "jd_too_short": {
        "zh": "JD 内容过短，缺少团队/产品/技术栈细节",
        "en": "Job description is very short — no team, product or tech-stack detail",
    },
    "jd_vague": {
        "zh": "JD 模板化套话多（{term} 等）且无具体技术栈",
        "en": "Job description is heavy on template language ({term}) with no concrete tech stack",
    },
    "evergreen": {
        "zh": "含常设招聘/人才库特征词：{term}",
        "en": "Contains evergreen / résumé-harvesting wording: {term}",
    },
    "agency_wording": {
        "zh": "出现中介代招口吻：{term}",
        "en": "Reads like an agency posting: {term}",
    },
    "source_closed": {
        "zh": "源头 ATS 已下架该岗位（招聘已结束）",
        "en": "The source ATS has already taken this posting down (the search is over)",
    },
    "no_signal": {
        "zh": "未发现明显幽灵岗位信号",
        "en": "No obvious ghost-job signals found",
    },
}

RECOMMENDATION_TEXT: Dict[str, Dict[str, str]] = {
    "apply": {"zh": "直接投递", "en": "Apply directly"},
    "verify": {"zh": "建议去官网核实", "en": "Verify on the company site"},
    "ignore": {"zh": "建议忽略", "en": "Ignore it"},
}

ONE_LINER_RISKY: Dict[str, str] = {
    "zh": "该岗位 Ghost 风险偏高（{score}/100）：{reason}。{recommendation}。",
    "en": "This posting carries a high ghost-job risk ({score}/100): {reason}. {recommendation}.",
}
ONE_LINER_CLEAN: Dict[str, str] = {
    "zh": "暂未发现明显幽灵岗位特征（风险 {score}/100），可以正常准备投递。",
    "en": "No obvious ghost-job signals (risk {score}/100) — worth preparing an application.",
}
ONE_LINER_CLOSED: Dict[str, str] = {
    "zh": "源头 ATS 已下架该岗位，Indeed/LinkedIn 上属于陈旧挂单，不必投递。",
    "en": "The employer's own ATS has taken this posting down — it is a stale listing, don't apply.",
}

_LLM_RECOMMENDATION_TO_CODE = {
    "直接投递": "apply",
    "建议去官网核实": "verify",
    "建议忽略": "ignore",
    "apply directly": "apply",
    "apply": "apply",
    "verify on the company site": "verify",
    "verify": "verify",
    "ignore it": "ignore",
    "ignore": "ignore",
}


def _norm_lang(lang: Optional[str]) -> str:
    return "en" if str(lang or "").lower().startswith("en") else "zh"


def _text(table: Dict[str, Dict[str, str]], code: str, lang: str, **params: Any) -> str:
    entry = table.get(code)
    if entry is None:
        # Never leak a raw key into the UI; use the code itself as last resort.
        return code
    template = entry.get(lang) or entry.get("zh") or code
    try:
        return template.format(**params) if params else template
    except (KeyError, IndexError):
        return template


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------
@dataclass
class GhostVerdict:
    ghost_score: int = 0
    is_ghost_job: bool = False
    risk_factors: List[str] = field(default_factory=list)
    recommendation: str = ""
    recommendation_code: str = "apply"
    one_liner: str = ""
    provider: str = "heuristic"
    source_status: str = "unknown"
    lang: str = "zh"
    analyzed_at: str = ""
    cached: bool = False

    def __post_init__(self) -> None:
        if not self.analyzed_at:
            self.analyzed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        if not self.recommendation:
            self.recommendation = RECOMMENDATION_TEXT[self.recommendation_code]["zh" if self.lang == "zh" else "en"]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["risk_factors"] = list(self.risk_factors)
        return data


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------
def heuristic_signals(
    job_title: str,
    company_name: str,
    post_age_days: Optional[float],
    source_type: str,
    jd_text: str,
    source_status: str = "unknown",
    lang: str = "zh",
) -> Dict[str, Any]:
    """Deterministic risk assessment — the always-available baseline."""
    lang = _norm_lang(lang)
    score = 0
    found: List[tuple] = []  # (weight, code, params) — sorted so the heaviest reasons surface
    text = (jd_text or "").lower()
    source_type = (source_type or "").lower()

    # 1. Age
    if post_age_days is not None:
        try:
            age = float(post_age_days)
        except (TypeError, ValueError):
            age = None
        if age is not None:
            if age > 60:
                score += 50
                found.append((50, "age_over_60", {"days": int(age)}))
            elif age > 30:
                score += 30
                found.append((30, "age_over_30", {"days": int(age)}))

    # 2. Source traceability
    if source_type not in ATS_SOURCES:
        score += 20
        if source_type in ("agency", "agency_scraped", "aggregator"):
            found.append((25, "agency_scrape", {}))
        else:
            found.append((20, "no_ats_entry", {}))

    # 3. Vagueness vs. specificity
    vague_hits = [p for p in VAGUE_PATTERNS if p in text]
    specific_hits = [p for p in SPECIFIC_PATTERNS if p in text]
    if not jd_text or len(jd_text.strip()) < 200:
        score += 20
        found.append((20, "jd_too_short", {}))
    elif len(vague_hits) >= 2 and len(specific_hits) == 0:
        score += 20
        found.append((20, "jd_vague", {"term": vague_hits[0]}))

    # 4. Evergreen / pipeline wording
    evergreen_hits = [p for p in EVERGREEN_PATTERNS if p in text]
    if evergreen_hits:
        score += 30
        found.append((30, "evergreen", {"term": evergreen_hits[0]}))

    # 5. Agency wording
    agency_hits = [p for p in AGENCY_PATTERNS if p in text]
    if agency_hits:
        score += 20
        found.append((20, "agency_wording", {"term": agency_hits[0]}))

    # Hard signal: the employer's own ATS already dropped it
    if source_status == "closed":
        score = max(score + 40, 95)
        found.append((100, "source_closed", {}))

    score = max(0, min(100, score))

    ordered = sorted(found, key=lambda item: item[0], reverse=True)
    factors = [_text(FACTOR_TEXT, code, lang, **params) for _, code, params in ordered]

    if score >= 80:
        code = "ignore"
    elif score > 50:
        code = "verify"
    else:
        code = "apply"

    return {
        "ghost_score": score,
        "is_ghost_job": score > 50,
        "recommendation_code": code,
        "recommendation": RECOMMENDATION_TEXT[code][lang],
        "risk_factors": factors[:3] or [_text(FACTOR_TEXT, "no_signal", lang)],
        "signals": {
            "vague_hits": vague_hits,
            "specific_hits": specific_hits,
            "evergreen_hits": evergreen_hits,
            "agency_hits": agency_hits,
        },
    }


def _one_liner_from_heuristic(score: int, factors: List[str], recommendation: str, lang: str) -> str:
    lang = _norm_lang(lang)
    if score > 50:
        reason = factors[0] if factors else ("存在明显风险信号" if lang == "zh" else "clear risk signals")
        return ONE_LINER_RISKY[lang].format(score=score, reason=reason, recommendation=recommendation)
    return ONE_LINER_CLEAN[lang].format(score=score)


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------
class GhostAnalyzer:
    """Score a posting as a possible ghost job."""

    def __init__(self, provider: Optional[str] = None, timeout: int = 45, lang: Optional[str] = None):
        self.provider = (provider or os.getenv("AI_PROVIDER", "heuristic")).lower()
        self.timeout = timeout
        self.lang = _norm_lang(lang or os.getenv("GHOST_DEFAULT_LANG", "zh"))
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY", os.getenv("MINIMAX_API_KEY", ""))
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "minimax/minimax-m2.5:free")
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self.gemini_key = os.getenv("GEMINI_API_KEY", "")

    # -- public ------------------------------------------------------------
    def analyze(
        self,
        job_title: str = "",
        company_name: str = "",
        post_age_days: Optional[float] = None,
        source_type: str = "unknown",
        jd_text: str = "",
        source_status: str = "unknown",
        lang: Optional[str] = None,
    ) -> GhostVerdict:
        lang = _norm_lang(lang or self.lang)
        baseline = heuristic_signals(
            job_title, company_name, post_age_days, source_type, jd_text, source_status, lang
        )

        # Hard, non-probabilistic signal: the source ATS already removed it.
        if source_status == "closed":
            factors = [_text(FACTOR_TEXT, "source_closed", lang)] + [
                f for f in baseline["risk_factors"]
                if f != _text(FACTOR_TEXT, "source_closed", lang)
            ]
            return GhostVerdict(
                ghost_score=max(95, baseline["ghost_score"]),
                is_ghost_job=True,
                risk_factors=factors[:3],
                recommendation=RECOMMENDATION_TEXT["ignore"][lang],
                recommendation_code="ignore",
                one_liner=ONE_LINER_CLOSED[lang],
                provider="source_ats",
                source_status=source_status,
                lang=lang,
            )

        llm = self._ask_llm(
            job_title, company_name, post_age_days, source_type, jd_text,
            source_status, baseline, lang,
        )
        if llm:
            return self._merge(llm, baseline, source_status, lang)

        return GhostVerdict(
            ghost_score=baseline["ghost_score"],
            is_ghost_job=baseline["is_ghost_job"],
            risk_factors=baseline["risk_factors"],
            recommendation=baseline["recommendation"],
            recommendation_code=baseline["recommendation_code"],
            one_liner=_one_liner_from_heuristic(
                baseline["ghost_score"], baseline["risk_factors"],
                baseline["recommendation"], lang,
            ),
            provider="heuristic",
            source_status=source_status,
            lang=lang,
        )

    # -- LLM chain ---------------------------------------------------------
    def _ask_llm(
        self,
        job_title: str,
        company_name: str,
        post_age_days: Optional[float],
        source_type: str,
        jd_text: str,
        source_status: str,
        baseline: Dict[str, Any],
        lang: str,
    ) -> Optional[Dict[str, Any]]:
        user_prompt = self._build_user_prompt(
            job_title, company_name, post_age_days, source_type, jd_text,
            source_status, baseline, lang,
        )
        for provider in self._provider_chain():
            try:
                raw = self._call_provider(provider, user_prompt, lang)
                if not raw:
                    continue
                parsed = _extract_json(raw)
                if parsed and "ghost_score" in parsed:
                    parsed["_provider"] = provider
                    return parsed
                logger.warning("ghost: %s returned unparsable payload", provider)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ghost: provider %s failed: %s", provider, exc)
        return None

    def _provider_chain(self) -> List[str]:
        """Configured provider first, then any other provider that has a key."""
        if self.provider in ("keyword", "heuristic", "none", "off"):
            return []
        available = []
        if self.openrouter_key:
            available.append("openrouter")
        if self.deepseek_key:
            available.append("deepseek")
        if self.gemini_key:
            available.append("gemini")
        configured = self.provider if self.provider in available else None
        return ([configured] + [p for p in available if p != configured]) if configured else available

    def _build_user_prompt(
        self,
        job_title: str,
        company_name: str,
        post_age_days: Optional[float],
        source_type: str,
        jd_text: str,
        source_status: str,
        baseline: Dict[str, Any],
        lang: str,
    ) -> str:
        jd = (jd_text or "").strip()
        if len(jd) > 6000:
            jd = jd[:6000] + ("\n...[truncated]" if lang == "en" else "\n...[已截断]")
        if lang == "en":
            status_line = {
                "open": "the source ATS confirms it is still open",
                "closed": "the source ATS has taken it down",
                "unknown": "the source status is unknown",
            }.get(source_status, "the source status is unknown")
            unknown = "(unknown)"
            return f"""Job Title: {job_title or unknown}
Company: {company_name or unknown}
Post Age (Days): {post_age_days if post_age_days is not None else unknown}
ATS / Source Type: {source_type or "unknown"} ({status_line})

The rule engine's preliminary reasons were: {json.dumps(baseline.get('risk_factors', []), ensure_ascii=False)}
Re-check them yourself and adjust the score if you disagree.

JD Text:
{jd or "(no job description provided — judge from the metadata and say so in risk_factors)"}"""

        status_cn = {
            "open": "源头 ATS 校验为仍在招聘",
            "closed": "源头 ATS 校验为已下架",
            "unknown": "源头状态未知",
        }.get(source_status, "源头状态未知")
        return f"""Job Title: {job_title or "(未知)"}
Company: {company_name or "(未知)"}
Post Age (Days): {post_age_days if post_age_days is not None else "(未知)"}
ATS / Source Type: {source_type or "unknown"} （{status_cn}）

规则引擎已给出的初步扣分：{json.dumps(baseline.get('risk_factors', []), ensure_ascii=False)}
请结合这些信号自行复核，若不同意可调整分数。

JD Text:
{jd or "(未提供职位描述，请主要依据元数据判断，并在 risk_factors 中说明信息不足)"}"""

    def _call_provider(self, provider: str, user_prompt: str, lang: str = "zh") -> Optional[str]:
        import requests

        system_prompt = SYSTEM_PROMPT_EN if _norm_lang(lang) == "en" else SYSTEM_PROMPT_ZH

        if provider == "openrouter":
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://jobdetector.blackrice.top",
                    "X-Title": "JobDetector",
                },
                json={
                    "model": self.openrouter_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
                timeout=self.timeout,
            )
            data = resp.json()
            if "choices" not in data:
                raise RuntimeError(f"openrouter error: {str(data)[:200]}")
            return data["choices"][0]["message"]["content"]

        if provider == "deepseek":
            resp = requests.post(
                f"{self.deepseek_base.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.deepseek_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
                timeout=self.timeout,
            )
            data = resp.json()
            if "choices" not in data:
                raise RuntimeError(f"deepseek error: {str(data)[:200]}")
            return data["choices"][0]["message"]["content"]

        if provider == "gemini":
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-1.5-flash:generateContent?key={self.gemini_key}"
            )
            resp = requests.post(
                url,
                json={
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"parts": [{"text": user_prompt}]}],
                    "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
                },
                timeout=self.timeout,
            )
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

        return None

    @staticmethod
    def _merge(llm: Dict[str, Any], baseline: Dict[str, Any], source_status: str, lang: str) -> GhostVerdict:
        lang = _norm_lang(lang)
        try:
            score = int(round(float(llm.get("ghost_score", baseline["ghost_score"]))))
        except (TypeError, ValueError):
            score = baseline["ghost_score"]
        score = max(0, min(100, score))

        factors = llm.get("risk_factors") or baseline["risk_factors"]
        if isinstance(factors, str):
            factors = [factors]
        factors = [str(f) for f in factors][:3]

        is_ghost = llm.get("is_ghost_job")
        if not isinstance(is_ghost, bool):
            is_ghost = score > 50

        # Prefer the machine-readable enum; fall back to mapping the label.
        code = str(llm.get("recommendation_code") or "").strip().lower()
        if code not in RECOMMENDATION_TEXT:
            label = str(llm.get("recommendation") or "").strip().lower()
            code = _LLM_RECOMMENDATION_TO_CODE.get(label) or baseline["recommendation_code"]
        recommendation = RECOMMENDATION_TEXT[code][lang]

        one_liner = str(llm.get("one_liner") or "").strip()
        if not one_liner:
            one_liner = _one_liner_from_heuristic(score, factors, recommendation, lang)

        return GhostVerdict(
            ghost_score=score,
            is_ghost_job=is_ghost,
            risk_factors=factors,
            recommendation=recommendation,
            recommendation_code=code,
            one_liner=one_liner,
            provider=str(llm.get("_provider") or "llm"),
            source_status=source_status,
            lang=lang,
        )


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON extraction from an LLM response."""
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001
            pass
        # Tolerate trailing commas
        try:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", match.group(0)))
        except Exception:  # noqa: BLE001
            pass
    return None


def analyze_job(
    job_title: str = "",
    company_name: str = "",
    post_age_days: Optional[float] = None,
    source_type: str = "unknown",
    jd_text: str = "",
    source_status: str = "unknown",
    provider: Optional[str] = None,
    lang: str = "zh",
) -> Dict[str, Any]:
    """Convenience wrapper returning a plain dict."""
    return GhostAnalyzer(provider=provider).analyze(
        job_title=job_title,
        company_name=company_name,
        post_age_days=post_age_days,
        source_type=source_type,
        jd_text=jd_text,
        source_status=source_status,
        lang=lang,
    ).to_dict()


def days_since(value: Any) -> Optional[float]:
    """Convert a datetime / ISO string / epoch into "days ago"."""
    if value is None or value == "":
        return None
    dt: Optional[datetime] = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(value) / (1000.0 if value > 1e11 else 1.0), tz=timezone.utc)
        except Exception:  # noqa: BLE001
            return None
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    return round(delta.total_seconds() / 86400.0, 1)
