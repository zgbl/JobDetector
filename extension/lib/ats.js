/**
 * lib/ats.js — ATS identification + offline (no-backend) verification.
 *
 * This module is intentionally PURE with respect to the extension platform:
 * it never touches `chrome.*`, so it can be imported by the MV3 service worker
 * (`background.js`) and by plain `node --test` unit tests.
 *
 * The logic is a JavaScript port of the Python reference
 * `src/services/source_verify.py` (functions `identify`, `_check_greenhouse`,
 * `_check_lever`, `_check_ashby`, `_check_generic`). Reason strings keep the
 * same Simplified-Chinese wording so that backend and local verdicts read the
 * same in the UI.
 */

/* ------------------------------------------------------------------ *
 * ATS host patterns (mirrors the Python regex table)
 * ------------------------------------------------------------------ */
const GREENHOUSE_RE = /(?:boards|job-boards|boards-api)\.greenhouse\.io/i;
const LEVER_RE = /(?:jobs|api|hire)\.lever\.co/i;
const ASHBY_RE = /(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com)/i;
const WORKABLE_RE = /(?:apply|jobs)\.workable\.com/i;
const SMARTRECRUITERS_RE = /(?:jobs|careers|api)\.smartrecruiters\.com/i;
const WORKDAY_RE = /\.(?:wd\d+)\.myworkdayjobs\.com/i;
const BREEZY_RE = /\.breezy\.hr/i;
const RECRUITEE_RE = /\.recruitee\.com/i;
const PERSONIO_RE = /\.jobs\.personio\.(?:de|com)/i;
const TEAMTAILOR_RE = /\.teamtailor\.com/i;

/** Domains we recognise while harvesting links out of a job page. */
export const ATS_DOMAIN_RE =
  /(?:boards|job-boards|boards-api)\.greenhouse\.io|(?:jobs|api|hire)\.lever\.co|(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com)|(?:apply|jobs)\.workable\.com|(?:jobs|careers|api)\.smartrecruiters\.com|\.(?:wd\d+)\.myworkdayjobs\.com|\.breezy\.hr|\.recruitee\.com|\.jobs\.personio\.(?:de|com)|\.teamtailor\.com/i;

/** Human-readable ATS labels used in the UI. */
export const ATS_LABELS = {
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  ashby: 'Ashby',
  workable: 'Workable',
  smartrecruiters: 'SmartRecruiters',
  workday: 'Workday',
  breezy: 'Breezy',
  recruitee: 'Recruitee',
  personio: 'Personio',
  teamtailor: 'Teamtailor',
  careers_page: '企业招聘页',
  unknown: '未知来源',
};

/** Every ATS the identifier understands. */
export const KNOWN_ATS = Object.keys(ATS_LABELS).filter(
  (k) => k !== 'careers_page' && k !== 'unknown'
);

/** Phrases that mean "this requisition is gone" on a generic careers page. */
export const CLOSED_PHRASES = [
  'no longer accepting applications',
  'this position has been filled',
  'position has been filled',
  'this job has been filled',
  'job posting has expired',
  'this posting has expired',
  'this job is no longer available',
  'this position is no longer available',
  'the job you are looking for',
  'job not found',
  'no longer available',
  'position closed',
  'posting is closed',
  'applications are closed',
  'this role has been closed',
];

/** Phrases that suggest applications are still being accepted. */
export const OPEN_PHRASES = [
  'apply for this job',
  'apply now',
  'submit application',
  'apply for this position',
];

export const DEFAULT_TIMEOUT_MS = 8000;

/* ------------------------------------------------------------------ *
 * Small helpers
 * ------------------------------------------------------------------ */

/** Prepend `https://` when the user pasted a scheme-less URL. */
export function normalizeUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return '';
  const trimmed = rawUrl.trim();
  if (!trimmed) return '';
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return 'https://' + trimmed.replace(/^\/+/, '');
}

/** Query params used by LinkedIn / Indeed to wrap an outbound apply link. */
const REDIRECT_PARAMS = ['url', 'u', 'target', 'redirect', 'redirect_url', 'dest', 'destination', 'to'];

/**
 * Unwrap aggregator redirect wrappers, e.g.
 * `linkedin.com/redir/redirect?url=https%3A%2F%2Fjobs.lever.co%2F...`.
 * Returns the inner URL when it points at a known ATS, else the input.
 */
export function unwrapRedirectUrl(rawUrl, depth = 2) {
  let current = normalizeUrl(rawUrl);
  for (let i = 0; i < depth; i += 1) {
    if (!current) return current;
    let parsed;
    try {
      parsed = new URL(current);
    } catch {
      return current;
    }
    if (ATS_DOMAIN_RE.test(parsed.hostname || '')) return current;
    let found = '';
    for (const key of REDIRECT_PARAMS) {
      let value = null;
      try {
        value = parsed.searchParams.get(key);
      } catch {
        value = null;
      }
      if (!value) continue;
      let candidate = value;
      try {
        candidate = decodeURIComponent(value);
      } catch {
        candidate = value;
      }
      if (/^https?:\/\//i.test(candidate)) {
        found = candidate;
        break;
      }
    }
    if (!found) return current;
    current = found;
  }
  return current;
}

function splitParts(pathname) {
  return String(pathname || '')
    .split('/')
    .filter(Boolean);
}

/** A VerifyResult with every field present, exactly matching the HTTP contract. */
export function emptyResult(inputUrl = '') {
  return {
    input_url: inputUrl || '',
    status: 'unknown',
    ats: 'unknown',
    confidence: 0,
    reason: '',
    reason_en: '',
    canonical_url: '',
    apply_url: '',
    matched_title: '',
    company: '',
    location: '',
    posted_at: '',
    http_status: null,
    checked_at: new Date().toISOString(),
    elapsed_ms: 0,
    cached: false,
  };
}

/** Normalise any partial/foreign object into the frozen VerifyResult shape. */
export function coerceResult(raw, inputUrl = '') {
  const base = emptyResult(inputUrl);
  if (!raw || typeof raw !== 'object') return base;
  const status = ['open', 'closed', 'unknown'].includes(raw.status) ? raw.status : 'unknown';
  let confidence = Number(raw.confidence);
  if (!Number.isFinite(confidence)) confidence = 0;
  confidence = Math.min(1, Math.max(0, confidence));
  return {
    input_url: str(raw.input_url) || inputUrl || '',
    status,
    ats: str(raw.ats) || 'unknown',
    confidence,
    reason: str(raw.reason),
    reason_en: str(raw.reason_en),
    canonical_url: str(raw.canonical_url),
    apply_url: str(raw.apply_url),
    matched_title: str(raw.matched_title),
    company: str(raw.company),
    location: str(raw.location),
    posted_at: str(raw.posted_at),
    http_status: Number.isFinite(Number(raw.http_status)) && raw.http_status !== null
      ? Number(raw.http_status)
      : null,
    checked_at: str(raw.checked_at) || new Date().toISOString(),
    elapsed_ms: Number.isFinite(Number(raw.elapsed_ms)) ? Number(raw.elapsed_ms) : 0,
    cached: Boolean(raw.cached),
  };
}

function str(value) {
  if (value === null || value === undefined) return '';
  return typeof value === 'string' ? value : String(value);
}

/* ------------------------------------------------------------------ *
 * identifyAts
 * ------------------------------------------------------------------ */

/**
 * Classify a URL and pull out the identifiers needed to query the ATS.
 *
 * @param {string} rawUrl
 * @returns {{ats: string, token: string|null, jobId: string|null}}
 */
export function identifyAts(rawUrl) {
  const out = { ats: 'unknown', token: null, jobId: null };
  const url = unwrapRedirectUrl(rawUrl);
  if (!url) return out;

  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return out;
  }

  const host = parsed.hostname.toLowerCase();
  const parts = splitParts(parsed.pathname);
  const q = parsed.searchParams;

  // --- Greenhouse -------------------------------------------------------
  // Many companies expose their Greenhouse board behind their own domain,
  // e.g. https://stripe.com/jobs/search?gh_jid=8172487 . The board token is
  // then unknown, so the caller may inject one via `tokenHint`.
  if (q.has('gh_jid') && !GREENHOUSE_RE.test(host)) {
    out.ats = 'greenhouse';
    out.jobId = q.get('gh_jid') || null;
    out.token = q.get('for') || null;
    return out;
  }

  if (GREENHOUSE_RE.test(host)) {
    out.ats = 'greenhouse';
    // embed form: /embed/job_app?for=TOKEN&token=JOBID
    if (q.has('for')) {
      out.token = q.get('for') || null;
      out.jobId = q.get('token') || q.get('job_id') || null;
      return out;
    }
    let p = parts;
    if (p.length >= 3 && p[0] === 'v1' && p[1] === 'boards') p = p.slice(2);
    if (p.length) out.token = p[0];
    const idx = p.indexOf('jobs');
    if (idx !== -1 && p.length > idx + 1 && /^\d+$/.test(p[idx + 1])) {
      out.jobId = p[idx + 1];
    }
    return out;
  }

  // --- Lever ------------------------------------------------------------
  if (LEVER_RE.test(host)) {
    out.ats = 'lever';
    let p = parts;
    if (p.length > 1 && p[0] === 'v0' && p[1] === 'postings') p = p.slice(2);
    if (p.length) out.token = p[0];
    if (p.length > 1) out.jobId = p[1];
    return out;
  }

  // --- Ashby ------------------------------------------------------------
  if (ASHBY_RE.test(host)) {
    out.ats = 'ashby';
    if (parts.length && parts[0] === 'posting-api') {
      out.token = parts[parts.length - 1];
    } else {
      if (parts.length) out.token = parts[0];
      if (parts.length > 1) out.jobId = parts[1];
    }
    return out;
  }

  // --- Workable ---------------------------------------------------------
  if (WORKABLE_RE.test(host)) {
    out.ats = 'workable';
    if (host.startsWith('jobs.')) {
      // jobs.workable.com/view/{id}/{slug} — no board token available
      if (parts.length > 1 && parts[0] === 'view') out.jobId = parts[1];
      return out;
    }
    if (parts.length && parts[0] === 'j') {
      // apply.workable.com/j/{SHORTCODE}
      out.jobId = parts.length > 1 ? parts[1] : null;
      return out;
    }
    if (parts.length) out.token = parts[0];
    if (parts.length > 2 && parts[1] === 'j') out.jobId = parts[2];
    else if (parts.length > 1) out.jobId = parts[1];
    return out;
  }

  // --- SmartRecruiters --------------------------------------------------
  if (SMARTRECRUITERS_RE.test(host)) {
    out.ats = 'smartrecruiters';
    if (parts.length) out.token = parts[0];
    if (parts.length > 1) out.jobId = parts[1].split('-')[0];
    // api.smartrecruiters.com/v1/companies/{token}/postings/{id}
    const idx = parts.indexOf('companies');
    if (idx !== -1) {
      if (parts.length > idx + 1) out.token = parts[idx + 1];
      if (parts.length > idx + 3) out.jobId = parts[idx + 3];
    }
    return out;
  }

  // --- Workday ----------------------------------------------------------
  if (WORKDAY_RE.test(host)) {
    out.ats = 'workday';
    out.token = host.split('.')[0];
    let p = parts;
    if (p.length && /^[a-z]{2}-[A-Z]{2}$/.test(p[0])) p = p.slice(1);
    const idx = p.indexOf('job');
    if (idx !== -1) out.jobId = p.slice(idx).join('/');
    return out;
  }

  // --- Breezy -----------------------------------------------------------
  if (BREEZY_RE.test(host)) {
    out.ats = 'breezy';
    out.token = host.split('.')[0];
    if (parts.length > 1 && (parts[0] === 'p' || parts[0] === 'positions')) {
      out.jobId = parts[1];
    }
    return out;
  }

  // --- Recruitee --------------------------------------------------------
  if (RECRUITEE_RE.test(host)) {
    out.ats = 'recruitee';
    out.token = host.split('.')[0];
    if (parts.length > 1 && parts[0] === 'o') out.jobId = parts[1];
    return out;
  }

  // --- Personio ---------------------------------------------------------
  if (PERSONIO_RE.test(host)) {
    out.ats = 'personio';
    out.token = host.split('.')[0];
    if (parts.length > 1 && parts[0] === 'job') out.jobId = parts[1];
    return out;
  }

  // --- Teamtailor -------------------------------------------------------
  if (TEAMTAILOR_RE.test(host)) {
    out.ats = 'teamtailor';
    out.token = host.split('.')[0];
    if (parts.length > 1 && parts[0] === 'jobs') out.jobId = parts[1];
    return out;
  }

  return out;
}

/** True when the URL points at an ATS we can verify. */
export function isKnownAts(url) {
  return KNOWN_ATS.includes(identifyAts(url).ats);
}

/**
 * Build the cache key for a verification.
 * `ats|token|jobId` when the source is identifiable, else the normalized URL.
 */
export function cacheKeyFor(ref, fallbackUrl = '') {
  if (ref && ref.ats && ref.ats !== 'unknown' && (ref.token || ref.jobId)) {
    return `${ref.ats}|${ref.token || ''}|${ref.jobId || ''}`;
  }
  return normalizeUrl(fallbackUrl) || 'unknown';
}

/* ------------------------------------------------------------------ *
 * Offline verification (greenhouse / lever / ashby + generic probe)
 * ------------------------------------------------------------------ */

async function fetchWithTimeout(url, { timeoutMs = DEFAULT_TIMEOUT_MS, headers } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      signal: controller.signal,
      redirect: 'follow',
      headers: headers || {
        Accept: 'application/json, text/html;q=0.9, */*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
      },
    });
  } finally {
    clearTimeout(timer);
  }
}

async function getJson(url, timeoutMs) {
  try {
    const res = await fetchWithTimeout(url, { timeoutMs });
    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    return { code: res.status, data, finalUrl: res.url || url };
  } catch {
    return { code: null, data: null, finalUrl: url };
  }
}

async function getText(url, timeoutMs) {
  try {
    const res = await fetchWithTimeout(url, { timeoutMs });
    let text = '';
    try {
      text = await res.text();
    } catch {
      text = '';
    }
    return { code: res.status, text, finalUrl: res.url || url };
  } catch {
    return { code: null, text: '', finalUrl: url };
  }
}

async function checkGreenhouse(ref, out, timeoutMs) {
  const token = ref.token;
  const jobId = ref.jobId;
  if (!token) {
    out.reason = '无法从 URL 解析 Greenhouse board token';
    return;
  }
  const base = `https://boards-api.greenhouse.io/v1/boards/${token}`;
  out.canonical_url = jobId
    ? `https://job-boards.greenhouse.io/${token}/jobs/${jobId}`
    : `https://job-boards.greenhouse.io/${token}`;

  if (jobId) {
    const { code, data } = await getJson(`${base}/jobs/${jobId}`, timeoutMs);
    out.http_status = code;
    if (code === 200 && data && typeof data === 'object') {
      out.status = 'open';
      out.confidence = 0.98;
      out.reason = 'Greenhouse 源头 API 返回该岗位仍在招';
      out.matched_title = str(data.title);
      const loc = data.location;
      out.location = loc && typeof loc === 'object' ? str(loc.name) : str(loc);
      out.posted_at = str(data.updated_at || data.first_published);
      out.apply_url = str(data.absolute_url) || out.canonical_url;
      flagDeadline(data, out);
      return;
    }
    if (code === 404 || code === 410) {
      // A 404 can also mean "unlisted job post" — confirm with the board list
      const listed = await greenhouseListed(base, jobId, timeoutMs);
      if (listed === true) {
        out.status = 'open';
        out.confidence = 0.75;
        out.reason = '岗位详情 API 404，但在 board 列表中仍存在（unlisted job post）';
      } else if (listed === false) {
        out.status = 'closed';
        out.confidence = 0.97;
        out.reason = 'Greenhouse 源头已下架该岗位（详情 404 且 board 列表无此 ID）';
      } else {
        out.status = 'closed';
        out.confidence = 0.8;
        out.reason = 'Greenhouse 源头详情返回 404（board 列表二次确认失败）';
      }
      return;
    }
    if (code === 401 || code === 403) {
      out.reason = 'Greenhouse board 未公开或拒绝访问';
      return;
    }
    out.reason = `Greenhouse 详情请求异常 (HTTP ${code})`;
    return;
  }

  // Board-only URL: report board health
  const { code, data } = await getJson(`${base}/jobs`, timeoutMs);
  out.http_status = code;
  if (code === 200 && data && typeof data === 'object') {
    const jobs = Array.isArray(data.jobs) ? data.jobs : [];
    out.status = 'open';
    out.confidence = 0.4;
    out.reason = `仅校验到 board 存在（${jobs.length} 个在招岗位），缺少 job id 无法判定单岗`;
  } else if (code === 404 || code === 410) {
    out.status = 'closed';
    out.confidence = 0.8;
    out.reason = 'Greenhouse board 不存在（400/404）';
  } else {
    out.reason = `Greenhouse board 请求异常 (HTTP ${code})`;
  }
}

async function greenhouseListed(base, jobId, timeoutMs) {
  const { code, data } = await getJson(`${base}/jobs`, timeoutMs);
  if (code !== 200 || !data || typeof data !== 'object') return null;
  const jobs = Array.isArray(data.jobs) ? data.jobs : [];
  const ids = new Set(jobs.filter(Boolean).map((j) => str(j.id)));
  return ids.has(str(jobId));
}

function flagDeadline(data, out) {
  const deadline = data && data.application_deadline;
  if (!deadline) return;
  const dt = new Date(deadline);
  if (!Number.isNaN(dt.getTime()) && dt.getTime() < Date.now()) {
    out.status = 'closed';
    out.confidence = 0.9;
    out.reason = `岗位申请截止日期已过 (${deadline})`;
  }
}

async function checkLever(ref, out, timeoutMs) {
  const token = ref.token;
  const jobId = ref.jobId;
  if (!token) {
    out.reason = '无法从 URL 解析 Lever board token';
    return;
  }
  out.canonical_url = jobId
    ? `https://jobs.lever.co/${token}/${jobId}`
    : `https://jobs.lever.co/${token}`;

  if (jobId) {
    const { code, data } = await getJson(
      `https://api.lever.co/v0/postings/${token}/${jobId}`,
      timeoutMs
    );
    out.http_status = code;
    if (code === 200 && data && typeof data === 'object') {
      out.status = 'open';
      out.confidence = 0.97;
      out.reason = 'Lever 源头 API 返回该岗位仍在招';
      out.matched_title = str(data.text);
      const categories = data.categories;
      out.location = categories && typeof categories === 'object' ? str(categories.location) : '';
      const created = Number(data.createdAt);
      if (Number.isFinite(created) && created > 0) {
        out.posted_at = new Date(created).toISOString();
      }
      out.apply_url = str(data.applyUrl || data.hostedUrl) || out.canonical_url;
      return;
    }
    if (code === 404 || code === 410) {
      const board = await getJson(
        `https://api.lever.co/v0/postings/${token}?mode=json`,
        timeoutMs
      );
      if (board.code === 200 && Array.isArray(board.data)) {
        const ids = new Set(board.data.filter(Boolean).map((j) => str(j.id)));
        if (ids.has(str(jobId))) {
          out.status = 'open';
          out.confidence = 0.7;
          out.reason = '详情接口 404，但 board 列表中仍存在该岗位';
        } else {
          out.status = 'closed';
          out.confidence = 0.97;
          out.reason = 'Lever 源头已下架该岗位（详情 404 且 board 无此 ID）';
        }
      } else {
        out.status = 'closed';
        out.confidence = 0.8;
        out.reason = 'Lever 源头详情返回 404';
      }
      return;
    }
    if (code === 401 || code === 403) {
      out.reason = 'Lever board 未公开或拒绝访问';
      return;
    }
    out.reason = `Lever 详情请求异常 (HTTP ${code})`;
    return;
  }

  const { code, data } = await getJson(
    `https://api.lever.co/v0/postings/${token}?mode=json`,
    timeoutMs
  );
  out.http_status = code;
  if (code === 200 && Array.isArray(data)) {
    out.status = 'open';
    out.confidence = 0.4;
    out.reason = `仅校验到 board 存在（${data.length} 个在招岗位），缺少 job id`;
  } else if (code === 404 || code === 410) {
    out.status = 'closed';
    out.confidence = 0.75;
    out.reason = 'Lever board 不存在';
  } else {
    out.reason = `Lever board 请求异常 (HTTP ${code})`;
  }
}

async function checkAshby(ref, out, timeoutMs) {
  const token = ref.token;
  const jobId = ref.jobId;
  if (!token) {
    out.reason = '无法从 URL 解析 Ashby organization slug';
    return;
  }
  out.canonical_url = jobId
    ? `https://jobs.ashbyhq.com/${token}/${jobId}`
    : `https://jobs.ashbyhq.com/${token}`;

  const { code, data } = await getJson(
    `https://api.ashbyhq.com/posting-api/job-board/${token}?includeCompensation=true`,
    timeoutMs
  );
  out.http_status = code;
  if (code !== 200 || !data || typeof data !== 'object') {
    if (code === 404 || code === 410) {
      out.status = 'closed';
      out.confidence = 0.7;
      out.reason = 'Ashby organization 不存在';
    } else {
      out.reason = `Ashby board API 请求异常 (HTTP ${code})`;
    }
    return;
  }

  const jobs = Array.isArray(data.jobs) ? data.jobs : [];
  if (!jobId) {
    out.status = 'open';
    out.confidence = 0.4;
    out.reason = `仅校验到 Ashby board 存在（${jobs.length} 个在招岗位），缺少 job id`;
    return;
  }

  const match = jobs.find((j) => j && str(j.id) === str(jobId));
  if (match) {
    out.status = 'open';
    out.confidence = 0.97;
    out.reason = 'Ashby 源头 board 中仍存在该岗位';
    out.matched_title = str(match.title);
    out.location = str(match.location);
    out.posted_at = str(match.publishedAt || match.updatedAt);
    out.apply_url = str(match.jobUrl || match.applyUrl) || out.canonical_url;
    if (match.isListed === false) {
      out.confidence = 0.6;
      out.reason = '岗位在 Ashby 中仍存在但已取消公开列出（isListed=false）';
    }
    return;
  }

  out.status = 'closed';
  out.confidence = 0.95;
  out.reason = `Ashby 源头 board 已无此岗位（当前在招 ${jobs.length} 个）`;
}

async function checkGeneric(url, out, timeoutMs) {
  out.ats = out.ats !== 'unknown' ? out.ats : 'careers_page';
  const { code, text, finalUrl } = await getText(url, timeoutMs);
  out.http_status = code;
  out.canonical_url = finalUrl || url;
  if (code === null) {
    out.reason = '无法访问该页面（网络错误/超时）';
    return;
  }
  if (code === 404 || code === 410) {
    out.status = 'closed';
    out.confidence = 0.7;
    out.reason = `源页面返回 HTTP ${code}，岗位页面已不存在`;
    return;
  }
  if (code === 401 || code === 403) {
    out.reason = `源页面拒绝访问 (HTTP ${code})，需登录或反爬`;
    return;
  }
  if (code >= 500) {
    out.reason = `源站异常 (HTTP ${code})`;
    return;
  }
  if (!text) {
    out.reason = `源页面返回空内容 (HTTP ${code})`;
    return;
  }

  if (collapsedToRoot(url, finalUrl)) {
    out.status = 'closed';
    out.confidence = 0.5;
    out.reason = '原岗位 URL 被重定向到列表/首页，岗位详情页已不存在';
    return;
  }

  const lower = text.toLowerCase();
  const phrase = CLOSED_PHRASES.find((p) => lower.includes(p));
  if (phrase) {
    out.status = 'closed';
    out.confidence = 0.75;
    out.reason = `页面出现失效提示文案: “${phrase}”`;
    return;
  }

  if (OPEN_PHRASES.some((p) => lower.includes(p))) {
    out.status = 'open';
    out.confidence = 0.5;
    out.reason = '页面仍包含申请入口文案，但无结构化数据佐证';
    return;
  }

  out.status = 'unknown';
  out.confidence = 0.25;
  out.reason = '页面可访问但未找到明确的在招/失效信号（可能是 JS 渲染页面）';
}

function collapsedToRoot(original, finalUrl) {
  if (!finalUrl) return false;
  let o;
  let f;
  try {
    o = new URL(normalizeUrl(original));
    f = new URL(normalizeUrl(finalUrl));
  } catch {
    return false;
  }
  if (o.hostname !== f.hostname) return false;
  const oParts = splitParts(o.pathname);
  const fParts = splitParts(f.pathname);
  return oParts.length >= 2 && fParts.length <= 1;
}

/**
 * Offline fallback verification. Never throws; always resolves to a
 * VerifyResult-shaped object.
 *
 * @param {string} rawUrl
 * @param {{tokenHint?: string|null, timeoutMs?: number}} [options]
 * @returns {Promise<object>}
 */
export async function verifyLocal(rawUrl, options = {}) {
  const started = Date.now();
  const url = normalizeUrl(rawUrl);
  const result = emptyResult(url || rawUrl || '');
  const ref = identifyAts(url);
  if (options.tokenHint && !ref.token) ref.token = options.tokenHint;
  result.ats = ref.ats;

  try {
    const timeoutMs = Number(options.timeoutMs) || DEFAULT_TIMEOUT_MS;
    if (ref.ats === 'greenhouse') await checkGreenhouse(ref, result, timeoutMs);
    else if (ref.ats === 'lever') await checkLever(ref, result, timeoutMs);
    else if (ref.ats === 'ashby') await checkAshby(ref, result, timeoutMs);
    else await checkGeneric(url, result, timeoutMs);
  } catch (err) {
    result.status = 'unknown';
    result.confidence = 0;
    result.reason = `校验过程异常: ${err && err.message ? err.message : err}`;
  }

  if (!result.apply_url) result.apply_url = result.canonical_url || result.input_url || url;
  result.elapsed_ms = Date.now() - started;
  result.checked_at = new Date().toISOString();
  return result;
}
