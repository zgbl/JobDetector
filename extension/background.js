/**
 * background.js — MV3 service worker (ES module).
 *
 * Responsibilities
 * ----------------
 * 1. Answer `VERIFY_JOB` from the content script / popup with a VerifyResult.
 * 2. Answer `GHOST_ANALYZE` by proxying the LLM call to our own backend.
 * 3. Cache verdicts in `chrome.storage.local` under `jd_cache_v1`.
 * 4. Keep the toolbar badge in sync for the active tab.
 * 5. Seed default settings on install.
 *
 * Caching model (see README): open verdicts are trusted longer than negative
 * ones, because a closed posting can be re-opened while an open one is far more
 * stable. TTLs below are derived from the `cacheTtlHours` setting (default 12).
 */

import {
  identifyAts,
  verifyLocal,
  cacheKeyFor,
  coerceResult,
  normalizeUrl,
  DEFAULT_TIMEOUT_MS,
} from './lib/ats.js';

/* --- Cache tuning constants (documented in README.md) ------------------ */
const CACHE_KEY = 'jd_cache_v1';
/** `open` verdicts live this long when the user keeps the default 12h. */
const CACHE_TTL_OPEN_MS = 12 * 60 * 60 * 1000;
/** `closed` / `unknown` verdicts are re-checked twice as often (6h). */
const CACHE_TTL_CLOSED_MS = 6 * 60 * 60 * 1000;
/** Hard cap on cached entries; oldest `checkedAt` is evicted first. */
const CACHE_MAX_ENTRIES = 500;
/** Network timeout for `POST /api/verify/source` and friends. */
const VERIFY_TIMEOUT_MS = DEFAULT_TIMEOUT_MS;
/** The ghost LLM call is slower than a plain existence check. */
const GHOST_TIMEOUT_MS = 25000;

const SETTINGS_KEY = 'settings';
const DEFAULT_SETTINGS = {
  backendBaseUrl: 'https://jobdetector.blackrice.top',
  enableLinkedIn: true,
  enableIndeed: true,
  autoVerify: true,
  showGhostButton: true,
  cacheTtlHours: 12,
};

/* ------------------------------------------------------------------ *
 * Settings
 * ------------------------------------------------------------------ */

/** Strip a trailing slash so `base + '/api/...'` is always well formed. */
function cleanBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

/**
 * Read settings. The canonical location is `chrome.storage.sync.settings`, but
 * we also accept the literal dotted key `settings.backendBaseUrl` so both
 * interpretations of the contract keep working.
 */
export async function getSettings() {
  const flatKeys = Object.keys(DEFAULT_SETTINGS).map((k) => `${SETTINGS_KEY}.${k}`);
  let stored = {};
  try {
    stored = await chrome.storage.sync.get([SETTINGS_KEY, ...flatKeys]);
  } catch {
    stored = {};
  }
  const bundle = stored[SETTINGS_KEY] && typeof stored[SETTINGS_KEY] === 'object'
    ? stored[SETTINGS_KEY]
    : {};
  const merged = { ...DEFAULT_SETTINGS, ...bundle };
  for (const key of Object.keys(DEFAULT_SETTINGS)) {
    const dotted = stored[`${SETTINGS_KEY}.${key}`];
    if (dotted !== undefined && bundle[key] === undefined) merged[key] = dotted;
  }
  merged.backendBaseUrl = cleanBaseUrl(merged.backendBaseUrl);
  const ttl = Number(merged.cacheTtlHours);
  merged.cacheTtlHours = Number.isFinite(ttl) && ttl > 0 ? ttl : DEFAULT_SETTINGS.cacheTtlHours;
  return merged;
}

/** Persist settings under `settings` *and* the dotted keys. */
export async function saveSettings(next) {
  const merged = { ...DEFAULT_SETTINGS, ...(next || {}) };
  merged.backendBaseUrl = cleanBaseUrl(merged.backendBaseUrl);
  const payload = { [SETTINGS_KEY]: merged };
  for (const key of Object.keys(DEFAULT_SETTINGS)) {
    payload[`${SETTINGS_KEY}.${key}`] = merged[key];
  }
  await chrome.storage.sync.set(payload);
  return merged;
}

/* ------------------------------------------------------------------ *
 * Small utilities
 * ------------------------------------------------------------------ */

function ttlFor(status, ttlHours) {
  const hours = Number(ttlHours) > 0 ? Number(ttlHours) : 12;
  if (status === 'open') return hours * 60 * 60 * 1000;
  // closed / unknown expire at half the open TTL (default: 6h)
  return Math.max(1, hours / 2) * 60 * 60 * 1000;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = VERIFY_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function postJson(url, body, timeoutMs) {
  const res = await fetchWithTimeout(
    url,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    },
    timeoutMs
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/* ------------------------------------------------------------------ *
 * Cache
 * ------------------------------------------------------------------ */

async function readCache() {
  try {
    const stored = await chrome.storage.local.get(CACHE_KEY);
    const value = stored && stored[CACHE_KEY];
    return value && typeof value === 'object' ? value : {};
  } catch {
    return {};
  }
}

async function getCached(key, ttlHours) {
  if (!key) return null;
  const cache = await readCache();
  const entry = cache[key];
  if (!entry || !entry.result) return null;
  const checkedAt = Date.parse(entry.checkedAt || '');
  if (!Number.isFinite(checkedAt)) return null;
  const age = Date.now() - checkedAt;
  if (age > ttlFor(entry.result.status, ttlHours)) return null;
  return { ...coerceResult(entry.result, entry.result.input_url), cached: true };
}

async function putCache(key, result, ttlHours) {
  if (!key) return;
  try {
    const cache = await readCache();
    cache[key] = { result, checkedAt: new Date().toISOString() };
    const keys = Object.keys(cache);
    if (keys.length > CACHE_MAX_ENTRIES) {
      keys
        .sort((a, b) => Date.parse(cache[a].checkedAt || 0) - Date.parse(cache[b].checkedAt || 0))
        .slice(0, keys.length - CACHE_MAX_ENTRIES)
        .forEach((old) => delete cache[old]);
    }
    await chrome.storage.local.set({ [CACHE_KEY]: cache });
  } catch {
    /* cache is best-effort; never fail a verification because of it */
  }
  return ttlHours;
}

/* ------------------------------------------------------------------ *
 * Badge
 * ------------------------------------------------------------------ */

const BADGE_STATES = {
  open: { text: '✓', color: '#1a7f37' },
  closed: { text: '!', color: '#c62828' },
  unknown: { text: '?', color: '#6b7280' },
};

async function updateBadge(tabId, status) {
  if (typeof tabId !== 'number' || tabId < 0) return;
  const state = BADGE_STATES[status] || BADGE_STATES.unknown;
  try {
    await chrome.action.setBadgeText({ tabId, text: state.text });
    await chrome.action.setBadgeBackgroundColor({ tabId, color: state.color });
  } catch {
    /* the tab may be gone */
  }
}

/* ------------------------------------------------------------------ *
 * Verification pipeline
 * ------------------------------------------------------------------ */

/** Collect ATS-shaped URLs from the page payload, preserving page order. */
function buildCandidates(payload) {
  const raw = [];
  if (payload && payload.url) raw.push(payload.url);
  if (payload && Array.isArray(payload.urls)) raw.push(...payload.urls);
  const out = [];
  for (const item of raw) {
    const url = normalizeUrl(item);
    if (!url || out.includes(url)) continue;
    if (identifyAts(url).ats === 'unknown') continue;
    out.push(url);
    if (out.length >= 12) break;
  }
  return out;
}

/** open > closed > unknown, then by confidence. Mirrors Python `best()`. */
function pickBest(results) {
  const rank = { open: 2, closed: 1, unknown: 0 };
  const sorted = [...results].sort((a, b) => {
    const ra = rank[a.status] || 0;
    const rb = rank[b.status] || 0;
    if (ra !== rb) return rb - ra;
    return (b.confidence || 0) - (a.confidence || 0);
  });
  return sorted.length ? sorted[0] : null;
}

function noSourceResult(payload) {
  const result = coerceResult(null, payload && payload.url);
  result.reason = 'No source information found. Try adding the company name, or paste the employer\'s own apply link.';
  result.confidence = 0;
  return result;
}

async function verifyViaBackend(payload, candidates, settings) {
  const body = {
    urls: candidates,
    company: payload.company || '',
    title: payload.title || '',
    location: payload.location || '',
    refresh: Boolean(payload.refresh),
  };
  const data = await postJson(`${settings.backendBaseUrl}/api/verify/source`, body, VERIFY_TIMEOUT_MS);
  const rawResults = Array.isArray(data && data.results) ? data.results : [];
  const results = rawResults.map((r) => coerceResult(r, (payload && payload.url) || ''));
  const lookup = data && data.lookup ? coerceResult(data.lookup, (payload && payload.url) || '') : null;

  // An explicit, high-confidence verdict for the exact URL on the page beats a
  // fuzzy company+title match; the fuzzy match is kept as `alternative` so the
  // card can still surface "a similar role is open".
  const definitive = results.filter(
    (r) => (r.status === 'open' || r.status === 'closed') && (r.confidence || 0) >= 0.85
  );
  let best = null;
  let alternative = null;
  if (definitive.length) {
    best = pickBest(definitive);
    if (lookup && lookup.status === 'open' && best && best.status === 'closed') {
      alternative = lookup;
    }
  } else {
    best = pickBest(results.concat(lookup ? [lookup] : []));
  }
  if (!best) return noSourceResult(payload);
  if (data && data.alternative && !alternative) {
    alternative = coerceResult(data.alternative, (payload && payload.url) || '');
  }
  if (alternative) best.alternative = alternative;
  return best;
}

/** Offline path: run the local verifier over every candidate, pick the best. */
async function verifyOffline(payload, candidates) {
  if (!candidates.length) return noSourceResult(payload);
  const settled = await Promise.all(
    candidates.map((url) => verifyLocal(url, { tokenHint: payload.tokenHint || null }))
  );
  return pickBest(settled.map((r) => coerceResult(r, (payload && payload.url) || '')))
    || noSourceResult(payload);
}

async function handleVerifyJob(payload = {}) {
  const settings = await getSettings();
  const candidates = buildCandidates(payload);
  const ref = candidates.length ? identifyAts(candidates[0]) : { ats: 'unknown', token: null, jobId: null };
  const key = cacheKeyFor(ref, payload.url);

  if (!payload.refresh) {
    const cached = await getCached(key, settings.cacheTtlHours);
    if (cached) {
      return { ok: true, result: cached, degraded: false, candidates, cached: true };
    }
  }

  let result = null;
  let degraded = false;

  if (settings.backendBaseUrl) {
    try {
      result = await verifyViaBackend(payload, candidates, settings);
    } catch {
      degraded = true;
    }
  } else {
    degraded = true;
  }

  if (!result) {
    degraded = true;
    result = await verifyOffline(payload, candidates);
  }

  result.checked_at = new Date().toISOString();
  await putCache(key, result, settings.cacheTtlHours);

  return { ok: true, result, degraded, candidates, cached: false };
}

/* ------------------------------------------------------------------ *
 * Ghost job analysis
 * ------------------------------------------------------------------ */

async function handleGhostAnalyze(payload = {}) {
  const settings = await getSettings();
  if (!settings.backendBaseUrl) {
    return { ok: false, error: 'Backend required (no backend URL configured)' };
  }
  const body = {
    job_title: String(payload.job_title || '').slice(0, 300),
    company_name: String(payload.company_name || '').slice(0, 300),
    post_age_days:
      payload.post_age_days === null || payload.post_age_days === undefined
        ? null
        : Number(payload.post_age_days),
    source_type: String(payload.source_type || 'unknown'),
    jd_text: String(payload.jd_text || '').slice(0, 6000),
    source_status: ['open', 'closed', 'unknown'].includes(payload.source_status)
      ? payload.source_status
      : null,
    lang: 'en',
  };
  try {
    const data = await postJson(`${settings.backendBaseUrl}/api/ghost/analyze`, body, GHOST_TIMEOUT_MS);
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: `Ghost job analysis failed: ${err && err.message ? err.message : 'backend unavailable'}` };
  }
}

/* ------------------------------------------------------------------ *
 * Message router
 * ------------------------------------------------------------------ */

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const type = message && message.type;

  if (type === 'VERIFY_JOB') {
    handleVerifyJob(message.payload || {})
      .then(async (response) => {
        const tabId = sender && sender.tab ? sender.tab.id : undefined;
        if (typeof tabId === 'number') await updateBadge(tabId, response.result.status);
        sendResponse(response);
      })
      .catch((err) => {
        const result = coerceResult(null, (message.payload && message.payload.url) || '');
        result.reason = `Check failed: ${err && err.message ? err.message : 'unknown error'}`;
        sendResponse({ ok: false, result, degraded: true, candidates: [], cached: false });
      });
    return true;
  }

  if (type === 'GHOST_ANALYZE') {
    handleGhostAnalyze(message.payload || {})
      .then(sendResponse)
      .catch((err) => sendResponse({ ok: false, error: `Ghost job analysis failed: ${err && err.message}` }));
    return true;
  }

  if (type === 'GET_SETTINGS') {
    getSettings().then(sendResponse).catch(() => sendResponse({ ...DEFAULT_SETTINGS }));
    return true;
  }

  if (type === 'SET_BADGE') {
    const tabId = sender && sender.tab ? sender.tab.id : undefined;
    updateBadge(tabId, message.status).then(() => sendResponse({ ok: true }));
    return true;
  }

  return false;
});

/* ------------------------------------------------------------------ *
 * Lifecycle
 * ------------------------------------------------------------------ */

chrome.runtime.onInstalled.addListener((details) => {
  chrome.storage.sync.get(SETTINGS_KEY).then((stored) => {
    const existing = stored && stored[SETTINGS_KEY];
    const merged = { ...DEFAULT_SETTINGS, ...(existing || {}) };
    saveSettings(merged).catch(() => {});
  }).catch(() => {});
  if (details && details.reason === 'install') {
    chrome.action.setBadgeText({ text: '' }).catch(() => {});
  }
});
